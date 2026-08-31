"""Data models shared across TesterBot."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

SEVERITY_WEIGHT = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@dataclass
class Finding:
    """A single problem discovered on the site."""

    severity: str
    category: str
    title: str
    detail: str = ""
    url: str = ""
    element: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    screenshot: Optional[str] = None
    how_to_fix: str = ""
    occurrences: int = 1
    other_urls: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Stable identity used for de-duplication."""
        raw = "|".join([self.category, self.title, self.url, self.element or ""])
        return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:12]

    @property
    def group_key(self) -> str:
        """Identity ignoring the URL, so a site-wide issue collapses into one row."""
        raw = "|".join([self.category, self.title])
        return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:12]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["id"] = self.key
        return data


@dataclass
class PageResult:
    """Everything TesterBot learned about one page."""

    url: str
    status: Optional[int] = None
    title: str = ""
    depth: int = 0
    load_ms: Optional[float] = None
    ttfb_ms: Optional[float] = None
    dom_ready_ms: Optional[float] = None
    weight_kb: Optional[float] = None
    requests: int = 0
    links_found: int = 0
    buttons_clicked: int = 0
    forms_tested: int = 0
    findings: int = 0
    screenshot: Optional[str] = None
    error: Optional[str] = None
    skipped_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
