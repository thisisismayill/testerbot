"""A miniature link graph — the atomic unit of what Ahrefs sells.

As the crawler visits pages it feeds every hyperlink here as an *edge*
(source page -> target). Afterwards we compute:

  * internal PageRank  — the same power-iteration Google/Ahrefs use, run over
    the site's own pages, to find the most 'important' page by link structure;
  * outbound domain graph — which external domains this site links to, how
    often, and with what anchor text (a real backlink dataset, seen from the
    other side);
  * inbound internal links — which pages the site itself points at most.

Everything is exported as a raw edge list (JSON + CSV) so it is a genuine,
inspectable dataset, not just a chart.
"""
from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from typing import Any, Dict, List, Tuple

from .urls import normalise, registrable, same_scope, path_of


class LinkGraph:
    def __init__(self, base_url: str, allow_subdomains: bool = False) -> None:
        self.base_url = base_url
        self.allow_subdomains = allow_subdomains
        self.base_domain = registrable(base_url.split("//")[-1].split("/")[0])
        # edges: list of dicts (source, target, anchor, internal, nofollow)
        self.edges: List[Dict[str, Any]] = []
        self.pages: set = set()             # internal pages actually visited
        self._seen_edge: set = set()        # dedupe identical (src,dst) pairs

    # ------------------------------------------------------------------
    def note_page(self, url: str) -> None:
        n = normalise(url)
        if n:
            self.pages.add(n)

    def add_link(self, source: str, target_raw: str, anchor: str = "",
                 rel: str = "") -> None:
        source = normalise(source) or source
        target = normalise(target_raw, source)
        if not target:
            return
        internal = same_scope(target, self.base_url, self.allow_subdomains)
        nofollow = "nofollow" in (rel or "")
        key = (source, target)
        if key in self._seen_edge:
            return
        self._seen_edge.add(key)
        self.edges.append({
            "source": source,
            "target": target,
            "anchor": (anchor or "").strip()[:120],
            "internal": internal,
            "nofollow": nofollow,
        })

    # ------------------------------------------------------------------
    def _internal_pagerank(self, damping: float = 0.85,
                           iterations: int = 40) -> Dict[str, float]:
        """Power-iteration PageRank over the internal page graph."""
        # build adjacency among pages we actually fetched (both ends internal)
        nodes = set(self.pages)
        out_links: Dict[str, List[str]] = defaultdict(list)
        for e in self.edges:
            if not e["internal"] or e["nofollow"]:
                continue
            s, t = e["source"], e["target"]
            if s in nodes and t in nodes and s != t:
                out_links[s].append(t)
        if not nodes:
            return {}
        N = len(nodes)
        rank = {n: 1.0 / N for n in nodes}
        dangling = [n for n in nodes if not out_links.get(n)]
        for _ in range(iterations):
            new = {n: (1.0 - damping) / N for n in nodes}
            # distribute dangling mass evenly
            dmass = damping * sum(rank[n] for n in dangling) / N
            for n in nodes:
                new[n] += dmass
            for s, targets in out_links.items():
                share = damping * rank[s] / len(targets)
                for t in targets:
                    new[t] += share
            rank = new
        # normalise to 0..100 for a friendly score
        if rank:
            mx = max(rank.values()) or 1.0
            rank = {n: round(v / mx * 100, 1) for n, v in rank.items()}
        return rank

    # ------------------------------------------------------------------
    def analyse(self) -> Dict[str, Any]:
        internal_edges = [e for e in self.edges if e["internal"]]
        external_edges = [e for e in self.edges if not e["internal"]]

        # inbound internal links per page
        inbound: Dict[str, int] = defaultdict(int)
        for e in internal_edges:
            if not e["nofollow"]:
                inbound[e["target"]] += 1

        pr = self._internal_pagerank()
        top_pages = sorted(
            self.pages,
            key=lambda p: (pr.get(p, 0), inbound.get(p, 0)),
            reverse=True,
        )
        top_pages_out = [{
            "url": p,
            "path": path_of(p),
            "pagerank": pr.get(p, 0),
            "inbound_internal": inbound.get(p, 0),
        } for p in top_pages[:25]]

        # outbound external domains
        dom_edges: Dict[str, Dict[str, Any]] = {}
        for e in external_edges:
            dom = registrable(e["target"].split("//")[-1].split("/")[0])
            d = dom_edges.setdefault(dom, {"domain": dom, "links": 0,
                                           "from_pages": set(), "nofollow": 0,
                                           "anchors": []})
            d["links"] += 1
            d["from_pages"].add(e["source"])
            if e["nofollow"]:
                d["nofollow"] += 1
            if e["anchor"] and len(d["anchors"]) < 5:
                d["anchors"].append(e["anchor"])
        outbound = sorted(
            ({"domain": d["domain"], "links": d["links"],
              "from_pages": len(d["from_pages"]), "nofollow": d["nofollow"],
              "anchors": d["anchors"]} for d in dom_edges.values()),
            key=lambda d: d["links"], reverse=True)

        # anchor-text distribution (internal + external)
        anchors: Dict[str, int] = defaultdict(int)
        for e in self.edges:
            a = e["anchor"].lower().strip()
            if a:
                anchors[a] += 1
        top_anchors = sorted(anchors.items(), key=lambda kv: kv[1],
                             reverse=True)[:20]

        return {
            "base_domain": self.base_domain,
            "stats": {
                "pages": len(self.pages),
                "edges": len(self.edges),
                "internal_edges": len(internal_edges),
                "external_edges": len(external_edges),
                "external_domains": len(dom_edges),
                "nofollow_edges": sum(1 for e in self.edges if e["nofollow"]),
            },
            "top_pages": top_pages_out,
            "outbound_domains": outbound[:40],
            "top_anchors": [{"text": t, "count": c} for t, c in top_anchors],
        }

    # ------------------------------------------------------------------
    def export(self, out_dir: str) -> Dict[str, str]:
        """Write the raw edge list so it's a real, inspectable dataset."""
        os.makedirs(out_dir, exist_ok=True)
        analysis = self.analyse()
        json_path = os.path.join(out_dir, "linkgraph.json")
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump({"analysis": analysis, "edges": self.edges}, fh,
                      indent=2, ensure_ascii=False)
        csv_path = os.path.join(out_dir, "linkgraph-edges.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["source", "target", "anchor", "internal", "nofollow"])
            for e in self.edges:
                w.writerow([e["source"], e["target"], e["anchor"],
                            e["internal"], e["nofollow"]])
        return {"json": json_path, "csv": csv_path, "analysis": analysis}
