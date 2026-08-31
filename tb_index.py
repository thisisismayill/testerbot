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

    store = IndexStore(args.db)
    print(f"TesterBot Index v{__version__}")
    print(f"  index db : {store.path}")

    expanded = []
    if args.expand:
        waiting = store.frontier_size(args.min_links)
        already = {registrable(s.split("//")[-1].split("/")[0]) for s in seeds}
        found = store.frontier(args.expand, args.min_links, args.skip_domain)
        expanded = [(dom, url) for dom, _n, url in found if dom not in already]
        seeds += [url for _dom, url in expanded]
        print(f"  frontier : {waiting} domains discovered and not yet crawled, "
              f"taking {len(expanded)}")

    print(f"  domains  : {len(seeds)} to crawl"
          + (f" ({len(seeds) - len(expanded)} seeds + {len(expanded)} from the frontier)"
             if expanded else ""))
    if args.time_budget:
        print(f"  budget   : {args.time_budget} min")
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
                                          robots=robots, delay_ms=args.delay)
                except Exception as exc:
                    print(f"    error: {exc}", flush=True)
                    info = {"pages": 0, "seconds": 0}
                new = store.add_edges(graph.edges)
                store.mark_crawled(dom)
                blk = f" · {info.get('blocked',0)} robots-blocked" if info.get('blocked') else ""
                print(f"    {info['pages']} pages · {len(graph.edges)} links "
                      f"({new} new){blk} · {info['seconds']}s", flush=True)
                if not info["pages"]:
                    # Silence here reads as "nothing to find". Say what happened.
                    why = info.get("error")
                    print(f"    ⚠ nothing was crawled — {why}" if why else
                          "    ⚠ nothing was crawled.", flush=True)
                    if seed.startswith("https://"):
                        print(f"       if {dom} is http-only, pass the full "
                              f"address: http://{dom}", flush=True)
            context.close()
            browser.close()

    print("\n→ computing Domain Authority over the index …")
    store.set_meta("last_run", str(int(time.time())))
    data = build_leaderboard(store)
    html_path = render_index(data, store, args.out)

    st = data["stats"]
    print("=" * 64)
    print(f"  Index: {st['domains']} domains · {st['edges']} links "
          f"· {st['cross_domain_edges']} cross-domain")
    print("  Top domains by our Domain Authority:")
    for r in data["leaderboard"][:10]:
        flag = "•" if r["crawled"] else " "
        print(f"   {flag} DA {r['authority']:3}  {r['referring_domains']:3} refdom  "
              f"{r['domain']}")
    print("-" * 64)
    waiting = store.frontier_size(args.min_links)
    if waiting:
        print(f"  Frontier: {waiting} more domains discovered, not yet crawled")
        print(f"            run again with --expand N to reach them")
    print(f"  Dashboard: {html_path}")
    print(f"  Index DB : {store.path}")
    print("=" * 64)
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
