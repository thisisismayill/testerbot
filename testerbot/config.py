"""Configuration for a TesterBot run."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

try:  # optional dependency
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class Config:
    # --- target -------------------------------------------------------
    url: str = ""
    max_pages: int = 40
    max_depth: int = 3
    include: List[str] = field(default_factory=list)   # regex, page must match one
    exclude: List[str] = field(default_factory=list)   # regex, page must match none
    allow_subdomains: bool = False
    extra_urls: List[str] = field(default_factory=list)
    use_sitemap: bool = True

    # --- browser ------------------------------------------------------
    headless: bool = True
    slow_mo: int = 0
    timeout_ms: int = 30000
    nav_timeout_ms: int = 45000
    user_agent: str = ""
    viewport_width: int = 1440
    viewport_height: int = 900
    locale: str = "en-US"
    ignore_https_errors: bool = False
    settle_ms: int = 1200          # extra wait after load for SPA rendering

    # --- login --------------------------------------------------------
    login_url: str = ""
    username: str = ""
    password: str = ""
    user_selector: str = ""
    pass_selector: str = ""
    submit_selector: str = ""
    login_success_text: str = ""
    login_success_url: str = ""
    storage_state: str = ""        # load an existing session
    save_storage_state: str = ""   # write session here after login

    # --- intelligence (site authority / performance / tech stack) -----
    run_intelligence: bool = True
    run_performance: bool = True     # PageSpeed Insights (slow-ish; can disable)
    opr_key: str = ""                # OpenPageRank domain-authority key (free)
    psi_key: str = ""                # PageSpeed Insights / Google API key (free, optional)

    # --- behaviour ----------------------------------------------------
    click_elements: bool = True
    submit_forms: bool = True
    max_clicks_per_page: int = 25
    max_forms_per_page: int = 4
    danger_mode: bool = False      # allow delete/pay/destructive clicks
    check_external_links: bool = True
    run_axe: bool = True
    hygiene_checks: bool = True
    responsive_checks: bool = True
    mobile_width: int = 390
    mobile_height: int = 844
    tablet_width: int = 820
    tablet_height: int = 1180
    screenshot_all: bool = False

    # --- thresholds ---------------------------------------------------
    slow_load_ms: int = 5000
    slow_ttfb_ms: int = 1500
    heavy_page_kb: int = 3000

    # --- output -------------------------------------------------------
    out_dir: str = "testerbot-report"
    report_name: str = "report.html"
    quiet: bool = False

    # ------------------------------------------------------------------
    DANGER_WORDS = [
        # english
        r"\bdelete\b", r"\bremove\b", r"\bdestroy\b", r"\berase\b", r"\bwipe\b",
        r"\bdeactivate\b", r"\bdisable account\b", r"\bclose account\b",
        r"\bcancel (subscription|account|order|plan)\b", r"\bunsubscribe\b",
        r"\bterminate\b", r"\bpay\b", r"\bpayment\b", r"\bcheckout\b", r"\bbuy\b",
        r"\bpurchase\b", r"\border now\b", r"\bdonate\b",
        r"\bconfirm order\b", r"\bplace order\b", r"\bwithdraw\b", r"\btransfer\b",
        r"\bsend money\b", r"\bblock user\b", r"\breset\b",
        r"\bfactory reset\b", r"\brestore defaults\b",
        r"\blog ?out\b", r"\bsign ?out\b", r"\bexit\b",
        r"\bpublish\b", r"\bdeploy\b", r"\bsend invite\b",
        # azerbaijani / turkish
        r"\bsil\b", r"\bsilin\b", r"\bs[iı]l[mn]", r"\bl[əe][ğg]v\b", r"\bl[əe][ğg]v et\b",
        r"\b[öo]d[əe]\b", r"\b[öo]d[əe]ni[şs]\b", r"\bsat[ıi]n al\b", r"\bsifari[şs]\b",
        r"\b[çc][ıi]x[ıi][şs]\b", r"\bhesab[ıi] ba[ğg]la\b", r"\bblokla\b",
        r"\bg[öo]nd[əe]r pul\b", r"\byay[ıi]mla\b",
        # russian
        r"\bудалить\b", r"\bоплатить\b", r"\bвыйти\b", r"\bотменить\b",
    ]

    SKIP_URL_PATTERNS = [
        r"/logout", r"/log-out", r"/signout", r"/sign-out", r"/exit",
        r"/unsubscribe", r"/delete", r"/remove", r"/destroy",
        r"[?&]action=(delete|logout|remove|destroy)",
        r"/wp-login\.php\?action=logout",
        r"\.(zip|rar|7z|tar|gz|exe|dmg|pkg|msi|iso|mp4|mp3|avi|mov|wav|apk)$",
    ]

    def danger_re(self) -> re.Pattern:
        return re.compile("|".join(self.DANGER_WORDS), re.I)

    def skip_url_re(self) -> re.Pattern:
        return re.compile("|".join(self.SKIP_URL_PATTERNS), re.I)

    # ------------------------------------------------------------------
    @classmethod
    def from_file(cls, path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        data: Dict[str, Any]
        if path.lower().endswith((".yaml", ".yml")):
            if yaml is None:
                raise SystemExit("PyYAML is not installed. Run: pip install pyyaml")
            data = yaml.safe_load(text) or {}
        else:
            data = json.loads(text)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        unknown = set(data) - known
        if unknown:
            raise SystemExit(f"Unknown config keys: {', '.join(sorted(unknown))}")
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        return cfg

    def merge_env(self) -> None:
        """Credentials may come from the environment so they never land in a file."""
        self.username = os.environ.get("TESTERBOT_USER", self.username)
        self.password = os.environ.get("TESTERBOT_PASS", self.password)
        self.opr_key = os.environ.get("TESTERBOT_OPR_KEY", self.opr_key)
        self.psi_key = os.environ.get("TESTERBOT_PSI_KEY", self.psi_key)

    def to_public_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if data.get("password"):
            data["password"] = "***"
        for k in ("opr_key", "psi_key"):
            if data.get(k):
                data[k] = "***"
        return data
