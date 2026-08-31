"""Offline technology detection using a Wappalyzer-style fingerprint set.

Runs entirely on the HTML, headers, cookies, scripts and meta tags that
TesterBot already collects — no network, no API key.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "techfp.json")

# harvested from the page in one JS call (see HARVEST_JS)
HARVEST_JS = r"""
() => {
  const cut = (s, n) => (s && s.length > n ? s.slice(0, n) : (s || ''));
  const scriptSrc = [], scripts = [];
  for (const s of document.scripts) {
    if (s.src) scriptSrc.push(s.src);
    else if (s.textContent) scripts.push(cut(s.textContent, 3000));
  }
  const meta = {};
  for (const m of document.querySelectorAll('meta[name],meta[property]')) {
    const k = (m.getAttribute('name') || m.getAttribute('property') || '').toLowerCase();
    if (k) meta[k] = m.getAttribute('content') || '';
  }
  const links = [];
  for (const l of document.querySelectorAll('link[rel]')) {
    links.push((l.getAttribute('href') || '') + ' ' + (l.getAttribute('rel') || ''));
  }
  // a bounded set of global JS names actually present, so `js` rules can match
  let globals = [];
  try { globals = Object.getOwnPropertyNames(window).slice(0, 4000); } catch (e) {}
  return {
    url: location.href,
    html: cut(document.documentElement.outerHTML, 120000),
    scriptSrc, scripts, meta, links,
    globals,
    cookies: document.cookie || '',
    generator: (meta['generator'] || ''),
  };
}
"""


def _rx(pattern: str) -> Optional[re.Pattern]:
    """Wappalyzer patterns: 'regex\;version:\\1\;confidence:50'. Keep the regex part."""
    if not isinstance(pattern, str):
        return None
    raw = pattern.split("\;")[0]
    if raw == "":
        raw = ".*"
    try:
        return re.compile(raw, re.I)
    except re.error:
        try:
            return re.compile(re.escape(raw), re.I)
        except re.error:
            return None


def _as_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    if isinstance(v, str):
        return [v]
    return []


class TechDetector:
    def __init__(self) -> None:
        self.ok = False
        self.techs: Dict[str, Any] = {}
        self.cats: Dict[str, str] = {}
        if os.path.exists(VENDOR):
            try:
                data = json.load(open(VENDOR, encoding="utf-8"))
                self.techs = data["technologies"]
                self.cats = data["categories"]
                self.ok = True
            except Exception:
                self.ok = False

    # ------------------------------------------------------------------
    def detect(self, harvest: Dict[str, Any], headers: Dict[str, str]) -> List[Dict[str, Any]]:
        if not self.ok or not harvest:
            return []
        headers = {k.lower(): (v or "") for k, v in (headers or {}).items()}
        html = harvest.get("html", "") or ""
        script_src = harvest.get("scriptSrc", []) or []
        scripts = harvest.get("scripts", []) or []
        meta = {k.lower(): v for k, v in (harvest.get("meta", {}) or {}).items()}
        cookies = harvest.get("cookies", "") or ""
        url = harvest.get("url", "") or ""
        globals_set = set(harvest.get("globals", []) or [])

        cookie_names = set()
        for part in cookies.split(";"):
            if "=" in part:
                cookie_names.add(part.split("=")[0].strip())

        found: Dict[str, Dict[str, Any]] = {}

        def hit(name: str) -> None:
            if name in found or name not in self.techs:
                return
            spec = self.techs[name]
            found[name] = {
                "name": name,
                "categories": [self.cats.get(str(cid), "") for cid in spec.get("cats", [])],
            }
            for imp in _as_list(spec.get("implies", [])):
                dep = imp.split("\;")[0]
                if dep and dep != name:
                    hit(dep)

        for name, spec in self.techs.items():
            if name in found:
                continue
            matched = False

            # headers
            for hk, pat in (spec.get("headers") or {}).items():
                val = headers.get(hk.lower())
                if val is not None:
                    rx = _rx(pat)
                    if rx and rx.search(val):
                        matched = True
                        break
            # cookies
            if not matched:
                for ck, pat in (spec.get("cookies") or {}).items():
                    if ck in cookie_names:
                        rx = _rx(pat)
                        val = ""
                        m = re.search(re.escape(ck) + r"=([^;]*)", cookies)
                        if m:
                            val = m.group(1)
                        if pat in ("", None) or (rx and rx.search(val)) or rx is None:
                            matched = True
                            break
            # scriptSrc
            if not matched:
                for pat in _as_list(spec.get("scriptSrc")):
                    rx = _rx(pat)
                    if rx and any(rx.search(s) for s in script_src):
                        matched = True
                        break
            # inline scripts
            if not matched:
                for pat in _as_list(spec.get("scripts")):
                    rx = _rx(pat)
                    if rx and any(rx.search(s) for s in scripts):
                        matched = True
                        break
            # meta
            if not matched:
                for mk, pat in (spec.get("meta") or {}).items():
                    val = meta.get(mk.lower())
                    if val is not None:
                        rx = _rx(pat)
                        if rx and rx.search(val):
                            matched = True
                            break
            # js globals — only single-segment, distinctive names, to avoid
            # firing every jQuery plugin off the bare `jQuery` global
            if not matched:
                for jk in (spec.get("js") or {}).keys():
                    if re.search(r"[.\[\]]", jk):
                        continue
                    if len(jk) >= 4 and jk in globals_set:
                        matched = True
                        break
            # url
            if not matched:
                for pat in _as_list(spec.get("url")):
                    rx = _rx(pat)
                    if rx and rx.search(url):
                        matched = True
                        break
            # html (do this last — most expensive)
            if not matched:
                for pat in _as_list(spec.get("html")):
                    rx = _rx(pat)
                    if rx and rx.search(html):
                        matched = True
                        break

            if matched:
                hit(name)

        # group by category for a tidy result
        out = list(found.values())
        out.sort(key=lambda t: (t["categories"][0] if t["categories"] else "zzz", t["name"]))
        return out


def group_by_category(techs: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {}
    for t in techs:
        cat = t["categories"][0] if t.get("categories") else "Other"
        groups.setdefault(cat, [])
        if t["name"] not in groups[cat]:
            groups[cat].append(t["name"])
    return groups
