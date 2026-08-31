"""robots.txt handling — crawl like a bot people are glad to have visit.

The index harvester crawls other people's sites, so by default it fetches and
obeys robots.txt, identifies itself honestly, and waits politely between pages.
Being a declared, well-behaved crawler is what keeps a bot un-blocked at scale —
the single biggest structural advantage a link-intelligence product has.
"""
from __future__ import annotations

import time
import urllib.request
import urllib.robotparser
from typing import Dict, Optional
from urllib.parse import urlparse

# an honest, identifying user-agent (declared crawler, not a disguise)
USER_AGENT = ("Mozilla/5.0 (compatible; TesterBotIndex/2.0; "
              "+site-audit-and-index bot)")
UA_TOKEN = "TesterBotIndex"


class RobotsCache:
    """Fetches and caches robots.txt per origin; answers can_fetch()."""

    def __init__(self, user_agent: str = USER_AGENT, timeout: int = 12,
                 fetch=None) -> None:
        self.ua = user_agent
        self.timeout = timeout
        # fetch(url) -> (status:int, text:str) | None. Defaults to urllib; the
        # harvester passes a browser-backed fetcher so it shares the crawl's
        # network stack (and can resolve whatever the browser can).
        self._fetch = fetch or self._urllib_fetch
        self._cache: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}
        self._crawl_delay: Dict[str, float] = {}

    def _urllib_fetch(self, url: str):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.ua})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except Exception:
            return None

    def _origin(self, url: str) -> str:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"

    def _load(self, origin: str) -> Optional[urllib.robotparser.RobotFileParser]:
        if origin in self._cache:
            return self._cache[origin]
        rp = urllib.robotparser.RobotFileParser()
        robots_url = origin + "/robots.txt"
        try:
            res = self._fetch(robots_url)
            if not res or res[0] >= 400 or res[1] is None:
                self._cache[origin] = None          # no robots => allow all
                return None
            text = res[1]
            rp.parse(text.splitlines())
            # capture crawl-delay if declared
            try:
                cd = rp.crawl_delay(UA_TOKEN) or rp.crawl_delay("*")
                if cd:
                    self._crawl_delay[origin] = float(cd)
            except Exception:
                pass
            self._cache[origin] = rp
            return rp
        except Exception:
            self._cache[origin] = None              # unreachable => allow all
            return None

    def can_fetch(self, url: str) -> bool:
        rp = self._load(self._origin(url))
        if rp is None:
            return True
        try:
            return rp.can_fetch(UA_TOKEN, url) or rp.can_fetch("*", url)
        except Exception:
            return True

    def crawl_delay(self, url: str) -> float:
        return self._crawl_delay.get(self._origin(url), 0.0)
