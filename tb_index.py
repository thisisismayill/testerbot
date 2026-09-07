#!/usr/bin/env python3
"""
TesterBot Index — crawl several domains, build a link index, compute our own
Domain Authority, and export an explorable dashboard.

    python3 tb_index.py site-a.com site-b.com site-c.com
    python3 tb_index.py --seeds seeds.txt --max-pages 30

The index accumulates in a local SQLite file (testerbot-index.db) and grows
every time you run it. Only crawl sites you own or are authorised to crawl.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.sync_api import sync_playwright

from testerbot import __version__
from testerbot.config import Config
from testerbot.linkgraph import LinkGraph
from testerbot.harvest import harvest_domain
from testerbot.index_store import IndexStore
from testerbot.authority import build_leaderboard
from testerbot.index_report import render_index
from testerbot.urls import normalise, registrable
from testerbot.robots import RobotsCache, USER_AGENT
from testerbot.topic import TopicFilter


# Chromium's wording for "there is no network here", as opposed to "this one
# site is broken". Telling them apart decides whether to keep going.
_OFFLINE_MARKERS = ("ERR_NAME_NOT_RESOLVED", "ERR_INTERNET_DISCONNECTED",
                    "ERR_NETWORK_CHANGED", "ERR_ADDRESS_UNREACHABLE",
                    "ERR_PROXY_CONNECTION_FAILED", "ERR_NAME_RESOLUTION_FAILED")


def _looks_offline(err: str) -> bool:
    return any(m in (err or "") for m in _OFFLINE_MARKERS)


def norm_seed(s: str) -> str:
    s = s.strip()
    if not s or s.startswith("#"):
        return ""
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="tb_index.py",
        description="Build a multi-domain link index with our own Domain Authority.")
    p.add_argument("domains", nargs="*", help="Domains / URLs to crawl")
    p.add_argument("--seeds", help="Text file with one domain per line")
    p.add_argument("--db", default="testerbot-index.db", help="Index database file")
    p.add_argument("--out", default="index-report", help="Dashboard output folder")
    p.add_argument("--max-pages", type=int, default=25, help="Pages per domain")
    p.add_argument("--max-depth", type=int, default=3)
    p.add_argument("--allow-subdomains", action="store_true")
    p.add_argument("--ignore-robots", action="store_true",
                   help="Do NOT obey robots.txt (only for sites you own)")
    p.add_argument("--delay", type=int, default=400,
                   help="Politeness delay between pages, ms (default 400)")
    p.add_argument("--headed", dest="headless", action="store_false", default=True)
    p.add_argument("--no-crawl", action="store_true",
                   help="Skip crawling; just recompute authority + dashboard from the DB")

    g = p.add_argument_group("keep growing on its own")
    g.add_argument("--expand", type=int, metavar="N",
                   help="After the seeds, also crawl the N most-linked domains the index "
                        "has discovered but never visited. Run it again and again and the "
                        "index keeps reaching further out")
    g.add_argument("--min-links", type=int, default=2, metavar="N",
                   help="Only expand into a domain once at least N different domains link "
                        "to it (default 2) - keeps one-off mentions out of the crawl")
    g.add_argument("--time-budget", type=int, metavar="MINUTES",
                   help="Stop starting new domains after this many minutes. For scheduled "
                        "runs, so a nightly crawl never overruns")
    g.add_argument("--skip-domain", action="append", default=[], metavar="DOMAIN",
                   help="Never expand into this domain (repeatable)")
    g.add_argument("--per-domain-seconds", type=int, default=180, metavar="SECONDS",
                   help="Give up on one domain after this long and move to the next "
                        "(default 180). An index is built on breadth: one slow site "
                        "must not spend the whole run. 0 disables the cap")
    g.add_argument("--topic", action="append", default=[], metavar="TERM",
                   help="A word that belongs to your subject, e.g. --topic fintech "
                        "--topic payments. Repeatable. A discovered domain must show "
                        "one of these before the crawl goes deeper into it, which is "
                        "what stops a focused index drifting into whatever the web "
                        "links to next. Without any, nothing is filtered")
    g.add_argument("--min-topic-hits", type=int, default=2, metavar="N",
                   help="How many DIFFERENT subject terms a candidate's page must "
                        "show (default 2). One is too easy: a gaming site that "
                        "mentions blockchain once would pass. Link text is always "
                        "judged on one, because an anchor is only a few words")
    g.add_argument("--topic-file", metavar="FILE",
                   help="Text file with one subject term per line (# for comments)")
    g.add_argument("--page-timeout", type=int, default=20000, metavar="MS",
                   help="Per-page load timeout while harvesting links (default 20000). "
                        "Lower than the QA crawl's, because a page that will not load "
                        "in 20s is not worth a link index's time")
    p.add_argument("--version", action="version", version=f"TesterBot Index {__version__}")
    args = p.parse_args(argv)

    seeds = [norm_seed(d) for d in args.domains]
    if args.seeds:
        with open(args.seeds, encoding="utf-8") as fh:
            seeds += [norm_seed(line) for line in fh]
    seeds = [s for s in seeds if s]

    if args.expand and args.ignore_robots:
        p.error("--expand crawls sites that are not yours, so robots.txt must be "
                "respected. Drop --ignore-robots.")

    topic_terms = list(args.topic)
    if args.topic_file:
        with open(args.topic_file, encoding="utf-8") as fh:
            topic_terms += [l.strip() for l in fh
                            if l.strip() and not l.startswith("#")]
    # Two filters, because the two gates see different amounts of text.
    # A page has paragraphs, so it can be asked for two distinct subject terms
    # and a gaming site that says "blockchain" once no longer passes. An anchor
    # is three words - demanding two terms there would throw away real sites
    # linked as "payments partner", so that gate stays at one.
    topic = TopicFilter(topic_terms, min_hits=args.min_topic_hits)
    topic_anchor = TopicFilter(topic_terms, min_hits=1)

    store = IndexStore(args.db)
    print(f"TesterBot Index v{__version__}")
    print(f"  index db : {store.path}")
    if topic:
        shown = ", ".join(topic.terms[:6]) + (" …" if len(topic.terms) > 6 else "")
        print(f"  subject  : {len(topic.terms)} terms, {topic.min_hits} needed "
              f"on a page ({shown})")

    expanded = []
    if args.expand:
        waiting = store.frontier_size(args.min_links)
        already = {registrable(s.split("//")[-1].split("/")[0]) for s in seeds}
        # Ask for more than we need: infrastructure and off-subject candidates
        # are dropped here, before any of them costs a page fetch.
        found = store.frontier(args.expand * 4, args.min_links, args.skip_domain)
        expanded, skipped_infra, skipped_topic = [], 0, 0
        for dom, _n, url, anchors in found:
            if dom in already:
                continue
            if TopicFilter.is_infrastructure(dom):
                skipped_infra += 1
                store.mark_offtopic(dom)
                continue
            if topic and not topic_anchor.matches(f"{dom} {anchors}"):
                # No sign of the subject in the domain name or in a single
                # anchor pointing at it. Still worth one page - the link text
                # is often just "here" - so it is not written off yet.
                skipped_topic += 1
                continue
            expanded.append((dom, url))
            if len(expanded) >= args.expand:
                break
        seeds += [url for _dom, url in expanded]
        print(f"  frontier : {waiting} domains discovered and not yet crawled, "
              f"taking {len(expanded)}")
        if skipped_infra or skipped_topic:
            bits = []
            if skipped_infra:
                bits.append(f"{skipped_infra} infrastructure (job boards, "
                            f"newswires, CMS vendors)")
            if skipped_topic:
                bits.append(f"{skipped_topic} with no sign of the subject in "
                            f"their anchors")
            print(f"             skipped " + " and ".join(bits))

    print(f"  domains  : {len(seeds)} to crawl"
          + (f" ({len(seeds) - len(expanded)} seeds + {len(expanded)} from the frontier)"
             if expanded else ""))
    if args.time_budget:
        print(f"  budget   : {args.time_budget} min total"
              + (f", {args.per_domain_seconds}s per domain"
                 if args.per_domain_seconds else ""))
    elif args.per_domain_seconds:
        print(f"  budget   : {args.per_domain_seconds}s per domain")
    print("  Only crawl sites you own or are authorised to crawl.\n")

    if seeds and not args.no_crawl:
        cfg = Config(max_pages=args.max_pages, max_depth=args.max_depth,
                     allow_subdomains=args.allow_subdomains, headless=args.headless)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=args.headless,
                                         args=["--disable-dev-shm-usage"])
            context = browser.new_context(user_agent=USER_AGENT)
            robots = None if args.ignore_robots else RobotsCache()
            if robots is None:
                print("  ⚠ robots.txt IGNORED (for your own sites only)")
            else:
                print("  respecting robots.txt · UA: TesterBotIndex/2.0")
            context.set_default_navigation_timeout(cfg.nav_timeout_ms)
            deadline = (time.time() + args.time_budget * 60) if args.time_budget else None
            offline_streak = 0
            for i, seed in enumerate(seeds, 1):
                if deadline and time.time() > deadline:
                    print(f"  time budget spent - stopping with {len(seeds) - i + 1} "
                          f"domains left for the next run", flush=True)
                    break
                dom = registrable(seed.split("//")[-1].split("/")[0])
                print(f"[{i}/{len(seeds)}] crawling {dom} …", flush=True)
                graph = LinkGraph(seed, args.allow_subdomains)
                try:
                    info = harvest_domain(context, seed, cfg, graph,
                                          log=lambda m: print(m, flush=True),
                                          robots=robots, delay_ms=args.delay,
                                          max_seconds=args.per_domain_seconds or None,
                                          page_timeout_ms=args.page_timeout,
                                          topic=topic if topic else None)
                except Exception as exc:
                    print(f"    error: {exc}", flush=True)
                    info = {"pages": 0, "seconds": 0}
                new = store.add_edges(graph.edges)
                blk = f" · {info.get('blocked',0)} robots-blocked" if info.get('blocked') else ""
                cap = " · time cap reached" if info.get("out_of_time") else ""
                print(f"  = {info['pages']} pages · {len(graph.edges)} links "
                      f"({new} new){blk} · {info['seconds']}s{cap}", flush=True)
                if info.get("off_topic"):
                    store.mark_offtopic(dom)
                    offline_streak = 0
                    print(f"    off subject - not part of this index, "
                          f"moving on", flush=True)
                elif info["pages"]:
                    store.mark_crawled(dom)
                    offline_streak = 0
                    if info.get("thin_page"):
                        print(f"    note: the first page carried almost no text "
                              f"(a consent wall or a JS-only page), so the subject "
                              f"check was skipped - kept rather than judged",
                              flush=True)
                else:
                    # Never write a domain off as crawled when we never reached it:
                    # the frontier would stop offering it and the index would be
                    # missing it for good, silently.
                    why = info.get("error") or ""
                    tries = store.mark_failed(dom, why)
                    left = store.MAX_ATTEMPTS - tries
                    print(f"    ⚠ nothing was crawled — {why}" if why else
                          "    ⚠ nothing was crawled.", flush=True)
                    print(f"       not marked as done; "
                          + (f"{left} more attempt{'' if left == 1 else 's'} left"
                             if left > 0 else
                             f"giving up after {tries} attempts"), flush=True)
                    if _looks_offline(why):
                        offline_streak += 1
                        if offline_streak >= 3:
                            print("\n  ⚠ three domains in a row failed to resolve — this "
                                  "machine looks offline.", flush=True)
                            print("    Stopping so the rest of the frontier is not burned "
                                  "on a dead network.", flush=True)
                            print("    Reconnect and run the same command again.", flush=True)
                            break
                    else:
                        offline_streak = 0
                    if seed.startswith("https://") and not _looks_offline(why):
                        print(f"       if {dom} is http-only, pass the full "
                              f"address: http://{dom}", flush=True)
            context.close()
            browser.close()

    print("\n→ computing Domain Authority over the index …")
    store.set_meta("last_run", str(int(time.time())))
    data = build_leaderboard(store)
    # The crawl is the expensive part and it is already committed to the index
    # database by this point. If the dashboard cannot be written - a read-only
    # folder, a full disk, a permission the OS will not grant - say so and keep
    # going. Losing an hour of crawling because one HTML file would not save is
    # not an acceptable trade.
    html_path = None
    render_error = None
    try:
        html_path = render_index(data, store, args.out)
    except Exception as exc:
        render_error = f"{type(exc).__name__}: {exc}"

    st = data["stats"]
    print("=" * 64)
    print(f"  Index: {st['domains']} domains · {st['edges']} links "
          f"· {st['cross_domain_edges']} cross-domain")
    # Social networks, shorteners and CDNs sit in every site's footer, so in a
    # focused index they float to the top and hide the domains you came for.
    # They stay in the data; they are just not what this ranking is for.
    ranked = [r for r in data["leaderboard"]
              if not r.get("utility") and not r.get("thin")]
    hidden = sum(1 for r in data["leaderboard"] if r.get("utility"))
    thin = sum(1 for r in data["leaderboard"]
               if r.get("thin") and not r.get("utility"))
    print("  Top domains by our Domain Authority:")
    for r in ranked[:10]:
        flag = "•" if r["crawled"] else " "
        print(f"   {flag} DA {r['authority']:3}  {r['referring_domains']:3} refdom  "
              f"{r['domain']}")
    if hidden:
        print(f"   ({hidden} social / CDN / cookie-banner domains left out of this "
              f"ranking - still in the index)")
    if thin:
        floor = data.get("min_refdoms_to_rank", 2)
        print(f"   ({thin} domains with fewer than {floor} referring domains not "
              f"ranked yet - too little evidence to score)")
    print("-" * 64)
    waiting = store.frontier_size(args.min_links)
    if waiting:
        print(f"  Frontier: {waiting} more domains discovered, not yet crawled")
        print(f"            run again with --expand N to reach them")
    if html_path:
        print(f"  Dashboard: {html_path}")
    else:
        print(f"  ⚠ the dashboard could not be written to '{args.out}'")
        print(f"    {render_error}")
        print("    The crawl itself is safe - everything is in the index database")
        print("    below. Re-run with --no-crawl --out SOME_OTHER_FOLDER to build")
        print("    the dashboard again without crawling anything a second time.")
    print(f"  Index DB : {store.path}")
    print("=" * 64)
    store.close()
    return 0 if html_path else 3


if __name__ == "__main__":
    sys.exit(main())
