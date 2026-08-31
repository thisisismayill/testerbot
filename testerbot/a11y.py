"""axe-core powered accessibility audit (bundled, works offline)."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from .models import Finding

VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "axe.min.js")
CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"

IMPACT_TO_SEVERITY = {
    "critical": "high",
    "serious": "medium",
    "moderate": "low",
    "minor": "info",
}

RUN_AXE = """
async () => {
  if (typeof axe === 'undefined') return { error: 'axe not loaded' };
  try {
    const res = await axe.run(document, {
      resultTypes: ['violations'],
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] },
    });
    return {
      violations: res.violations.map(v => ({
        id: v.id, impact: v.impact, help: v.help, description: v.description,
        helpUrl: v.helpUrl,
        nodes: v.nodes.slice(0, 6).map(n => ({
          target: (n.target || []).join(' '),
          html: (n.html || '').slice(0, 200),
          summary: (n.failureSummary || '').slice(0, 300),
        })),
        total: v.nodes.length,
      })),
    };
  } catch (e) { return { error: String(e).slice(0, 300) }; }
}
"""

# axe rules already covered by TesterBot's own DOM checks - avoid duplicate noise
SKIP_RULES = {"image-alt", "html-has-lang", "duplicate-id", "duplicate-id-active",
              "duplicate-id-aria", "meta-viewport", "document-title", "link-name",
              "label", "button-name", "page-has-heading-one", "frame-title"}


def inject(page) -> bool:
    try:
        if page.evaluate("() => typeof axe !== 'undefined'"):
            return True
    except Exception:
        pass
    if os.path.exists(VENDOR):
        try:
            page.add_script_tag(path=VENDOR)
            return True
        except Exception:
            pass
    try:
        page.add_script_tag(url=CDN)
        return True
    except Exception:
        return False


def audit(page, url: str) -> List[Finding]:
    if not inject(page):
        return []
    try:
        result: Dict[str, Any] = page.evaluate(RUN_AXE)
    except Exception:
        return []
    if not result or result.get("error"):
        return []
    out: List[Finding] = []
    for v in result.get("violations", []):
        if v["id"] in SKIP_RULES:
            continue
        sev = IMPACT_TO_SEVERITY.get(v.get("impact") or "minor", "info")
        nodes = v.get("nodes", [])
        out.append(Finding(
            severity=sev, category="Accessibility",
            title=v["help"],
            occurrences=v.get("total", 1),
            detail=v.get("description", ""),
            url=url,
            evidence={"rule": v["id"], "impact": v.get("impact"),
                      "elements_affected": v.get("total", 1),
                      "examples": nodes, "reference": v.get("helpUrl", "")},
            how_to_fix=f"See the axe-core rule '{v['id']}': {v.get('helpUrl', '')}",
        ))
    return out
