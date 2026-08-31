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
from .urls import normalise, same_scope, is_asset, is_document
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
  return { url: location.href, title: (document.title||'').trim().slice(0,200), links: out };
}
"""


def harvest_domain(context, base_url: str, cfg: Config,
                   graph: LinkGraph, log=None,
                   robots: "RobotsCache" = None, delay_ms: int = 0) -> Dict[str, Any]:
    """BFS-crawl one domain for links, feeding the shared LinkGraph.

    If `robots` is given, URLs disallowed by robots.txt are skipped and any
    declared crawl-delay is honoured. `delay_ms` adds a politeness pause
    between page fetches.
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

    while queue and pages < cfg.max_pages:
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
            page.goto(url, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
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
        graph.note_page(url)
        for link in data.get("links", []):
            href = link.get("href", "")
            graph.add_link(url, href, link.get("text", ""), link.get("rel", ""))
            n = normalise(href, url)
            if n and same_scope(n, base_url, cfg.allow_subdomains) and n not in visited:
                queue.append((n, depth + 1))
        if log and pages % 5 == 0:
            log(f"    {pages} pages · {base_url}")

    try:
        page.close()
    except Exception:
        pass
    return {"pages": pages, "blocked": blocked, "error": first_error,
            "seconds": round(time.time() - t0, 1)}
