"""Logging the bot into the site under test.

The password is only ever typed into the site's own password field. It is
never printed, never put in a finding and never written to the report: any
text that could echo it is scrubbed first.
"""
from __future__ import annotations

import re
import time
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from .config import Config
from .models import Finding

# what a site says when it turns the credentials down
LOGIN_ERROR_RE = re.compile(
    r"[^.\n]{0,80}(invalid|incorrect|wrong|not found|does not exist|doesn't exist|failed|"
    r"do(es)? not match|too many|locked|blocked|not verified|unverified|try again|"
    r"x[əe]ta|s[əe]hv|yanl[ıi][şs]|неверн|ошибка)[^.\n]{0,80}", re.I)

USER_SELECTORS = [
    "input[type='email']",
    "input[name*='email' i]",
    "input[name*='user' i]",
    "input[name*='login' i]",
    "input[id*='email' i]",
    "input[id*='user' i]",
    "input[autocomplete='username']",
    "input[type='text']",
    "input[type='tel']",
]

SUBMIT_SELECTORS = [
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Log in')",
    "button:has-text('Login')",
    "button:has-text('Sign in')",
    "button:has-text('Sign In')",
    "button:has-text('Daxil ol')",
    "button:has-text('Giriş')",
    "button:has-text('Войти')",
    "form button",
]

LOGIN_LINK_SELECTORS = [
    "a:has-text('Log in')", "a:has-text('Login')", "a:has-text('Sign in')",
    "a:has-text('Daxil ol')", "a:has-text('Giriş')",
    "a[href*='login' i]", "a[href*='signin' i]", "a[href*='sign-in' i]",
]


class LoginError(Exception):
    pass


def _first_visible(page, selectors: List[str], scope=None):
    root = scope or page
    for sel in selectors:
        try:
            loc = root.locator(sel).first
            if loc.count() and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def find_login_page(page, base_url: str, cfg: Config) -> Optional[str]:
    """If no --login-url was given, try to discover one from the home page."""
    if cfg.login_url:
        return cfg.login_url
    try:
        page.goto(base_url, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
    except Exception:
        return None
    if page.locator("input[type='password']").count():
        return page.url
    link = _first_visible(page, LOGIN_LINK_SELECTORS)
    if link is not None:
        try:
            href = link.get_attribute("href")
            if href:
                from .urls import normalise
                return normalise(href, page.url)
        except Exception:
            pass
    for guess in ("/login", "/signin", "/sign-in", "/account/login", "/user/login", "/admin/login"):
        try:
            resp = page.goto(base_url.rstrip("/") + guess,
                             timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
            if resp and resp.status < 400 and page.locator("input[type='password']").count():
                return page.url
        except Exception:
            continue
    return None


def _scrub(text: str, cfg: Config) -> str:
    """Never let the password through, whatever an error message quotes."""
    text = str(text or "")
    if cfg.password:
        text = text.replace(cfg.password, "***")
    return text


def login(page, cfg: Config, base_url: str) -> Tuple[bool, List[Finding], str]:
    """Perform the login. Returns (ok, findings, message)."""
    findings: List[Finding] = []
    if not cfg.username and not cfg.password:
        return False, findings, "no credentials supplied"
    try:
        return _login(page, cfg, base_url, findings)
    except Exception as exc:          # a broken page must not crash the whole run
        return False, findings, _scrub(f"login could not be completed: {exc}", cfg)[:300]


def _login(page, cfg: Config, base_url: str,
           findings: List[Finding]) -> Tuple[bool, List[Finding], str]:
    target = find_login_page(page, base_url, cfg)
    if target and not cfg.login_url:
        cfg.login_url = target        # so the crawl knows which page is the login page
    if not target:
        findings.append(Finding(
            severity="high", category="Authentication",
            title="Login page could not be found",
            detail="TesterBot looked for a login link and the usual login paths but found no "
                   "page containing a password field. Pass --login-url explicitly.",
            url=base_url,
            how_to_fix="Re-run with --login-url https://your-site/login",
        ))
        return False, findings, "login page not found"

    try:
        page.goto(target, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(cfg.settle_ms)
    except Exception as exc:
        findings.append(Finding(
            severity="critical", category="Authentication",
            title="Login page failed to load",
            detail=_scrub(exc, cfg)[:400], url=target,
        ))
        return False, findings, "login page failed to load"

    pass_loc = (page.locator(cfg.pass_selector).first if cfg.pass_selector
                else page.locator("input[type='password']").first)
    if not pass_loc.count():
        # single-page apps sometimes draw the form a moment after the page loads
        try:
            pass_loc.wait_for(state="attached", timeout=8000)
        except Exception:
            pass
    if not pass_loc.count():
        findings.append(Finding(
            severity="high", category="Authentication",
            title="No password field on the login page",
            detail=f"Opened {target} but found no input[type=password].",
            url=target,
            how_to_fix="Pass --pass-selector with the real selector if the field is custom.",
        ))
        return False, findings, "no password field"

    user_loc = (page.locator(cfg.user_selector).first if cfg.user_selector
                else _first_visible(page, USER_SELECTORS))
    if user_loc is None or not user_loc.count():
        findings.append(Finding(
            severity="high", category="Authentication",
            title="Username field could not be identified",
            detail="Found a password field but no matching username/email input.",
            url=target,
            how_to_fix="Pass --user-selector with the real selector.",
        ))
        return False, findings, "no username field"

    before_url = page.url
    try:
        user_loc.fill(cfg.username, timeout=cfg.timeout_ms)
        pass_loc.fill(cfg.password, timeout=cfg.timeout_ms)
    except Exception as exc:
        return False, findings, _scrub(f"could not fill credentials: {exc}", cfg)[:300]

    submit = (page.locator(cfg.submit_selector).first if cfg.submit_selector
              else _first_visible(page, SUBMIT_SELECTORS))
    try:
        if submit is not None and submit.count():
            submit.click(timeout=cfg.timeout_ms)
        else:
            pass_loc.press("Enter")
    except Exception:
        try:
            pass_loc.press("Enter")
        except Exception as exc:
            return False, findings, _scrub(f"could not submit login form: {exc}", cfg)[:300]

    try:
        page.wait_for_load_state("networkidle", timeout=min(cfg.nav_timeout_ms, 15000))
    except Exception:
        pass
    page.wait_for_timeout(cfg.settle_ms)

    # A single-page app checks the password over the network and then redraws,
    # sometimes seconds later: keep looking for a little while before deciding.
    # Success has to hold for a moment too - some forms vanish while they send
    # and come back with an error.
    def settled() -> bool:
        if not _verify(page, cfg, before_url):
            return False
        page.wait_for_timeout(1200)
        return _verify(page, cfg, before_url)

    ok = settled()
    deadline = time.time() + 12
    while not ok and time.time() < deadline:
        page.wait_for_timeout(700)
        ok = settled()
    if not ok:
        body = ""
        try:
            body = (page.inner_text("body") or "")
        except Exception:
            pass
        said = LOGIN_ERROR_RE.search(body)
        said_text = " ".join(said.group(0).split())[:200] if said else ""
        findings.append(Finding(
            severity="critical", category="Authentication",
            title="Login with the supplied test account failed",
            detail="After submitting the credentials the bot was still on a page with a "
                   "password field (or the success condition was not met). Everything behind "
                   "the login therefore went untested."
                   + (f" The site said: \"{_scrub(said_text, cfg)}\"" if said_text else ""),
            url=page.url,
            evidence={"page_text_excerpt": _scrub(body[:600], cfg), "final_url": page.url,
                      "username": cfg.username},
            how_to_fix="Check the username and password, or pass --login-success-url / "
                       "--login-success-text so the bot can recognise a successful login. "
                       "Two-step verification and CAPTCHAs on the login stop the bot.",
        ))
        return False, findings, ("login failed: " + _scrub(said_text, cfg)) if said_text \
            else "login not confirmed"

    return True, findings, f"logged in as {cfg.username}"


def _verify(page, cfg: Config, before_url: str) -> bool:
    if cfg.login_success_url:
        return cfg.login_success_url.lower() in page.url.lower()
    if cfg.login_success_text:
        try:
            return cfg.login_success_text.lower() in (page.inner_text("body") or "").lower()
        except Exception:
            return False
    # default heuristic: the password field is gone, or we left the login page
    try:
        if page.locator("input[type='password']:visible").count() == 0:
            return True
    except Exception:
        pass
    return page.url.split("#")[0].rstrip("/") != before_url.split("#")[0].rstrip("/")


def _path(url: str) -> str:
    try:
        return (urlparse(url).path or "/").rstrip("/").lower() or "/"
    except ValueError:
        return ""


def is_logged_out(page, requested_url: str = "", login_url: str = "") -> bool:
    """Detect that the session was lost mid-crawl: the site sent us to its login
    page. A page that merely contains a password field (sign-up, change password)
    is not a sign of that."""
    try:
        if page.locator("input[type='password']:visible").count() == 0:
            return False
    except Exception:
        return False
    here = _path(page.url)
    if login_url and here == _path(login_url) and _path(requested_url) != here:
        return True
    if requested_url and here != _path(requested_url):
        return bool(re.search(r"log-?in|sign-?in|auth", here))
    return False
