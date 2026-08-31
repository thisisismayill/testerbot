"""Turn raw page observations into Findings."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .config import Config
from .models import Finding
from .urls import shorten

# ---------------------------------------------------------------- console / JS

IGNORABLE_CONSOLE = re.compile(
    r"(favicon\.ico|Download the React DevTools|Lighthouse|"
    r"chrome-extension://|DevTools failed to load source ?map|"
    r"was preloaded using link preload but not used|"
    r"Third-party cookie will be blocked|Failed to load resource: the server responded)", re.I)


def audit_console(url: str, console_msgs: List[Dict[str, Any]],
                  page_errors: List[Dict[str, Any]]) -> List[Finding]:
    out: List[Finding] = []
    for err in page_errors:
        out.append(Finding(
            severity="critical", category="JavaScript Error",
            title=f"Uncaught JS exception: {err['message'][:110]}",
            detail="An unhandled JavaScript exception was thrown while the page was open. "
                   "Whatever feature threw it is very likely broken for real users.",
            url=url,
            evidence={"message": err["message"][:1500], "stack": (err.get("stack") or "")[:2000]},
            how_to_fix="Open DevTools on this page, reproduce, and fix the throwing call.",
        ))
    seen = set()
    for msg in console_msgs:
        text = msg.get("text", "")
        if IGNORABLE_CONSOLE.search(text):
            continue
        kind = msg.get("type")
        key = text[:120]
        if key in seen:
            continue
        seen.add(key)
        if kind == "error":
            out.append(Finding(
                severity="high", category="Console Error",
                title=f"console.error: {text[:110]}",
                detail="The browser console logged an error on this page.",
                url=url,
                evidence={"text": text[:1500], "location": msg.get("location", "")},
                how_to_fix="Trace the logged error in DevTools and remove the cause.",
            ))
        elif kind == "warning" and re.search(
                r"(deprecat|violation|failed|cannot|blocked|insecure|mixed content)", text, re.I):
            out.append(Finding(
                severity="low", category="Console Warning",
                title=f"console.warn: {text[:110]}",
                detail="A notable browser warning was logged.",
                url=url, evidence={"text": text[:1000]},
            ))
    return out


# ---------------------------------------------------------------- network

def audit_network(url: str, failed: List[Dict[str, Any]],
                  bad_responses: List[Dict[str, Any]]) -> List[Finding]:
    out: List[Finding] = []
    for req in failed:
        out.append(Finding(
            severity="high", category="Network",
            title=f"Request failed: {shorten(req['url'], 80)}",
            detail=f"The browser could not complete this request ({req.get('failure')}). "
                   "A missing asset or an unreachable API breaks part of the page.",
            url=url,
            evidence={"request_url": req["url"], "resource_type": req.get("resource_type"),
                      "failure": req.get("failure"), "method": req.get("method")},
            how_to_fix="Fix the URL, restore the file, or handle the failure in code.",
        ))
    for resp in bad_responses:
        status = resp["status"]
        sev = "critical" if status >= 500 else "high"
        out.append(Finding(
            severity=sev, category="Network",
            title=f"HTTP {status} on {resp.get('resource_type', 'request')}: "
                  f"{shorten(resp['url'], 70)}",
            detail=f"A sub-request returned HTTP {status} while loading this page."
                   + (" A 5xx means the server itself errored."
                      if status >= 500 else " The resource is missing or forbidden."),
            url=url,
            evidence={"request_url": resp["url"], "status": status,
                      "method": resp.get("method"), "resource_type": resp.get("resource_type")},
            how_to_fix="Fix the endpoint or stop the page from requesting it.",
        ))
    return out


# ---------------------------------------------------------------- HTTP + headers

SECURITY_HEADERS = {
    "content-security-policy": ("Content-Security-Policy", "low"),
    "x-content-type-options": ("X-Content-Type-Options", "low"),
    "referrer-policy": ("Referrer-Policy", "info"),
    "x-frame-options": ("X-Frame-Options", "low"),
    "strict-transport-security": ("Strict-Transport-Security", "low"),
}


def audit_http(url: str, status: Optional[int], headers: Dict[str, str],
               is_entry: bool) -> List[Finding]:
    out: List[Finding] = []
    headers = {k.lower(): v for k, v in (headers or {}).items()}

    if status is not None and status >= 400:
        sev = "critical" if status >= 500 else "high"
        out.append(Finding(
            severity=sev, category="HTTP Status",
            title=f"Page returns HTTP {status}",
            detail="This page is linked from the site but does not load successfully.",
            url=url, evidence={"status": status},
            how_to_fix="Restore the page or remove/redirect the links pointing at it.",
        ))
        return out

    if not is_entry:
        return out

    # header hygiene reported once, on the entry page
    for key, (label, sev) in SECURITY_HEADERS.items():
        if key == "strict-transport-security" and not url.startswith("https://"):
            continue
        if key == "x-frame-options":
            csp = headers.get("content-security-policy", "")
            if "frame-ancestors" in csp.lower():
                continue
        if key not in headers:
            out.append(Finding(
                severity=sev, category="Security Headers",
                title=f"Missing security header: {label}",
                detail=f"The site does not send the {label} response header.",
                url=url, evidence={"present_headers": sorted(headers.keys())[:40]},
                how_to_fix=f"Add the {label} header at the web server or CDN level.",
            ))
    server = headers.get("server", "") + " " + headers.get("x-powered-by", "")
    if re.search(r"\d+\.\d+", server):
        out.append(Finding(
            severity="info", category="Security Headers",
            title="Server software and version are advertised in response headers",
            detail=f"Server/X-Powered-By reveals: {server.strip()}",
            url=url, evidence={"server": headers.get("server", ""),
                               "x_powered_by": headers.get("x-powered-by", "")},
            how_to_fix="Suppress the version banner in the web server configuration.",
        ))
    return out


# ---------------------------------------------------------------- DOM findings

def audit_dom(url: str, d: Dict[str, Any], cfg: Config, is_entry: bool) -> List[Finding]:
    out: List[Finding] = []
    add = out.append

    # ---- content sanity
    if d.get("bodyTextLength", 0) < 30:
        add(Finding(
            severity="high", category="Content",
            title="Page renders (almost) no text",
            detail=f"Only {d.get('bodyTextLength', 0)} characters of visible text were found. "
                   "The page is blank, still loading, or the app failed to mount.",
            url=url, evidence={"excerpt": d.get("bodyExcerpt", "")},
            how_to_fix="Check that the content/app actually renders without a logged-in state "
                       "or a slow API.",
        ))
    for junk in d.get("junk", []):
        label = junk["label"]
        sev = "high" if label in ("Error text", "[object Object]", "undefined", "NaN") else "medium"
        add(Finding(
            severity=sev, category="Content",
            title=f"Placeholder / debug text visible to users: {label}",
            detail="Text that should never reach production is rendered on the page.",
            url=url, evidence={"excerpt": junk["excerpt"]},
            how_to_fix="Replace the placeholder or fix the value that renders as junk.",
        ))

    # ---- SEO / metadata
    title = d.get("title", "")
    if not title:
        add(Finding(severity="medium", category="SEO",
                    title="Page has no <title>", url=url,
                    detail="Browsers, bookmarks and search results have nothing to show.",
                    how_to_fix="Add a unique, descriptive <title> to this page."))
    elif len(title) > 65:
        add(Finding(severity="info", category="SEO",
                    title="Page title is longer than 65 characters", url=url,
                    detail=f"Title ({len(title)} chars): {title}",
                    evidence={"title": title},
                    how_to_fix="Shorten it so search engines do not truncate it."))
    desc = d.get("metaDescription")
    if desc is None:
        add(Finding(severity="low", category="SEO",
                    title="No meta description", url=url,
                    detail="Search engines will invent a snippet for this page.",
                    how_to_fix="Add <meta name=\"description\" content=\"…\">."))
    elif not desc.strip():
        add(Finding(severity="low", category="SEO",
                    title="Meta description is empty", url=url,
                    how_to_fix="Fill in the description or remove the tag."))
    if d.get("h1Count", 0) == 0:
        add(Finding(severity="low", category="SEO",
                    title="Page has no <h1>", url=url,
                    detail="No top-level heading was found in the rendered page.",
                    how_to_fix="Give the page exactly one <h1> describing its content."))
    elif d.get("h1Count", 0) > 1:
        add(Finding(severity="info", category="SEO",
                    title=f"Page has {d['h1Count']} <h1> headings", url=url,
                    detail="Multiple H1s dilute the page's topic signal.",
                    how_to_fix="Keep one <h1> and demote the rest."))
    if is_entry and not d.get("favicon"):
        add(Finding(severity="info", category="SEO",
                    title="No favicon declared", url=url,
                    how_to_fix="Add <link rel=\"icon\" …> so tabs and bookmarks look right."))
    if d.get("noindex"):
        add(Finding(severity="medium", category="SEO",
                    title="Page is marked noindex", url=url,
                    detail="A robots meta tag tells search engines to skip this page. "
                           "That is a bug if the page is meant to be public.",
                    how_to_fix="Remove the noindex tag if the page should be indexed."))
    if is_entry and not d.get("ogTitle"):
        add(Finding(severity="info", category="SEO",
                    title="No Open Graph tags", url=url,
                    detail="Links shared on social media / chat apps will have no preview.",
                    how_to_fix="Add og:title, og:description and og:image."))

    # ---- language & viewport
    if not d.get("lang"):
        add(Finding(severity="low", category="Accessibility",
                    title="<html> has no lang attribute", url=url,
                    detail="Screen readers cannot pick the right pronunciation rules.",
                    how_to_fix="Add lang=\"en\" (or the real language) to the <html> tag."))
    if d.get("viewportMeta") is None:
        add(Finding(severity="high", category="Responsive",
                    title="No responsive viewport meta tag", url=url,
                    detail="Without it, mobile browsers render the page at desktop width and "
                           "zoom out — the classic 'tiny text on phone' bug.",
                    how_to_fix='Add <meta name="viewport" content="width=device-width, '
                               'initial-scale=1">.'))
    elif "user-scalable=no" in (d.get("viewportMeta") or "").lower() or \
            re.search(r"maximum-scale=\s*1(\.0)?\b", (d.get("viewportMeta") or "").lower()):
        add(Finding(severity="low", category="Accessibility",
                    title="Viewport meta disables pinch zoom", url=url,
                    evidence={"viewport": d.get("viewportMeta")},
                    how_to_fix="Remove user-scalable=no / maximum-scale so users can zoom."))

    # ---- images
    no_alt = d.get("imagesNoAlt", [])
    if no_alt:
        add(Finding(severity="medium", category="Accessibility",
                    title="Images without an alt attribute", url=url, occurrences=len(no_alt),
                    detail="Screen-reader users get no description; broken images show nothing.",
                    element=no_alt[0]["selector"],
                    evidence={"images": no_alt[:15]},
                    how_to_fix='Add alt="…" (or alt="" for purely decorative images).'))
    broken = d.get("imagesBroken", [])
    if broken:
        add(Finding(severity="high", category="Broken Media",
                    title="Images that fail to load", url=url, occurrences=len(broken),
                    detail="The <img> resolved to a URL the browser could not render.",
                    element=broken[0]["selector"],
                    evidence={"images": broken[:15]},
                    how_to_fix="Fix the image path or upload the missing file."))

    # ---- links
    if d.get("emptyLinks"):
        add(Finding(severity="medium", category="Accessibility",
                    title="Links with no readable text", url=url,
                    occurrences=len(d['emptyLinks']),
                    detail="Icon-only or empty links are announced as 'link' with no context.",
                    element=d["emptyLinks"][0]["selector"],
                    evidence={"links": d["emptyLinks"][:15]},
                    how_to_fix="Add visible text, aria-label, or alt text on the inner icon."))
    if d.get("blankNoRel"):
        add(Finding(severity="low", category="Security",
                    title="Links open a new tab without rel=noopener", url=url,
                    occurrences=len(d['blankNoRel']),
                    detail="target=\"_blank\" without rel=\"noopener\" lets the opened page "
                           "reach back through window.opener in older browsers.",
                    element=d["blankNoRel"][0]["selector"],
                    evidence={"links": d["blankNoRel"][:15]},
                    how_to_fix='Add rel="noopener noreferrer" to those links.'))
    if d.get("hrefLessAnchors", 0) > 0:
        add(Finding(severity="info", category="Accessibility",
                    title="<a> elements without an href", url=url,
                    occurrences=d['hrefLessAnchors'],
                    detail="An anchor without href is not keyboard focusable and is not a link.",
                    how_to_fix="Use a <button> for actions, or give the anchor a real href."))

    # ---- forms & labels
    unl = [u for u in d.get("unlabelled", []) if not u.get("placeholderOnly")]
    ph_only = [u for u in d.get("unlabelled", []) if u.get("placeholderOnly")]
    if unl:
        add(Finding(severity="medium", category="Accessibility",
                    title="Form fields with no label", url=url, occurrences=len(unl),
                    detail="Nothing tells a screen-reader user what to type in these fields.",
                    element=unl[0]["selector"], evidence={"fields": unl[:15]},
                    how_to_fix="Add <label for=\"…\"> or aria-label to each field."))
    if ph_only:
        add(Finding(severity="low", category="Accessibility",
                    title="Fields rely on placeholder text instead of a label", url=url,
                    occurrences=len(ph_only),
                    detail="The placeholder disappears as soon as the user types, so the "
                           "field loses its description.",
                    element=ph_only[0]["selector"], evidence={"fields": ph_only[:15]},
                    how_to_fix="Add a real <label> in addition to the placeholder."))
    if d.get("namelessButtons"):
        add(Finding(severity="medium", category="Accessibility",
                    title="Buttons with no accessible name", url=url,
                    occurrences=len(d['namelessButtons']),
                    element=d["namelessButtons"][0]["selector"],
                    evidence={"buttons": d["namelessButtons"][:10]},
                    detail="Icon-only buttons are announced as just 'button'.",
                    how_to_fix="Add aria-label or visually hidden text."))
    if d.get("insecureForms", 0):
        add(Finding(severity="critical", category="Security",
                    title="Form submits over plain HTTP", url=url,
                    detail="A form action starts with http:// — submitted data, possibly "
                           "including credentials, travels unencrypted.",
                    how_to_fix="Change the form action to https://."))

    # ---- structural
    if d.get("duplicateIds"):
        add(Finding(severity="low", category="HTML Validity",
                    title="Duplicate element ids", url=url,
                    occurrences=len(d['duplicateIds']),
                    detail="Duplicate IDs break label targeting, anchors and querySelector.",
                    evidence={"ids": d["duplicateIds"][:20]},
                    how_to_fix="Make every id unique on the page."))
    if d.get("headingSkips"):
        add(Finding(severity="info", category="Accessibility",
                    title="Heading levels are skipped", url=url,
                    detail="e.g. an H2 is followed directly by an H4, which confuses "
                           "screen-reader navigation.",
                    evidence={"skips": d["headingSkips"][:10]},
                    how_to_fix="Use heading levels in order without gaps."))
    if d.get("mixedContent"):
        add(Finding(severity="high", category="Security",
                    title="Mixed content (http:// resources on an https:// page)", url=url,
                    occurrences=len(d['mixedContent']),
                    detail="http:// resources on an https:// page are blocked or downgrade "
                           "the padlock.",
                    evidence={"resources": d["mixedContent"][:15]},
                    how_to_fix="Serve every resource over https://."))
    for frame in d.get("iframes", []):
        if not frame.get("title"):
            add(Finding(severity="info", category="Accessibility",
                        title="iframe without a title attribute", url=url,
                        evidence={"src": frame.get("src", "")},
                        how_to_fix="Add title=\"…\" describing the embedded content."))
            break
    if d.get("autoplayMedia", 0):
        add(Finding(severity="low", category="UX",
                    title="Media auto-plays with sound", url=url,
                    detail="Unmuted autoplay is blocked by most browsers and annoys users.",
                    how_to_fix="Mute autoplaying media or require a user gesture."))
    if d.get("videosNoCaptions", 0):
        add(Finding(severity="low", category="Accessibility",
                    title="Videos without captions", url=url,
                    occurrences=d['videosNoCaptions'],
                    how_to_fix="Add a <track kind=\"captions\"> element."))
    if d.get("domNodes", 0) > 4000:
        add(Finding(severity="low", category="Performance",
                    title=f"Very large DOM ({d['domNodes']} nodes)", url=url,
                    detail="Huge DOMs make styling, scrolling and interaction slow.",
                    how_to_fix="Virtualise long lists or split the page."))
    return out


# ---------------------------------------------------------------- performance

def audit_performance(url: str, cfg: Config, timing: Dict[str, Any],
                      weight_kb: float, requests: int) -> List[Finding]:
    out: List[Finding] = []
    load = timing.get("load_ms")
    ttfb = timing.get("ttfb_ms")
    if load and load > cfg.slow_load_ms:
        out.append(Finding(
            severity="medium" if load < cfg.slow_load_ms * 2 else "high",
            category="Performance",
            title=f"Slow page load: {load/1000:.1f}s",
            detail=f"Load event fired after {load:.0f} ms "
                   f"(threshold {cfg.slow_load_ms} ms).",
            url=url, evidence=timing,
            how_to_fix="Profile with DevTools; usually images, blocking JS or slow APIs."))
    if ttfb and ttfb > cfg.slow_ttfb_ms:
        out.append(Finding(
            severity="medium", category="Performance",
            title=f"Slow server response (TTFB {ttfb:.0f} ms)",
            detail="Time to first byte is dominated by server work, not the browser.",
            url=url, evidence=timing,
            how_to_fix="Cache the response, add an index, or move work off the request path."))
    if weight_kb and weight_kb > cfg.heavy_page_kb:
        out.append(Finding(
            severity="low", category="Performance",
            title=f"Heavy page: {weight_kb/1024:.1f} MB transferred",
            detail=f"{requests} requests, {weight_kb:.0f} KB total.",
            url=url, evidence={"weight_kb": round(weight_kb, 1), "requests": requests},
            how_to_fix="Compress images, enable gzip/brotli, split bundles."))
    return out


# ---------------------------------------------------------------- responsive

def audit_responsive(url: str, label: str, width: int, metrics: Dict[str, Any],
                     screenshot: Optional[str]) -> List[Finding]:
    out: List[Finding] = []
    scroll_w = metrics.get("scrollWidth", 0)
    if scroll_w and scroll_w > width + 4:
        out.append(Finding(
            severity="medium", category="Responsive",
            title=f"Horizontal scrolling on {label} ({width}px)",
            detail=f"Content is {scroll_w}px wide in a {width}px viewport, so the user has to "
                   "scroll sideways. Usually one element with a fixed width or an unwrapped table.",
            url=url,
            evidence={"viewport_width": width, "content_width": scroll_w,
                      "overflow_px": scroll_w - width,
                      "widest_elements": metrics.get("wide", [])[:5]},
            screenshot=screenshot,
            how_to_fix="Find the overflowing element and give it max-width:100% / overflow-x:auto."))
    return out
