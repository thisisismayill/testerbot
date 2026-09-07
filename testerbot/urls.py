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


def host_key(netloc: str) -> str:
    """Host as used for scope comparison, with a leading 'www.' removed.

    'www' is not a real subdomain boundary: www.example.com and example.com are
    the same site by convention, and sites redirect freely between the two. A
    crawl seeded at the bare domain that lands on the www form would otherwise
    judge every internal link out of scope and stop after one page. The port is
    kept, because a different port really is a different site.
    """
    host = netloc.lower()
    return host[4:] if host.startswith("www.") else host


def same_scope(url: str, base_url: str, allow_subdomains: bool = False) -> bool:
    a, b = urlparse(url), urlparse(base_url)
    if allow_subdomains:
        return registrable(a.netloc) == registrable(b.netloc)
    return host_key(a.netloc) == host_key(b.netloc)


# Domains that sit in the footer of almost every website: social networks,
# messengers, shorteners, app stores, CDNs. In a web-scale index they rank
# correctly high. In a focused index they are noise - every site you crawl
# links to them, so they float to the top of any ranking and push the domains
# you actually care about off the page. They stay in the graph (removing them
# would distort the link maths); they are only hidden from the default view.
UTILITY_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "youtube.com", "youtu.be", "tiktok.com", "pinterest.com", "reddit.com",
    "snapchat.com", "threads.net", "bsky.app", "mastodon.social", "vk.com",
    "t.me", "telegram.me", "telegram.org", "whatsapp.com", "wa.me", "discord.com", "discord.gg",
    "bit.ly", "tinyurl.com", "buff.ly", "ow.ly", "lnkd.in", "goo.gl", "t.co",
    "google.com", "gstatic.com", "googleapis.com", "googletagmanager.com",
    "doubleclick.net", "gravatar.com", "apple.com", "microsoft.com",
    "servedbyadbutler.com", "adbutler.com", "adsrvr.org", "criteo.com",
    "outbrain.com", "taboola.com", "scorecardresearch.com",
    "amazon.com", "adobe.com", "cloudflare.com", "jsdelivr.net", "unpkg.com",
    "cdnjs.com", "fontawesome.com", "bootstrapcdn.com", "w3.org", "schema.org",
    "wordpress.org", "wordpress.com", "wp.com", "gravatar.com",
    "wikipedia.org", "archive.org", "github.io", "gmail.com", "outlook.com",
    "play.google.com", "apps.apple.com", "itunes.apple.com",
    # publishing, podcast and consent platforms every publisher embeds:
    "spotify.com", "podcasts.apple.com", "soundcloud.com", "vimeo.com",
    "flickr.com", "beehiiv.com", "substack.com", "medium.com", "ghost.org",
    "mailchimp.com", "hubspot.com", "onetrust.com", "cookiebot.com",
    "eventbrite.com", "calendly.com", "typeform.com", "disqus.com",
    "creativecommons.org", "adobe.com", "oracle.com", "salesforce.com",
    # cookie banners and privacy notices link to the same handful of pages
    # from every site that has one:
    "cookiepedia.co.uk", "aboutcookies.org", "allaboutcookies.org",
    "aboutads.info", "youronlinechoices.com", "youronlinechoices.eu",
    "networkadvertising.org", "optout.aboutads.info", "iabeurope.eu",
    "qualtrics.com", "trustarc.com", "usercentrics.com",
    # browser vendors, linked from "this site works best in..." notices:
    "mozilla.org", "opera.com", "firefox.com", "chrome.com", "brave.com",
}


def is_utility(domain: str) -> bool:
    """True for the plumbing of the web rather than a site in anyone's field."""
    return host_key(domain or "") in UTILITY_DOMAINS


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
