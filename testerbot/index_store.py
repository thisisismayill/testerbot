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

from .urls import normalise, registrable

SCHEMA = """
CREATE TABLE IF NOT EXISTS domains (
    domain      TEXT PRIMARY KEY,
    first_seen  INTEGER,
    last_seen   INTEGER,
    crawled     INTEGER DEFAULT 0      -- 1 if we actually fetched this domain's pages
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
        self.db.commit()

    # ------------------------------------------------------------------ writes
    def mark_crawled(self, domain: str, now: Optional[int] = None) -> None:
        now = now or int(time.time())
        self.db.execute(
            "INSERT INTO domains(domain,first_seen,last_seen,crawled) VALUES(?,?,?,1) "
            "ON CONFLICT(domain) DO UPDATE SET last_seen=?, crawled=1",
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
