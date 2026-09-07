"""A persistent, growing link index — the data warehouse.

Every crawl feeds hyperlink edges here; they accumulate across runs in a local
SQLite file. Re-crawling a page refreshes 'last_seen' instead of duplicating,
so the index gets more complete and more current over time — exactly how a real
link-intelligence product's data behaves, at a scale one machine can hold.

Domain-level edges (domain A -> domain B) are the backlink graph; that is what
authority.py runs PageRank over to produce our own Domain Authority score.
"""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .urls import normalise, registrable, UTILITY_DOMAINS

SCHEMA = """
CREATE TABLE IF NOT EXISTS domains (
    domain      TEXT PRIMARY KEY,
    first_seen  INTEGER,
    last_seen   INTEGER,
    crawled     INTEGER DEFAULT 0,     -- 1 only if we actually fetched pages from it
    attempts    INTEGER DEFAULT 0,     -- failed tries; a domain we could not reach is
    last_error  TEXT,                  -- not finished, it is owed another attempt
    offtopic    INTEGER DEFAULT 0      -- looked at once, not about this subject
);
CREATE TABLE IF NOT EXISTS pages (
    url         TEXT PRIMARY KEY,
    domain      TEXT,
    first_seen  INTEGER,
    last_seen   INTEGER
);
CREATE TABLE IF NOT EXISTS edges (
    source_url   TEXT,
    target_url   TEXT,
    source_domain TEXT,
    target_domain TEXT,
    anchor       TEXT,
    internal     INTEGER,
    nofollow     INTEGER,
    first_seen   INTEGER,
    last_seen    INTEGER,
    PRIMARY KEY (source_url, target_url)
);
CREATE INDEX IF NOT EXISTS idx_edges_targetdom ON edges(target_domain);
CREATE INDEX IF NOT EXISTS idx_edges_sourcedom ON edges(source_domain);
CREATE INDEX IF NOT EXISTS idx_edges_internal  ON edges(internal);
CREATE INDEX IF NOT EXISTS idx_pages_domain    ON pages(domain);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _dom(url: str) -> str:
    netloc = url.split("//")[-1].split("/")[0]
    return registrable(netloc)


class IndexStore:
    def __init__(self, path: str = "testerbot-index.db") -> None:
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        # databases created before failure tracking existed
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(domains)")}
        for col, ddl in (("attempts", "ALTER TABLE domains ADD COLUMN attempts INTEGER DEFAULT 0"),
                         ("last_error", "ALTER TABLE domains ADD COLUMN last_error TEXT"),
                         ("offtopic", "ALTER TABLE domains ADD COLUMN offtopic INTEGER DEFAULT 0")):
            if col not in cols:
                self.db.execute(ddl)
        self.db.commit()

    # ------------------------------------------------------------------ writes
    def mark_crawled(self, domain: str, now: Optional[int] = None) -> None:
        now = now or int(time.time())
        self.db.execute(
            "INSERT INTO domains(domain,first_seen,last_seen,crawled) VALUES(?,?,?,1) "
            "ON CONFLICT(domain) DO UPDATE SET last_seen=?, crawled=1",
            (domain, now, now, now))
        self.db.commit()

    MAX_ATTEMPTS = 3   # after this many failures a domain stops using crawl budget

    def mark_failed(self, domain: str, error: str = "",
                    now: Optional[int] = None) -> int:
        """Record that a domain could not be crawled, and return the attempt count.

        Marking a failure as 'crawled' would quietly retire the domain: the
        frontier would never offer it again and the index would be missing it
        forever, with nothing in the output to say so. A domain we could not
        reach is unfinished, not done.
        """
        now = now or int(time.time())
        self.db.execute(
            "INSERT INTO domains(domain,first_seen,last_seen,crawled,attempts,last_error) "
            "VALUES(?,?,?,0,1,?) "
            "ON CONFLICT(domain) DO UPDATE SET last_seen=?, "
            "attempts=COALESCE(attempts,0)+1, last_error=?",
            (domain, now, now, error[:300], now, error[:300]))
        self.db.commit()
        row = self.db.execute("SELECT attempts FROM domains WHERE domain=?",
                              (domain,)).fetchone()
        return row[0] if row else 1

    def mark_offtopic(self, domain: str, now: Optional[int] = None) -> None:
        """This domain was reached and is not about the subject.

        Unlike a failure it is not owed another attempt - we looked, and the
        answer will not change - so it leaves the frontier for good and stops
        costing crawl budget. It stays in the graph: it is still a real link
        target, just not somewhere this index goes deeper.
        """
        now = now or int(time.time())
        self.db.execute(
            "INSERT INTO domains(domain,first_seen,last_seen,crawled,offtopic) "
            "VALUES(?,?,?,0,1) "
            "ON CONFLICT(domain) DO UPDATE SET last_seen=?, offtopic=1",
            (domain, now, now, now))
        self.db.commit()

    def _touch_domain(self, domain: str, now: int) -> None:
        self.db.execute(
            "INSERT INTO domains(domain,first_seen,last_seen) VALUES(?,?,?) "
            "ON CONFLICT(domain) DO UPDATE SET last_seen=?",
            (domain, now, now, now))

    def _touch_page(self, url: str, domain: str, now: int) -> None:
        self.db.execute(
            "INSERT INTO pages(url,domain,first_seen,last_seen) VALUES(?,?,?,?) "
            "ON CONFLICT(url) DO UPDATE SET last_seen=?",
            (url, domain, now, now, now))

    def add_edges(self, edges: Iterable[Dict[str, Any]],
                  now: Optional[int] = None) -> int:
        """Bulk-insert edges from a LinkGraph. Returns number of NEW edges."""
        now = now or int(time.time())
        cur = self.db.cursor()
        new = 0
        for e in edges:
            src = e.get("source")
            tgt = e.get("target")
            if not src or not tgt:
                continue
            sdom, tdom = _dom(src), _dom(tgt)
            self._touch_domain(sdom, now)
            self._touch_domain(tdom, now)
            self._touch_page(src, sdom, now)
            row = cur.execute(
                "SELECT 1 FROM edges WHERE source_url=? AND target_url=?",
                (src, tgt)).fetchone()
            if row:
                cur.execute(
                    "UPDATE edges SET last_seen=?, anchor=?, nofollow=? "
                    "WHERE source_url=? AND target_url=?",
                    (now, e.get("anchor", "")[:200], int(bool(e.get("nofollow"))),
                     src, tgt))
            else:
                new += 1
                cur.execute(
                    "INSERT INTO edges(source_url,target_url,source_domain,target_domain,"
                    "anchor,internal,nofollow,first_seen,last_seen) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (src, tgt, sdom, tdom, e.get("anchor", "")[:200],
                     int(bool(e.get("internal"))), int(bool(e.get("nofollow"))),
                     now, now))
        self.db.commit()
        return new

    # Domains that are almost never worth crawling for a link index: they link
    # out to everything, so they add noise and eat the whole crawl budget.
    # The same list the leaderboard hides, used here to keep the crawl
    # budget off domains that link out to everything.
    SKIP_DOMAINS = set(UTILITY_DOMAINS)

    def frontier(self, limit: int = 20, min_referring: int = 1,
                 skip: Optional[Iterable[str]] = None
                 ) -> List[Tuple[str, int, str, str]]:
        """Domains the index has seen linked to but has never crawled.

        Ranked by how many distinct domains link to them, so the most
        referenced - and so most likely to matter - come first. This is what
        turns a one-off crawl into an index that keeps growing: each run
        crawls part of the frontier, which reveals a new frontier.
        """
        blocked = set(self.SKIP_DOMAINS)
        if skip:
            blocked |= {s.strip().lower() for s in skip if s.strip()}
        # MIN(target_url) gives a real address we have actually seen linked to,
        # so the crawl keeps the scheme (and port) the link used instead of
        # guessing https:// and failing on an http-only host.
        rows = self.db.execute(
            "SELECT e.target_domain, COUNT(DISTINCT e.source_domain) AS refdoms, "
            "MIN(e.target_url), GROUP_CONCAT(e.anchor, ' | ') "
            "FROM edges e JOIN domains d ON d.domain = e.target_domain "
            "WHERE e.internal = 0 AND d.crawled = 0 AND e.target_domain != '' "
            "AND COALESCE(d.attempts,0) < ? AND COALESCE(d.offtopic,0) = 0 "
            "GROUP BY e.target_domain HAVING refdoms >= ? "
            "ORDER BY refdoms DESC, e.target_domain LIMIT ?",
            (self.MAX_ATTEMPTS, min_referring, limit + len(blocked))).fetchall()
        out = [(d, n, u, a or "") for d, n, u, a in rows if d not in blocked]
        return out[:limit]

    def frontier_size(self, min_referring: int = 1) -> int:
        """How many uncrawled domains are waiting, in total."""
        row = self.db.execute(
            "SELECT COUNT(*) FROM (SELECT e.target_domain "
            "FROM edges e JOIN domains d ON d.domain = e.target_domain "
            "WHERE e.internal = 0 AND d.crawled = 0 AND e.target_domain != '' "
            "AND COALESCE(d.attempts,0) < ? AND COALESCE(d.offtopic,0) = 0 "
            "GROUP BY e.target_domain HAVING COUNT(DISTINCT e.source_domain) >= ?)",
            (self.MAX_ATTEMPTS, min_referring)).fetchone()
        return row[0] if row else 0

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))
        self.db.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    # ------------------------------------------------------------------ reads
    def domain_edges(self, follow_only: bool = True) -> List[Tuple[str, str, int]]:
        """Aggregated domain->domain edges (external only) with weight =
        number of distinct source pages linking across the domain boundary."""
        q = ("SELECT source_domain, target_domain, COUNT(DISTINCT source_url) "
             "FROM edges WHERE internal=0 AND source_domain<>target_domain ")
        if follow_only:
            q += "AND nofollow=0 "
        q += "GROUP BY source_domain, target_domain"
        return [(r[0], r[1], r[2]) for r in self.db.execute(q).fetchall()]

    def all_domains(self) -> List[str]:
        return [r[0] for r in self.db.execute("SELECT domain FROM domains").fetchall()]

    def backlinks(self, domain: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Referring pages that link to any page on `domain` (the Ahrefs core view)."""
        rows = self.db.execute(
            "SELECT source_url, source_domain, target_url, anchor, nofollow, last_seen "
            "FROM edges WHERE target_domain=? AND source_domain<>target_domain "
            "ORDER BY nofollow ASC, last_seen DESC LIMIT ?",
            (domain, limit)).fetchall()
        return [{"from_url": r[0], "from_domain": r[1], "to_url": r[2],
                 "anchor": r[3], "nofollow": bool(r[4]), "last_seen": r[5]} for r in rows]

    def referring_domains(self, domain: str) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            "SELECT source_domain, COUNT(DISTINCT source_url) links, "
            "MAX(nofollow=0) has_follow "
            "FROM edges WHERE target_domain=? AND source_domain<>target_domain "
            "GROUP BY source_domain ORDER BY links DESC", (domain,)).fetchall()
        return [{"domain": r[0], "links": r[1], "follow": bool(r[2])} for r in rows]

    def outbound_domains(self, domain: str) -> List[Dict[str, Any]]:
        rows = self.db.execute(
            "SELECT target_domain, COUNT(DISTINCT source_url) links "
            "FROM edges WHERE source_domain=? AND source_domain<>target_domain "
            "GROUP BY target_domain ORDER BY links DESC", (domain,)).fetchall()
        return [{"domain": r[0], "links": r[1]} for r in rows]

    def stats(self) -> Dict[str, int]:
        g = self.db.execute
        return {
            "domains": g("SELECT COUNT(*) FROM domains").fetchone()[0],
            "crawled_domains": g("SELECT COUNT(*) FROM domains WHERE crawled=1").fetchone()[0],
            "pages": g("SELECT COUNT(*) FROM pages").fetchone()[0],
            "edges": g("SELECT COUNT(*) FROM edges").fetchone()[0],
            "cross_domain_edges": g(
                "SELECT COUNT(*) FROM edges WHERE source_domain<>target_domain").fetchone()[0],
        }

    def domain_counts(self) -> Dict[str, Dict[str, int]]:
        """Per-domain referring-domain and backlink counts, for the leaderboard."""
        out: Dict[str, Dict[str, int]] = {}
        for r in self.db.execute(
            "SELECT target_domain, COUNT(DISTINCT source_domain) refdoms, "
            "COUNT(*) backlinks FROM edges "
            "WHERE source_domain<>target_domain GROUP BY target_domain").fetchall():
            out[r[0]] = {"referring_domains": r[1], "backlinks": r[2]}
        return out

    def close(self) -> None:
        try:
            self.db.close()
        except Exception:
            pass
