"""Site-wide checks: robots, sitemap, 404 handling, link health, hygiene."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from .config import Config
from .models import Finding
from .urls import normalise, origin, same_scope, shorten

HYGIENE_PATHS = [
    ("/.env", "critical", "Environment file with secrets"),
    ("/.git/config", "critical", "Git repository metadata"),
    ("/.git/HEAD", "critical", "Git repository metadata"),
    ("/.DS_Store", "low", "macOS directory index"),
    ("/phpinfo.php", "high", "PHP configuration dump"),
    ("/server-status", "medium", "Apache status page"),
    ("/.svn/entries", "high", "Subversion metadata"),
    ("/backup.zip", "high", "Site backup archive"),
    ("/backup.sql", "critical", "Database dump"),
    ("/db.sql", "critical", "Database dump"),
    ("/wp-config.php.bak", "critical", "WordPress config backup"),
    ("/config.php.bak", "critical", "Config backup"),
    ("/.env.local", "critical", "Environment file with secrets"),
    ("/composer.lock", "info", "Dependency manifest"),
    ("/package.json", "info", "Dependency manifest"),
    ("/.well-known/security.txt", None, "Security contact file"),
]


def fetch(request, url: str, method: str = "GET", timeout: int = 15000):
    try:
        if method == "HEAD":
            return request.head(url, timeout=timeout, max_redirects=5)
        return request.get(url, timeout=timeout, max_redirects=5)
    except Exception:
        return None


def _verdict(resp) -> Tuple[str, Optional[int]]:
    """What a probe actually proves.

    Absence is only ever proven by 404/410. A refusal (401/403), a rate limit
    (429), a server error or a timeout all mean *we could not look* - a
    different statement. Reporting those as "not found" invents a problem the
    site does not have, and sends someone off to fix a file that is already
    there, so the two cases are kept apart everywhere below.
    """
    if resp is None:
        return "unreachable", None
    if resp.status in (404, 410):
        return "missing", resp.status
    if resp.status < 400:
        return "present", resp.status
    return "blocked", resp.status


def check_reachable(request, base_url: str) -> Tuple[bool, List[Finding]]:
    """Does the site answer us at all? Returns (blocked, findings).

    When the answer is no, every later 'X is missing' check would only be
    measuring the block, so the caller stops asking them.
    """
    resp = fetch(request, origin(base_url) + "/")
    state, status = _verdict(resp)
    if state != "blocked":
        return False, []
    return True, [Finding(
        severity="high", category="HTTP Status",
        title=f"The site refused TesterBot (HTTP {status}) - this report is incomplete",
        detail=(
            f"Every request came back {status}, including plain files like /robots.txt. "
            "The site itself is probably fine - it is this client that is being turned "
            "away, usually by a CDN, WAF, bot protection or a rate limit that reacts to "
            "an automated browser. Nothing below this line was actually measured."),
        url=origin(base_url) + "/", evidence={"status": status},
        how_to_fix=(
            "Allow your own testing while a run is in progress: allow-list your IP in the "
            "CDN or firewall, or use the host's testing bypass. If the block is a rate "
            "limit it clears by itself - wait and run again."))]


# ------------------------------------------------------------------ sitemap

def discover_sitemap_urls(request, base_url: str, cfg: Config,
                          log, blocked: bool = False) -> Tuple[List[str], List[Finding]]:
    findings: List[Finding] = []
    urls: List[str] = []
    root = origin(base_url)

    robots = fetch(request, root + "/robots.txt")
    robots_state, robots_status = _verdict(robots)
    sitemap_refs: List[str] = []
    if robots_state == "missing":
        findings.append(Finding(
            severity="info", category="Site Hygiene",
            title="No robots.txt", url=root + "/robots.txt",
            detail="Crawlers get no guidance about what to index.",
            how_to_fix="Add a robots.txt (even an allow-all one) and reference your sitemap."))
    elif robots_state != "present":
        if not blocked:
            findings.append(Finding(
                severity="info", category="Site Hygiene",
                title="Could not check robots.txt", url=root + "/robots.txt",
                detail=(f"The server answered {robots_status} instead of the file. It may well "
                        "exist - this run simply could not read it."
                        if robots_status else
                        "The request did not complete, so this run could not read the file."),
                evidence={"status": robots_status} if robots_status else {},
                how_to_fix="Open the address in a browser to see whether the file is there."))
    else:
        try:
            body = robots.text()
            sitemap_refs = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", body)
            if re.search(r"(?im)^\s*disallow:\s*/\s*$", body):
                findings.append(Finding(
                    severity="medium", category="Site Hygiene",
                    title="robots.txt blocks the entire site",
                    detail="'Disallow: /' tells search engines to index nothing. That is a "
                           "serious bug on a public site (fine on staging).",
                    url=root + "/robots.txt", evidence={"robots_txt": body[:800]},
                    how_to_fix="Remove the blanket Disallow before going live."))
        except Exception:
            pass

    candidates = sitemap_refs or [root + "/sitemap.xml", root + "/sitemap_index.xml"]
    found_any = False
    sitemap_blocked: Optional[int] = None   # a refusal, not a 404: we could not look
    for sm in candidates[:5]:
        resp = fetch(request, sm)
        sm_state, sm_status = _verdict(resp)
        if sm_state != "present":
            if sm_state == "blocked" and sitemap_blocked is None:
                sitemap_blocked = sm_status
            continue
        try:
            xml = resp.text()
        except Exception:
            continue
        found_any = True
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml, re.I)
        nested = [loc for loc in locs if loc.lower().endswith(".xml")]
        for nest in nested[:5]:
            sub = fetch(request, nest)
            if sub is not None and sub.status < 400:
                try:
                    locs += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sub.text(), re.I)
                except Exception:
                    pass
        for loc in locs:
            n = normalise(loc)
            if n and same_scope(n, base_url, cfg.allow_subdomains) and not n.lower().endswith(".xml"):
                urls.append(n)
    if not found_any and not blocked and not sitemap_blocked:
        findings.append(Finding(
            severity="low", category="Site Hygiene",
            title="No sitemap.xml found", url=root + "/sitemap.xml",
            detail="Search engines have to discover pages by crawling links only.",
            how_to_fix="Publish a sitemap.xml and link it from robots.txt."))
    elif not found_any and sitemap_blocked and not blocked:
        findings.append(Finding(
            severity="info", category="Site Hygiene",
            title="Could not check sitemap.xml", url=root + "/sitemap.xml",
            detail=(f"The server answered {sitemap_blocked} instead of the file. A sitemap may "
                    "well be published - this run could not read it."),
            evidence={"status": sitemap_blocked},
            how_to_fix="Open the address in a browser to see whether the file is there."))
    elif found_any:
        log(f"  sitemap: {len(set(urls))} URLs discovered")
    seen: Set[str] = set()
    ordered = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered, findings


# ------------------------------------------------------------------ misc site checks

def check_404(request, base_url: str) -> List[Finding]:
    probe = origin(base_url) + "/testerbot-does-not-exist-9f2c1a"
    resp = fetch(request, probe)
    if resp is None:
        return []
    if resp.status == 200:
        return [Finding(
            severity="medium", category="HTTP Status",
            title="Unknown URLs return HTTP 200 instead of 404",
            detail="A deliberately invalid path returned a normal 200 response. Search engines "
                   "index junk pages and monitoring cannot tell real pages from typos.",
            url=probe, evidence={"status": resp.status},
            how_to_fix="Return status 404 for unknown routes (a styled 404 page is still 404).")]
    if resp.status >= 500:
        return [Finding(
            severity="high", category="HTTP Status",
            title=f"Unknown URLs return HTTP {resp.status}",
            detail="A missing page crashes the server instead of returning a clean 404.",
            url=probe, evidence={"status": resp.status})]
    return []


def check_https(request, base_url: str) -> List[Finding]:
    out: List[Finding] = []
    parsed = urlparse(base_url)
    if parsed.scheme != "https":
        out.append(Finding(
            severity="critical", category="Security",
            title="Site is served over plain HTTP",
            detail="All traffic, including anything typed into a form, is unencrypted and "
                   "browsers will label the site 'Not secure'.",
            url=base_url,
            how_to_fix="Install a TLS certificate and redirect http:// to https://."))
        return out
    http_url = "http://" + parsed.netloc + "/"
    resp = fetch(request, http_url)
    if resp is not None and resp.status < 400:
        final = resp.url
        if final.startswith("http://"):
            out.append(Finding(
                severity="high", category="Security",
                title="HTTP is served without redirecting to HTTPS",
                detail=f"{http_url} answered with {resp.status} and stayed on http://.",
                url=http_url, evidence={"final_url": final, "status": resp.status},
                how_to_fix="Add a permanent redirect from http:// to https://."))
    return out


def check_hygiene(request, base_url: str, blocked: bool = False) -> List[Finding]:
    """Look for files that are commonly left exposed by accident on one's own server."""
    out: List[Finding] = []
    root = origin(base_url)
    for path, severity, label in HYGIENE_PATHS:
        resp = fetch(request, root + path, timeout=8000)
        if resp is None:
            continue
        if path == "/.well-known/security.txt":
            state, _status = _verdict(resp)
            if state == "missing" and not blocked:
                out.append(Finding(
                    severity="info", category="Site Hygiene",
                    title="No security.txt", url=root + path,
                    detail="There is no documented way for someone to report a problem.",
                    how_to_fix="Publish /.well-known/security.txt with a contact address."))
            continue
        if resp.status != 200:
            continue
        try:
            body = resp.text()[:400]
        except Exception:
            body = ""
        low = body.lower().lstrip()
        if low.startswith("<!doctype") or low.startswith("<html") or "<body" in low:
            continue  # a soft-404 HTML page, not the real file
        if path in ("/package.json", "/composer.lock") and not low.startswith("{"):
            continue
        out.append(Finding(
            severity=severity or "medium", category="Exposed File",
            title=f"{label} is publicly reachable: {path}",
            detail="This file should not be served to the internet. It usually gets exposed by "
                   "deploying the whole working directory.",
            url=root + path,
            evidence={"status": resp.status, "excerpt": body[:300]},
            how_to_fix="Block the path at the web server, or stop deploying the file."))
    return out


# ------------------------------------------------------------------ links

def check_links(request, links: Dict[str, Dict[str, Any]], base_url: str,
                cfg: Config, log) -> List[Finding]:
    """links: url -> {'sources': set(page urls), 'text': str}"""
    findings: List[Finding] = []
    total = len(links)
    checked = 0
    for url, meta in links.items():
        checked += 1
        if checked % 25 == 0:
            log(f"  link check {checked}/{total}")
        internal = same_scope(url, base_url, cfg.allow_subdomains)
        if not internal and not cfg.check_external_links:
            continue
        resp = fetch(request, url, method="HEAD", timeout=12000)
        if resp is None or resp.status in (405, 501, 403, 400):
            resp = fetch(request, url, method="GET", timeout=15000)
        sources = sorted(meta["sources"])[:8]
        if resp is None:
            findings.append(Finding(
                severity="medium" if not internal else "high",
                category="Broken Link",
                title=f"Link unreachable: {shorten(url, 70)}",
                detail="The request failed entirely (DNS, TLS or connection error).",
                url=sources[0] if sources else base_url,
                evidence={"target": url, "link_text": meta.get("text", ""),
                          "found_on": sources},
                occurrences=len(meta["sources"]), other_urls=sources[1:],
                how_to_fix="Fix or remove the link."))
            continue
        status = resp.status
        if status >= 400:
            sev = "high" if internal else "medium"
            if status in (401, 403):
                sev = "low" if not internal else "medium"
            findings.append(Finding(
                severity=sev, category="Broken Link",
                title=f"HTTP {status} link: {shorten(url, 65)}",
                detail=f"A link on the site points to a URL that answers {status}."
                       + ("" if internal else " (external site)"),
                url=sources[0] if sources else base_url,
                evidence={"target": url, "status": status,
                          "link_text": meta.get("text", ""), "found_on": sources},
                occurrences=len(meta["sources"]), other_urls=sources[1:],
                how_to_fix="Update the href or remove the link."))
    return findings


# ------------------------------------------------------------------ cross-page

def cross_page_checks(pages: List[Any]) -> List[Finding]:
    out: List[Finding] = []
    by_title: Dict[str, List[str]] = defaultdict(list)
    for p in pages:
        if p.title and p.status and p.status < 400:
            by_title[p.title.strip()].append(p.url)
    for title, urls in by_title.items():
        if len(urls) > 1:
            out.append(Finding(
                severity="low", category="SEO",
                title=f"{len(urls)} pages share the same <title>: \"{title[:60]}\"",
                detail="Duplicate titles hurt search results and make browser tabs ambiguous.",
                url=urls[0], evidence={"pages": urls[:12]},
                occurrences=len(urls), other_urls=urls[1:8],
                how_to_fix="Give every page a distinct title."))
    return out
