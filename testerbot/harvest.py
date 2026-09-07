"""Fast, link-only crawler for building the index across many domains.

Unlike the full TesterBot QA crawl (which clicks, fills forms, runs axe), this
does one thing: fetch pages and extract hyperlinks, as fast as possible, so we
can sweep many domains and grow the link index. One browser is reused across
all domains.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Dict, List, Optional, Set

from .config import Config
from .linkgraph import LinkGraph
from .urls import normalise, same_scope, is_asset, is_document, shorten
from .robots import RobotsCache

LINKS_JS = r"""
() => {
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href');
    if (!href) continue;
    out.push({
      href: a.href,
      text: ((a.innerText || a.textContent || '').trim()
             || (a.querySelector('img[alt]') ? a.querySelector('img[alt]').alt : '')).slice(0,120),
      rel: (a.getAttribute('rel') || '').toLowerCase()
    });
  }
  const t = (document.body ? (document.body.innerText || '') : '');
  return { url: location.href, title: (document.title||'').trim().slice(0,200),
           text: t.slice(0, 6000), links: out };
}
"""


def harvest_domain(context, base_url: str, cfg: Config,
                   graph: LinkGraph, log=None,
                   robots: "RobotsCache" = None, delay_ms: int = 0,
                   max_seconds: Optional[int] = None,
                   page_timeout_ms: Optional[int] = None,
                   topic=None) -> Dict[str, Any]:
    """BFS-crawl one domain for links, feeding the shared LinkGraph.

    If `robots` is given, URLs disallowed by robots.txt are skipped and any
    declared crawl-delay is honoured. `delay_ms` adds a politeness pause
    between page fetches.

    `topic`, when given, is checked against the first page that loads. A
    domain that shows no sign of the subject is abandoned after that one page
    rather than spending twenty-five on it: this is what stops a focused crawl
    drifting, one outbound link at a time, into whatever the web links to next.

    `max_seconds` caps how long one domain may hold the crawl. An index is
    built on breadth: twenty-five pages from a hundred domains says far more
    about who links to whom than twenty-five pages from twenty. Without a cap a
    single slow site quietly spends the whole run, and the pages already
    harvested from it are kept either way.
    """
    page = context.new_page()
    # let the robots cache fetch robots.txt through the browser's network stack
    if robots is not None and getattr(robots, "_bound", False) is False:
        def _bfetch(url):
            # fetch robots.txt through a real browser page, so it shares the
            # crawl's exact network + DNS resolution
            rp = None
            try:
                rp = context.new_page()
                resp = rp.goto(url, timeout=12000, wait_until="domcontentloaded")
                if not resp:
                    return None
                return resp.status, (resp.text() if resp.status < 400 else "")
            except Exception:
                return None
            finally:
                if rp is not None:
                    try: rp.close()
                    except Exception: pass
        robots._fetch = _bfetch
        robots._bound = True
    visited: Set[str] = set()
    queue: deque = deque([(normalise(base_url) or base_url, 0)])
    pages = 0
    blocked = 0
    first_error = None
    skip_re = cfg.skip_url_re()
    t0 = time.time()

    deadline = (t0 + max_seconds) if max_seconds else None
    out_of_time = False
    off_topic = False
    thin_page = False
    nav_timeout = page_timeout_ms or cfg.nav_timeout_ms
    while queue and pages < cfg.max_pages:
        if deadline and time.time() > deadline:
            out_of_time = True
            break
        url, depth = queue.popleft()
        if url in visited or depth > cfg.max_depth:
            continue
        if not same_scope(url, base_url, cfg.allow_subdomains):
            continue
        if (is_asset(url) and not is_document(url)) or skip_re.search(url):
            continue
        if robots is not None and not robots.can_fetch(url):
            blocked += 1
            visited.add(url)
            continue
        visited.add(url)
        wait = delay_ms
        if robots is not None:
            cd = robots.crawl_delay(url)
            if cd:
                wait = max(wait, int(cd * 1000))
        if wait and pages > 0:
            page.wait_for_timeout(min(wait, 5000))
        try:
            page.goto(url, timeout=nav_timeout, wait_until="domcontentloaded")
            page.wait_for_timeout(min(cfg.settle_ms, 600))
        except Exception as exc:
            # Keep the first failure. If every page fails the caller has nothing
            # to show the user otherwise, and "0 pages" with no reason is the
            # least helpful thing a crawler can say.
            if first_error is None:
                first_error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
            continue
        pages += 1
        try:
            data = page.evaluate(LINKS_JS)
        except Exception:
            continue
        if topic and pages == 1:
            body = (data.get("text") or "").strip()
            sample = f"{data.get('title','')} {url} {body}"
            # A page that gave us nothing has not told us it is off the subject -
            # it has told us nothing. Judging silence as a verdict is the same
            # mistake as reporting a blocked file as missing, and it cost this
            # index CoinDesk on its first clean run: a consent wall rendered no
            # text, so a central crypto publication was written off. The bar is
            # deliberately at the floor - a real page clears it easily, and only
            # an empty one does not.
            if len(body) < 60:
                thin_page = True
            elif not topic.matches(sample):
                off_topic = True
                break
        graph.note_page(url)
        for link in data.get("links", []):
            href = link.get("href", "")
            graph.add_link(url, href, link.get("text", ""), link.get("rel", ""))
            n = normalise(href, url)
            if n and same_scope(n, base_url, cfg.allow_subdomains) and n not in visited:
                queue.append((n, depth + 1))
        if log:
            log(f"    {pages}/{cfg.max_pages} · {int(time.time() - t0)}s · "
                f"{len(graph.edges)} links · {shorten(url, 58)}")

    try:
        page.close()
    except Exception:
        pass
    return {"pages": pages, "blocked": blocked, "error": first_error,
            "out_of_time": out_of_time, "off_topic": off_topic,
            "thin_page": thin_page,
            "seconds": round(time.time() - t0, 1)}
