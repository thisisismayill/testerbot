"""Logging the bot into the site under test."""
from __future__ import annotations

from typing import List, Optional, Tuple

from .config import Config
from .models import Finding

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


def login(page, cfg: Config, base_url: str) -> Tuple[bool, List[Finding], str]:
    """Perform the login. Returns (ok, findings, message)."""
    findings: List[Finding] = []
    if not cfg.username and not cfg.password:
        return False, findings, "no credentials supplied"

    target = find_login_page(page, base_url, cfg)
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
        page.wait_for_timeout(cfg.settle_ms)
    except Exception as exc:
        findings.append(Finding(
            severity="critical", category="Authentication",
            title="Login page failed to load",
            detail=str(exc)[:400], url=target,
        ))
        return False, findings, "login page failed to load"

    pass_loc = (page.locator(cfg.pass_selector).first if cfg.pass_selector
                else page.locator("input[type='password']").first)
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
        return False, findings, f"could not fill credentials: {exc}"

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
            return False, findings, f"could not submit login form: {exc}"

    try:
        page.wait_for_load_state("networkidle", timeout=cfg.nav_timeout_ms)
    except Exception:
        pass
    page.wait_for_timeout(cfg.settle_ms)

    ok = _verify(page, cfg, before_url)
    if not ok:
        body = ""
        try:
            body = (page.inner_text("body") or "")[:600]
        except Exception:
            pass
        findings.append(Finding(
            severity="critical", category="Authentication",
            title="Login with the supplied test account failed",
            detail="After submitting the credentials the bot was still on a page with a "
                   "password field (or the success condition was not met). Everything behind "
                   "the login therefore went untested.",
            url=page.url,
            evidence={"page_text_excerpt": body, "final_url": page.url},
            how_to_fix="Check the credentials, or pass --login-success-url / --login-success-text "
                       "so the bot can recognise a successful login.",
        ))
        return False, findings, "login not confirmed"

    return True, findings, f"logged in as {cfg.username}"


def _verify(page, cfg: Config, before_url: str) -> bool:
    if cfg.login_success_url:
        return cfg.login_success_url.lower() in page.url.lower()
    if cfg.login_success_text:
        try:
            return cfg.login_success_text.lower() in (page.inner_text("body") or "").lower()
        except Exception:
            return False
    # default heuristic: password field gone, or we navigated away from the login page
    try:
        if page.locator("input[type='password']").count() == 0:
            return True
    except Exception:
        pass
    return page.url.rstrip("/") != before_url.rstrip("/")


def is_logged_out(page) -> bool:
    """Detect that the session was lost mid-crawl."""
    try:
        if page.locator("input[type='password']").count() > 0:
            return True
    except Exception:
        pass
    return False
