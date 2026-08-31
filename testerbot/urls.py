"""URL helpers: normalisation, scoping, classification."""
from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import urljoin, urldefrag, urlparse, urlunparse, parse_qsl, urlencode

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid", "yclid", "msclkid", "_ga",
}

NON_PAGE_SCHEMES = ("mailto:", "tel:", "sms:", "javascript:", "data:", "blob:", "file:", "ftp:")

ASSET_EXT = re.compile(
    r"\.(png|jpe?g|gif|svg|webp|ico|bmp|avif|css|js|mjs|json|xml|txt|woff2?|ttf|eot|"
    r"pdf|zip|rar|7z|tar|gz|mp4|mp3|wav|avi|mov|webm|apk|exe|dmg|csv|xlsx?|docx?|pptx?)($|\?)",
    re.I,
)

DOC_EXT = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|csv|txt)($|\?)", re.I)


def normalise(url: str, base: Optional[str] = None) -> Optional[str]:
    """Absolute, fragment-free, tracking-free URL. None if not a fetchable http(s) URL."""
    if not url:
        return None
    url = url.strip()
    low = url.lower()
    if low.startswith(NON_PAGE_SCHEMES):
        return None
    if base:
        url = urljoin(base, url)
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS]
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and parsed.scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and parsed.scheme == "https":
        netloc = netloc[:-4]
    return urlunparse((parsed.scheme, netloc, path, "", urlencode(query), ""))


def registrable(host: str) -> str:
    """Crude eTLD+1 (good enough for scoping a crawl)."""
    host = host.lower().split(":")[0]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if parts[-2] in {"co", "com", "org", "net", "gov", "edu", "ac"} and len(parts[-1]) <= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_scope(url: str, base_url: str, allow_subdomains: bool = False) -> bool:
    a, b = urlparse(url), urlparse(base_url)
    if allow_subdomains:
        return registrable(a.netloc) == registrable(b.netloc)
    return a.netloc.lower() == b.netloc.lower()


def is_asset(url: str) -> bool:
    return bool(ASSET_EXT.search(urlparse(url).path or ""))


def is_document(url: str) -> bool:
    return bool(DOC_EXT.search(urlparse(url).path or ""))


def origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def path_of(url: str) -> str:
    return urlparse(url).path or "/"


def shorten(url: str, limit: int = 70) -> str:
    if len(url) <= limit:
        return url
    return url[: limit - 15] + "…" + url[-14:]


def split_host(url: str) -> Tuple[str, str]:
    p = urlparse(url)
    return p.scheme, p.netloc
