"""The orchestrator: crawl, audit, interact, collect."""
from __future__ import annotations

import os
import re
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from playwright.sync_api import sync_playwright

from . import a11y, audits, auth, site
from .intelligence import Intelligence
from .linkgraph import LinkGraph
from .config import Config
from .dom_probe import DOM_PROBE
from .interact import WIDE_ELEMENTS_JS, click_everything, test_forms
from .models import Finding, PageResult, SEVERITY_WEIGHT
from .recorder import Recorder
from .urls import (is_asset, is_document, normalise, origin, same_scope, shorten)

TIMING_JS = """
() => {
  const nav = performance.getEntriesByType('navigation')[0];
  if (!nav) {
    const t = performance.timing;
    if (!t || !t.navigationStart) return {};
    return { load_ms: t.loadEventEnd - t.navigationStart,
             dom_ready_ms: t.domContentLoadedEventEnd - t.navigationStart,
             ttfb_ms: t.responseStart - t.navigationStart };
  }
  return { load_ms: Math.round(nav.loadEventEnd || nav.duration),
           dom_ready_ms: Math.round(nav.domContentLoadedEventEnd),
           ttfb_ms: Math.round(nav.responseStart),
           transfer_kb: Math.round((nav.transferSize || 0) / 1024) };
}
"""

MAX_SCREENSHOTS = 220


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "shot").lower()).strip("-")[:40] or "shot"


class TesterBot:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.base_url = normalise(cfg.url) or cfg.url
        self.findings: List[Finding] = []
        self.pages: List[PageResult] = []
        self.links: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"sources": set(), "text": ""})
        self.tested_controls: Set[str] = set()
        self.tested_forms: Set[str] = set()
        self.shots = 0
        self.started = time.time()
        self.logged_in = False
        self.login_note = ""
        self.page = None
        self.out_dir = os.path.abspath(cfg.out_dir)
        self.shot_dir = os.path.join(self.out_dir, "screenshots")
        self.include_re = [re.compile(p, re.I) for p in cfg.include]
        self.exclude_re = [re.compile(p, re.I) for p in cfg.exclude]
        self.skip_re = cfg.skip_url_re()
        self.intel = (Intelligence(opr_key=cfg.opr_key, psi_key=cfg.psi_key,
                                   run_performance=cfg.run_performance)
                      if cfg.run_intelligence else None)
        self.intelligence: dict = {}
        self.linkgraph = LinkGraph(self.base_url, cfg.allow_subdomains)
        self.link_analysis: dict = {}

    # ------------------------------------------------------------- utils
    def log(self, msg: str) -> None:
        if not self.cfg.quiet:
            print(msg, flush=True)

    def add(self, findings: List[Finding]) -> None:
        self.findings.extend(findings)

    def shot(self, tag: str, full: bool = False) -> Optional[str]:
        if self.shots >= MAX_SCREENSHOTS or self.page is None:
            return None
        name = f"{self.shots:03d}-{slug(tag)}.png"
        path = os.path.join(self.shot_dir, name)
        try:
            self.page.screenshot(path=path, full_page=full, timeout=12000)
        except Exception:
            return None
        self.shots += 1
        return "screenshots/" + name

    def _shot_factory(self):
        return lambda tag: self.shot(tag)

    # ------------------------------------------------------------- crawl gate
    def should_visit(self, url: str) -> Optional[str]:
        if not same_scope(url, self.base_url, self.cfg.allow_subdomains):
            return "external"
        if is_asset(url) and not is_document(url):
            return "asset"
        if is_document(url):
            return "document"
        if self.skip_re.search(url):
            return "unsafe/destructive URL"
        if self.exclude_re and any(r.search(url) for r in self.exclude_re):
            return "excluded by --exclude"
        if self.include_re and not any(r.search(url) for r in self.include_re):
            return "not matched by --include"
        return None

    # ------------------------------------------------------------- main
    def run(self) -> Dict[str, Any]:
        os.makedirs(self.shot_dir, exist_ok=True)
        cfg = self.cfg
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=cfg.headless, slow_mo=cfg.slow_mo,
                                         args=["--disable-dev-shm-usage"])
            ctx_args: Dict[str, Any] = {
                "viewport": {"width": cfg.viewport_width, "height": cfg.viewport_height},
                "locale": cfg.locale,
                "ignore_https_errors": cfg.ignore_https_errors,
                "accept_downloads": False,
            }
            if cfg.user_agent:
                ctx_args["user_agent"] = cfg.user_agent
            if cfg.storage_state and os.path.exists(cfg.storage_state):
                ctx_args["storage_state"] = cfg.storage_state
                self.log(f"→ reusing saved session from {cfg.storage_state}")
            context = browser.new_context(**ctx_args)
            context.set_default_timeout(cfg.timeout_ms)
            context.set_default_navigation_timeout(cfg.nav_timeout_ms)

            rec = Recorder()
            page = context.new_page()
            rec.attach(page)
            rec.attach_context(context)   # after the main page exists
            self.page = page
            self.rec = rec
            request = context.request

            # ---------- site-level checks
            self.log("→ site-level checks (HTTPS, 404, robots, sitemap)")
            # If the site turns us away, every "X is missing" check below would
            # only be measuring the refusal. Say so once, then stop claiming
            # things are absent when we were never allowed to look.
            blocked, block_findings = site.check_reachable(request, self.base_url)
            self.add(block_findings)
            if blocked:
                self.log("   ⚠ the site refused us — the checks below cannot be trusted")
            self.add(site.check_https(request, self.base_url))
            self.add(site.check_404(request, self.base_url))
            if cfg.hygiene_checks:
                self.add(site.check_hygiene(request, self.base_url, blocked=blocked))
            seeds: List[str] = []
            if cfg.use_sitemap:
                sm_urls, sm_findings = site.discover_sitemap_urls(
                    request, self.base_url, cfg, self.log, blocked=blocked)
                self.add(sm_findings)
                seeds = sm_urls[: cfg.max_pages]

            # ---------- login
            if cfg.username or cfg.password:
                self.log("→ logging in")
                ok, lf, note = auth.login(page, cfg, self.base_url)
                self.add(lf)
                self.logged_in, self.login_note = ok, note
                self.log(f"   {note}")
                if ok and cfg.save_storage_state:
                    try:
                        context.storage_state(path=cfg.save_storage_state)
                        self.log(f"   session saved to {cfg.save_storage_state}")
                    except Exception:
                        pass
            elif cfg.storage_state:
                self.logged_in = True
                self.login_note = "restored from storage state"

            # ---------- crawl
            queue: deque = deque()
            queue.append((self.base_url, 0))
            for u in cfg.extra_urls:
                n = normalise(u, self.base_url)
                if n:
                    queue.append((n, 1))
            for u in seeds:
                queue.append((u, 1))
            visited: Set[str] = set()

            while queue and len(visited) < cfg.max_pages:
                url, depth = queue.popleft()
                if url in visited or depth > cfg.max_depth:
                    continue
                reason = self.should_visit(url)
                if reason and url != self.base_url:
                    continue
                visited.add(url)
                self.log(f"[{len(visited)}/{cfg.max_pages}] depth {depth} · {shorten(url, 90)}")
                new_links = self.process_page(page, rec, url, depth,
                                              is_entry=(url == self.base_url))
                for link in new_links:
                    if link not in visited and self.should_visit(link) is None:
                        queue.append((link, depth + 1))

            # ---------- link health
            if self.links:
                self.log(f"→ checking {len(self.links)} unique links")
                self.add(site.check_links(request, self.links, self.base_url, cfg, self.log))

            self.add(site.cross_page_checks(self.pages))
            try:
                exp = self.linkgraph.export(self.out_dir)
                self.link_analysis = exp["analysis"]
                self.log(f"→ link graph: {self.link_analysis['stats']['edges']} edge, "
                         f"{self.link_analysis['stats']['external_domains']} external domains")
            except Exception as exc:
                self.link_analysis = {"error": str(exc)[:200]}
            try:
                context.close()
                browser.close()
            except Exception:
                pass

        return self.build_report()

    # ------------------------------------------------------------- one page
    def process_page(self, page, rec: Recorder, url: str, depth: int,
                     is_entry: bool) -> List[str]:
        cfg = self.cfg
        rec.reset()
        result = PageResult(url=url, depth=depth)
        found_links: List[str] = []
        before = len(self.findings)

        try:
            response = page.goto(url, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
        except Exception as exc:
            result.error = str(exc).split("\n")[0][:250]
            self.add([Finding(
                severity="high", category="HTTP Status",
                title=f"Page failed to load: {shorten(url, 60)}",
                detail=result.error, url=url,
                how_to_fix="Check the route, the server, and the response time.")])
            self.pages.append(result)
            return found_links

        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(cfg.settle_ms)

        headers: Dict[str, str] = {}
        if response is not None:
            result.status = response.status
            try:
                headers = response.headers
            except Exception:
                headers = {}
        self.add(audits.audit_http(url, result.status, headers, is_entry))
        if result.status and result.status >= 400:
            result.screenshot = self.shot(f"http-{result.status}")
            result.findings = len(self.findings) - before
            self.pages.append(result)
            return found_links

        # session lost?
        if self.logged_in and auth.is_logged_out(page) and url != cfg.login_url:
            self.log("   session appears lost - logging in again")
            ok, _lf, _n = auth.login(page, cfg, self.base_url)
            if ok:
                try:
                    page.goto(url, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
                    page.wait_for_timeout(cfg.settle_ms)
                except Exception:
                    pass

        # ---- DOM probe
        try:
            data: Dict[str, Any] = page.evaluate(DOM_PROBE)
        except Exception as exc:
            data = {}
            self.add([Finding(
                severity="low", category="Interaction",
                title="Page could not be inspected",
                detail=str(exc)[:250], url=url)])
        result.title = data.get("title", "")

        if data:
            self.add(audits.audit_dom(url, data, cfg, is_entry))

        # ---- console / network
        self.add(audits.audit_console(url, rec.console, rec.page_errors))
        self.add(audits.audit_network(url, rec.failed, rec.bad_responses()))

        # ---- performance
        try:
            timing = page.evaluate(TIMING_JS) or {}
        except Exception:
            timing = {}
        weight = rec.weight_kb() or float(timing.get("transfer_kb") or 0)
        result.load_ms = timing.get("load_ms")
        result.ttfb_ms = timing.get("ttfb_ms")
        result.dom_ready_ms = timing.get("dom_ready_ms")
        result.weight_kb = round(weight, 1)
        result.requests = len(rec.responses)
        self.add(audits.audit_performance(url, cfg, timing, weight, result.requests))

        # ---- links (+ feed the link graph)
        self.linkgraph.note_page(url)
        for link in data.get("links", []):
            n = normalise(link.get("href", ""), url)
            if not n:
                continue
            self.linkgraph.add_link(url, link.get("href", ""),
                                    link.get("text", ""), link.get("rel", ""))
            entry = self.links[n]
            entry["sources"].add(url)
            if not entry["text"]:
                entry["text"] = link.get("text", "")
            found_links.append(n)
        result.links_found = len(found_links)

        # ---- a11y
        if cfg.run_axe:
            self.add(a11y.audit(page, url))

        # ---- site intelligence (entry page only: authority/perf/tech/hosting)
        if is_entry and self.intel is not None:
            try:
                harvest = self.intel.harvest_page(page)
                self.intelligence = self.intel.gather(url, harvest, headers)
                self.log("   intelligence: "
                         f"{self.intelligence['tech']['count']} texnologiya"
                         + (f", DA {self.intelligence['authority'].get('score')}"
                            if self.intelligence['authority'].get('found') else ""))
            except Exception as exc:
                self.intelligence = {"error": str(exc)[:200]}

        # ---- responsive
        if cfg.responsive_checks:
            self.check_responsive(page, url)

        # ---- page screenshot
        if cfg.screenshot_all or len(self.findings) > before:
            result.screenshot = self.shot(f"page-{slug(url.split('/')[-1] or 'home')}", full=True)

        # ---- interactions
        if cfg.click_elements and data.get("clickables"):
            f, clicked = click_everything(page, cfg, rec, url, data["clickables"],
                                          self.tested_controls, self._shot_factory())
            self.add(f)
            result.buttons_clicked = clicked
        if data.get("forms"):
            f, n_forms = test_forms(page, cfg, rec, url, data["forms"],
                                    self.tested_forms, self._shot_factory())
            self.add(f)
            result.forms_tested = n_forms

        result.findings = len(self.findings) - before
        self.pages.append(result)
        return found_links

    # ------------------------------------------------------------- responsive
    def check_responsive(self, page, url: str) -> None:
        cfg = self.cfg
        for label, w, h in (("mobile", cfg.mobile_width, cfg.mobile_height),
                            ("tablet", cfg.tablet_width, cfg.tablet_height)):
            try:
                page.set_viewport_size({"width": w, "height": h})
                page.wait_for_timeout(450)
                metrics = page.evaluate(
                    "() => ({scrollWidth: document.documentElement.scrollWidth,"
                    " clientWidth: document.documentElement.clientWidth})")
                if metrics.get("scrollWidth", 0) > w + 4:
                    metrics["wide"] = page.evaluate(WIDE_ELEMENTS_JS, w)
                    shot = self.shot(f"{label}-overflow")
                    self.add(audits.audit_responsive(url, label, w, metrics, shot))
                elif cfg.screenshot_all and label == "mobile":
                    self.shot("mobile-view")
            except Exception:
                continue
        try:
            page.set_viewport_size({"width": cfg.viewport_width, "height": cfg.viewport_height})
            page.wait_for_timeout(250)
        except Exception:
            pass

    # ------------------------------------------------------------- report data
    def build_report(self) -> Dict[str, Any]:
        merged: Dict[str, Finding] = {}
        for f in self.findings:
            key = f.group_key
            if key in merged:
                existing = merged[key]
                existing.occurrences += f.occurrences
                if f.url and f.url not in existing.other_urls and f.url != existing.url:
                    if len(existing.other_urls) < 25:
                        existing.other_urls.append(f.url)
                if not existing.screenshot and f.screenshot:
                    existing.screenshot = f.screenshot
            else:
                merged[key] = f
        findings = sorted(merged.values(),
                          key=lambda f: (SEVERITY_WEIGHT.get(f.severity, 9),
                                         -f.occurrences, f.category))
        counts: Dict[str, int] = defaultdict(int)
        for f in findings:
            counts[f.severity] += 1
        by_category: Dict[str, int] = defaultdict(int)
        for f in findings:
            by_category[f.category] += 1

        return {
            "meta": {
                "target": self.base_url,
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "duration_s": round(time.time() - self.started, 1),
                "pages_tested": len(self.pages),
                "links_checked": len(self.links),
                "controls_clicked": sum(p.buttons_clicked for p in self.pages),
                "forms_tested": sum(p.forms_tested for p in self.pages),
                "screenshots": self.shots,
                "logged_in": self.logged_in,
                "login_note": self.login_note,
                "danger_mode": self.cfg.danger_mode,
                "config": self.cfg.to_public_dict(),
                "version": __import__("testerbot").__version__,
            },
            "intelligence": self.intelligence,
            "linkgraph": self.link_analysis,
            "summary": {"severity": dict(counts), "category": dict(by_category),
                        "total": len(findings)},
            "findings": [f.to_dict() for f in findings],
            "pages": [p.to_dict() for p in self.pages],
        }
