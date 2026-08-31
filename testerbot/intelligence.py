"""Site-level intelligence: authority, performance, tech stack, hosting.

Everything here degrades gracefully. Tech detection and hosting facts work
with zero configuration. Authority (OpenPageRank) and performance
(PageSpeed Insights) activate when the user supplies a free API key; without
one they return a clear 'not configured' note instead of failing the run.
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .techdetect import HARVEST_JS, TechDetector, group_by_category

OPR_ENDPOINT = "https://openpagerank.com/api/v1.0/getPageRank"
PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def _get_json(url: str, headers: Optional[Dict[str, str]] = None,
              timeout: int = 25) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


# ----------------------------------------------------------------- authority
def domain_authority(domain: str, api_key: str) -> Dict[str, Any]:
    """OpenPageRank: free 0–10 domain authority. Key from openpagerank.com."""
    if not api_key:
        return {"available": False,
                "reason": "No OpenPageRank key set (free at openpagerank.com)."}
    q = urllib.parse.urlencode({"domains[0]": domain})
    data = _get_json(f"{OPR_ENDPOINT}?{q}", headers={"API-OPR": api_key})
    if not data or "response" not in data:
        return {"available": False, "reason": "OpenPageRank did not respond."}
    try:
        row = data["response"][0]
        if row.get("status_code") != 200:
            return {"available": True, "found": False, "domain": domain,
                    "note": "This domain was not found in the OpenPageRank index."}
        return {
            "available": True, "found": True, "domain": domain,
            "score": round(float(row.get("page_rank_decimal") or 0), 2),
            "score_max": 10,
            "rank": row.get("rank"),
        }
    except Exception:
        return {"available": False, "reason": "The OpenPageRank response could not be read."}


# ----------------------------------------------------------------- performance
def performance(url: str, api_key: str = "", strategy: str = "mobile") -> Dict[str, Any]:
    """PageSpeed Insights: real-user (CrUX) + lab performance. Key optional
    (keyless works at low volume; a free Google API key raises the limit)."""
    params = {"url": url, "strategy": strategy,
              "category": "performance"}
    if api_key:
        params["key"] = api_key
    q = urllib.parse.urlencode(params)
    data = _get_json(f"{PSI_ENDPOINT}?{q}", timeout=60)
    if not data:
        return {"available": False,
                "reason": "PageSpeed Insights did not respond "
                          "(adding a key raises the limit: Google Cloud → PageSpeed API)."}
    if "error" in data:
        msg = data["error"].get("message", "")[:160]
        return {"available": False, "reason": f"PageSpeed error: {msg}"}
    out: Dict[str, Any] = {"available": True, "strategy": strategy, "url": url}

    # lab score
    try:
        lh = data["lighthouseResult"]
        score = lh["categories"]["performance"]["score"]
        out["lab_score"] = round(score * 100) if score is not None else None
        audits = lh.get("audits", {})
        for key, label in (("largest-contentful-paint", "lcp"),
                           ("cumulative-layout-shift", "cls"),
                           ("total-blocking-time", "tbt"),
                           ("first-contentful-paint", "fcp"),
                           ("speed-index", "si"),
                           ("interactive", "tti")):
            a = audits.get(key, {})
            if a.get("displayValue"):
                out.setdefault("lab", {})[label] = a["displayValue"]
    except Exception:
        pass

    # field (real-user, CrUX)
    try:
        loe = data.get("loadingExperience", {})
        metrics = loe.get("metrics", {})
        field: Dict[str, Any] = {}
        names = {"LARGEST_CONTENTFUL_PAINT_MS": "lcp_ms",
                 "INTERACTION_TO_NEXT_PAINT": "inp_ms",
                 "CUMULATIVE_LAYOUT_SHIFT_SCORE": "cls",
                 "FIRST_CONTENTFUL_PAINT_MS": "fcp_ms",
                 "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "ttfb_ms"}
        for k, short in names.items():
            if k in metrics:
                field[short] = {"p75": metrics[k].get("percentile"),
                                "category": metrics[k].get("category")}
        if loe.get("overall_category"):
            field["overall"] = loe["overall_category"]
        if field:
            out["field"] = field
            out["has_field_data"] = "overall" in field
    except Exception:
        pass
    return out


# ----------------------------------------------------------------- hosting
def hosting_facts(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Server, CDN, IP, protocol — from data we already have, plus a DNS lookup."""
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    host = urlparse(url).netloc.split(":")[0]
    facts: Dict[str, Any] = {"host": host, "scheme": urlparse(url).scheme}
    if headers.get("server"):
        facts["server"] = headers["server"]
    if headers.get("x-powered-by"):
        facts["powered_by"] = headers["x-powered-by"]
    # CDN hints
    cdn = None
    hdr_blob = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
    for needle, label in (("cloudflare", "Cloudflare"), ("cf-ray", "Cloudflare"),
                          ("x-amz-cf", "Amazon CloudFront"), ("cloudfront", "Amazon CloudFront"),
                          ("x-vercel", "Vercel"), ("x-fastly", "Fastly"),
                          ("x-akamai", "Akamai"), ("x-cache", "CDN (x-cache)"),
                          ("netlify", "Netlify")):
        if needle in hdr_blob:
            cdn = label
            break
    if cdn:
        facts["cdn"] = cdn
    try:
        facts["ip"] = socket.gethostbyname(host)
    except Exception:
        pass
    return facts


# ----------------------------------------------------------------- orchestration
class Intelligence:
    def __init__(self, opr_key: str = "", psi_key: str = "",
                 run_performance: bool = True) -> None:
        self.opr_key = opr_key
        self.psi_key = psi_key
        self.run_performance = run_performance
        self.detector = TechDetector()

    def harvest_page(self, page) -> Dict[str, Any]:
        try:
            return page.evaluate(HARVEST_JS)
        except Exception:
            return {}

    def gather(self, url: str, harvest: Dict[str, Any],
               headers: Dict[str, str]) -> Dict[str, Any]:
        domain = urlparse(url).netloc.split(":")[0]
        techs = self.detector.detect(harvest, headers) if harvest else []
        result: Dict[str, Any] = {
            "url": url,
            "domain": domain,
            "hosting": hosting_facts(url, headers),
            "tech": {
                "available": self.detector.ok,
                "count": len(techs),
                "items": techs,
                "by_category": group_by_category(techs),
            },
            "authority": domain_authority(domain, self.opr_key),
        }
        if self.run_performance:
            result["performance"] = performance(url, self.psi_key, "mobile")
        else:
            result["performance"] = {"available": False,
                                     "reason": "The performance check is turned off."}
        return result
