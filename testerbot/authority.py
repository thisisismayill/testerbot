"""Our own Domain Authority — computed, not rented.

Runs weighted PageRank over the domain-level backlink graph accumulated in the
index store, then log-scales it to a 0-100 score (the way Moz's DA and Ahrefs'
DR are log-scaled, because link popularity is power-law distributed).

No API key, no third party: this authority is derived entirely from links we
crawled ourselves. At small scale it is a real, working authority metric; the
only thing separating it from Ahrefs' is how much of the web we have crawled.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Tuple


def pagerank(edges: List[Tuple[str, str, int]], damping: float = 0.85,
             iterations: int = 60, tol: float = 1e-9) -> Dict[str, float]:
    """Weighted PageRank over domain->domain edges (source, target, weight)."""
    nodes = set()
    out_w: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
    out_total: Dict[str, int] = defaultdict(int)
    for s, t, w in edges:
        if s == t:
            continue
        nodes.add(s)
        nodes.add(t)
        out_w[s].append((t, w))
        out_total[s] += w
    if not nodes:
        return {}
    N = len(nodes)
    rank = {n: 1.0 / N for n in nodes}
    dangling = [n for n in nodes if out_total.get(n, 0) == 0]
    for _ in range(iterations):
        new = {n: (1.0 - damping) / N for n in nodes}
        dmass = damping * sum(rank[n] for n in dangling) / N
        for n in nodes:
            new[n] += dmass
        for s, targets in out_w.items():
            tot = out_total[s]
            if tot <= 0:
                continue
            base = damping * rank[s] / tot
            for t, w in targets:
                new[t] += base * w
        diff = sum(abs(new[n] - rank[n]) for n in nodes)
        rank = new
        if diff < tol:
            break
    return rank


def _lognorm(vals: Dict[str, float]) -> Dict[str, float]:
    """Log-scale a dict of positive values into 0..1."""
    if not vals:
        return {}
    logs = {k: math.log10(max(v, 1e-12)) for k, v in vals.items()}
    lo, hi = min(logs.values()), max(logs.values())
    if hi - lo < 1e-9:
        return {k: 1.0 for k in vals}
    return {k: (v - lo) / (hi - lo) for k, v in logs.items()}


def build_leaderboard(store) -> Dict[str, Any]:
    """Domain Authority over the current index.

    Blends two signals the way real DA/DR metrics do, so the score is robust on
    small graphs and matches intuition (the domain everyone links to wins):

      * PageRank over the domain graph  — link *quality* / authority flow;
      * referring-domain breadth        — how many distinct domains vouch for it.

    Both are log-scaled (link popularity is power-law) then blended and mapped
    to 1..100.
    """
    dom_edges = store.domain_edges(follow_only=True)
    pr = pagerank(dom_edges)
    counts = store.domain_counts()
    # breadth signal uses FOLLOW-only referring domains (nofollow passes no authority)
    follow_refdoms = {}
    for _s, t, _w in dom_edges:
        follow_refdoms[t] = follow_refdoms.get(t, 0) + 1
    crawled = set(
        r[0] for r in store.db.execute(
            "SELECT domain FROM domains WHERE crawled=1").fetchall())

    domains = set(pr) | set(counts) | set(store.all_domains())

    # signal 1: PageRank (only defined for domains in the graph)
    pr_norm = _lognorm({d: pr[d] for d in pr if pr[d] > 0})
    # signal 2: referring-domain breadth
    rd_raw = {d: 1 + follow_refdoms.get(d, 0) for d in domains}
    rd_norm = _lognorm(rd_raw)

    W_PR, W_RD = 0.55, 0.45
    blended: Dict[str, float] = {}
    for d in domains:
        blended[d] = W_PR * pr_norm.get(d, 0.0) + W_RD * rd_norm.get(d, 0.0)

    # map blended 0..1 to 1..100
    if blended:
        mx = max(blended.values()) or 1.0
        scores = {d: max(1, round(100 * v / mx)) for d, v in blended.items()}
    else:
        scores = {}

    rows = []
    for d in domains:
        c = counts.get(d, {"referring_domains": 0, "backlinks": 0})
        rows.append({
            "domain": d,
            "authority": scores.get(d, 1),
            "pagerank": round(pr.get(d, 0.0), 8),
            "referring_domains": c["referring_domains"],
            "backlinks": c["backlinks"],
            "crawled": d in crawled,
        })
    rows.sort(key=lambda r: (r["authority"], r["referring_domains"], r["backlinks"]),
              reverse=True)
    return {
        "leaderboard": rows,
        "stats": store.stats(),
        "computed_over_domains": len(pr),
    }
