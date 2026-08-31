"""Clicking things and filling forms - the part that behaves like a manual tester."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import Config
from .models import Finding
from .recorder import Recorder

FINGERPRINT_JS = """
() => ({
  url: location.href,
  html: document.body ? document.body.innerHTML.length : 0,
  text: document.body ? (document.body.innerText || '').length : 0,
  dialogs: document.querySelectorAll(
    "[role='dialog'],dialog[open],.modal.show,.modal.in,[aria-modal='true'],.offcanvas.show").length,
  scrollY: Math.round(window.scrollY),
  focus: document.activeElement ? document.activeElement.tagName : ''
})
"""

WIDE_ELEMENTS_JS = """
(vw) => {
  const out = [];
  const walk = document.querySelectorAll('body *');
  for (const el of walk) {
    const r = el.getBoundingClientRect();
    if (r.width > vw + 4 && r.height > 0) {
      let sel = el.tagName.toLowerCase();
      if (el.id) sel += '#' + el.id;
      const c = (el.getAttribute('class') || '').trim().split(/\\s+/)[0];
      if (c) sel += '.' + c;
      out.push({ selector: sel, width: Math.round(r.width),
                 right: Math.round(r.right), text: (el.innerText || '').trim().slice(0, 60) });
      if (out.length > 12) break;
    }
  }
  return out;
}
"""

ERROR_TEXT_RE = re.compile(
    r"(\berror\b|failed|failure|invalid|exception|something went wrong|try again|"
    r"\bwrong\b|incorrect|do(es)? not match|required|must be|not found|"
    r"x[əe]ta|s[əe]hv|al[ıi]nmad[ıi]|yanl[ıi][şs]|ошибка|не удалось|неверн)", re.I)
SUCCESS_TEXT_RE = re.compile(
    r"(thank you|success|sent|received|submitted|saved|təşəkkür|göndərildi|uğurla|успешно)", re.I)

ESCAPE_MARKER = "TBQA7"
ESCAPE_PAYLOAD = f"<b>{ESCAPE_MARKER}</b>"


# ====================================================================== clicks

def click_everything(page, cfg: Config, rec: Recorder, url: str,
                     clickables: List[Dict[str, Any]], tested: Set[str],
                     shot) -> Tuple[List[Finding], int]:
    """Click every safe interactive element on the page."""
    findings: List[Finding] = []
    danger = cfg.danger_re()
    clicked = 0

    for item in clickables:
        if clicked >= cfg.max_clicks_per_page:
            break
        text = (item.get("text") or "").strip()
        sig = f"{item.get('tag')}|{item.get('selector')}|{text[:40]}"
        if sig in tested:
            continue
        if item.get("disabled"):
            tested.add(sig)
            continue
        if item.get("inForm") and item.get("type") in ("submit", "") \
                and item.get("tag") in ("button", "input"):
            tested.add(sig)          # the form engine submits this properly
            continue
        blob = f"{text} {item.get('html', '')}"
        if not cfg.danger_mode and danger.search(blob):
            tested.add(sig)
            findings.append(Finding(
                severity="info", category="Skipped",
                title=f"Destructive-looking control not clicked: '{text[:50] or item['tag']}'",
                detail="TesterBot avoids controls that look like delete / pay / logout so it "
                       "cannot damage real data. Re-run with --danger-mode on a staging copy "
                       "to include them.",
                url=url, element=item.get("selector"),
                evidence={"html": item.get("html", "")[:200]}))
            continue
        tested.add(sig)

        try:
            loc = page.locator(item["selector"]).first
            if not loc.count() or not loc.is_visible():
                continue
        except Exception:
            continue

        before = _fingerprint(page)
        mark = rec.mark()
        popups_before = len(rec.popups)
        downloads_before = len(rec.downloads)

        try:
            loc.scroll_into_view_if_needed(timeout=2500)
        except Exception:
            pass
        try:
            loc.click(timeout=4000, no_wait_after=True)
            clicked += 1
        except Exception as exc:
            msg = str(exc).split("\n")[0][:200]
            if "intercept" in msg.lower() or "not visible" in msg.lower() \
                    or "outside of the viewport" in msg.lower():
                findings.append(Finding(
                    severity="medium", category="Interaction",
                    title=f"Control cannot be clicked: '{text[:50] or item['tag']}'",
                    detail="Playwright could not click this element - it is covered by another "
                           "element, off-screen or otherwise unreachable. Real users with the "
                           "same viewport are likely blocked too.",
                    url=url, element=item.get("selector"),
                    evidence={"error": msg, "html": item.get("html", "")[:200]},
                    how_to_fix="Check z-index / overlays / sticky headers covering this control."))
            continue

        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass
        page.wait_for_timeout(400)

        delta = rec.delta(mark)
        after = _fingerprint(page)
        navigated = after.get("url") != before.get("url")
        new_popup = len(rec.popups) > popups_before
        new_download = len(rec.downloads) > downloads_before
        dom_changed = (abs(after.get("html", 0) - before.get("html", 0)) > 12
                       or abs(after.get("text", 0) - before.get("text", 0)) > 6
                       or after.get("dialogs", 0) != before.get("dialogs", 0)
                       or abs(after.get("scrollY", 0) - before.get("scrollY", 0)) > 30)
        net_activity = any(r["resource_type"] in ("xhr", "fetch", "document")
                           for r in delta["responses"])

        for err in delta["page_errors"]:
            findings.append(Finding(
                severity="critical", category="JavaScript Error",
                title=f"Clicking '{text[:45] or item['tag']}' throws: {err['message'][:80]}",
                detail="A JavaScript exception was raised as a direct result of clicking this "
                       "control, so the feature behind it is broken.",
                url=url, element=item.get("selector"),
                evidence={"message": err["message"][:1200], "stack": err.get("stack", "")[:1200],
                          "control_html": item.get("html", "")[:200]},
                screenshot=shot(f"click-error-{item.get('tag')}"),
                how_to_fix="Reproduce by clicking this control with DevTools open."))
        for resp in delta["responses"]:
            if resp["status"] >= 500:
                findings.append(Finding(
                    severity="critical", category="Server Error",
                    title=f"Clicking '{text[:40] or item['tag']}' returns HTTP {resp['status']}",
                    detail="The request triggered by this control failed on the server.",
                    url=url, element=item.get("selector"),
                    evidence={"request": resp["url"], "status": resp["status"],
                              "method": resp.get("method")},
                    how_to_fix="Check the server logs for this endpoint."))
            elif resp["status"] in (401, 403, 404) and resp["resource_type"] in ("xhr", "fetch"):
                findings.append(Finding(
                    severity="high", category="Network",
                    title=f"Clicking '{text[:40] or item['tag']}' calls a "
                          f"{resp['status']} endpoint",
                    detail="The API call behind this control does not succeed.",
                    url=url, element=item.get("selector"),
                    evidence={"request": resp["url"], "status": resp["status"]}))
        for dlg in delta["dialogs"]:
            findings.append(Finding(
                severity="low", category="UX",
                title=f"Native browser dialog ({dlg['type']}) opened by "
                      f"'{text[:40] or item['tag']}'",
                detail=f"Message: {dlg['message'][:200]}. Native alert/confirm dialogs block the "
                       "page and cannot be styled or tested well.",
                url=url, element=item.get("selector"),
                how_to_fix="Replace alert()/confirm() with an in-page dialog component."))

        if not (navigated or dom_changed or net_activity or new_popup or new_download
                or delta["dialogs"] or delta["page_errors"]):
            findings.append(Finding(
                severity="low", category="Dead Control",
                title=f"Control appears to do nothing: '{text[:50] or item['tag']}'",
                detail="After clicking, the URL, the DOM, the network and the console were all "
                       "unchanged. Either the handler is missing or the effect is invisible "
                       "(e.g. copy-to-clipboard). Worth a manual look.",
                url=url, element=item.get("selector"),
                evidence={"html": item.get("html", "")[:200]},
                screenshot=shot("dead-control"),
                how_to_fix="Confirm the control has a working handler."))

        if navigated:
            try:
                page.go_back(timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
            except Exception:
                try:
                    page.goto(url, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
                except Exception:
                    return findings, clicked
            page.wait_for_timeout(300)
        elif after.get("dialogs", 0) > before.get("dialogs", 0):
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
            except Exception:
                pass

    return findings, clicked


def _fingerprint(page) -> Dict[str, Any]:
    try:
        return page.evaluate(FINGERPRINT_JS)
    except Exception:
        return {}


# ====================================================================== forms

def test_forms(page, cfg: Config, rec: Recorder, url: str, forms: List[Dict[str, Any]],
               tested: Set[str], shot) -> Tuple[List[Finding], int]:
    findings: List[Finding] = []
    danger = cfg.danger_re()
    count = 0

    for form in forms:
        if count >= cfg.max_forms_per_page:
            break
        if not form.get("visible"):
            continue
        fields = [f for f in form["fields"]
                  if f["visible"] and f["type"] not in ("hidden", "submit", "button", "reset")]
        if not fields:
            continue
        sig = form.get("signature") or form.get("selector")
        if sig in tested:
            continue
        tested.add(sig)

        blob = f"{form.get('submitText', '')} {form.get('action') or ''} {form.get('id', '')}"
        if not cfg.danger_mode and danger.search(blob):
            findings.append(Finding(
                severity="info", category="Skipped",
                title=f"Form not submitted (looks destructive/transactional): "
                      f"{form.get('submitText') or form.get('action') or form.get('selector')}",
                detail="TesterBot does not submit forms that look like payment, deletion or "
                       "account changes. Use --danger-mode on a staging copy to include them.",
                url=url, element=form.get("selector")))
            continue

        count += 1
        if not form.get("hasSubmit"):
            findings.append(Finding(
                severity="low", category="Forms",
                title="Form has no submit button",
                detail="The form can only be submitted by pressing Enter, which many users "
                       "and all keyboard-only flows will miss.",
                url=url, element=form.get("selector"),
                how_to_fix="Add a <button type=\"submit\">."))
        if form.get("novalidate"):
            findings.append(Finding(
                severity="info", category="Forms",
                title="Form has novalidate - browser validation is switched off",
                detail="Make sure custom JS validation covers everything the browser would have.",
                url=url, element=form.get("selector")))

        required = [f for f in fields if f["required"]]
        if not required and len(fields) > 1 and not _is_search_form(form, fields):
            findings.append(Finding(
                severity="medium", category="Forms",
                title="Form has no required fields at all",
                detail="None of the inputs are marked required, so a completely empty "
                       "submission is accepted by the browser.",
                url=url, element=form.get("selector"),
                evidence={"fields": [f["name"] or f["type"] for f in fields][:12]},
                how_to_fix="Mark the mandatory inputs with the required attribute."))

        if not cfg.submit_forms:
            continue
        if form.get("hasPassword") and "signup" not in blob.lower():
            # avoid brute-forcing login forms we did not get credentials for
            pass

        # ---- 1. empty submission -------------------------------------
        if required:
            findings += _submit_case(page, cfg, rec, url, form, fields, shot,
                                     mode="empty")
        # ---- 2. invalid email ----------------------------------------
        if any(f["type"] == "email" for f in fields):
            findings += _submit_case(page, cfg, rec, url, form, fields, shot,
                                     mode="bad_email")
        # ---- 3. valid data (also checks output escaping) --------------
        findings += _submit_case(page, cfg, rec, url, form, fields, shot, mode="valid")

    return findings, count


def _is_search_form(form: Dict[str, Any], fields: List[Dict[str, Any]]) -> bool:
    blob = f"{form.get('action') or ''} {form.get('id', '')} {form.get('name', '')} " \
           f"{' '.join(f['name'] for f in fields)}"
    return bool(re.search(r"search|axtar|поиск|filter|query", blob, re.I)) or \
        any(f["type"] == "search" for f in fields)


def _submit_case(page, cfg: Config, rec: Recorder, url: str, form: Dict[str, Any],
                 fields: List[Dict[str, Any]], shot, mode: str) -> List[Finding]:
    findings: List[Finding] = []
    label = {"empty": "empty submission", "bad_email": "invalid e-mail",
             "valid": "valid test data"}[mode]

    try:
        page.goto(url, timeout=cfg.nav_timeout_ms, wait_until="domcontentloaded")
        page.wait_for_timeout(cfg.settle_ms // 2)
    except Exception:
        return findings

    try:
        form_loc = page.locator(form["selector"]).first
        if not form_loc.count():
            return findings
    except Exception:
        return findings

    marker_used = False
    if mode != "empty":
        marker_used = _fill_form(page, cfg, form, fields, bad_email=(mode == "bad_email"))

    mark = rec.mark()
    before_url = page.url
    valid_before = _form_validity(page, form["selector"])
    bypassed = False
    if mode == "empty" and valid_before is False:
        # the browser blocks this submission - strip the client-side rules and see
        # whether the SERVER also rejects it
        bypassed = _disable_client_validation(page, form["selector"])

    try:
        _submit(page, cfg, form)
    except Exception as exc:
        findings.append(Finding(
            severity="medium", category="Forms",
            title=f"Form could not be submitted ({label})",
            detail=str(exc)[:300], url=url, element=form.get("selector")))
        return findings

    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass
    page.wait_for_timeout(600)

    delta = rec.delta(mark)
    navigated = page.url != before_url
    posts = [r for r in delta["responses"]
             if r["resource_type"] in ("xhr", "fetch", "document")
             and r["method"] in ("POST", "PUT", "PATCH", "GET")]
    server_errors = [r for r in delta["responses"] if r["status"] >= 500]
    client_errors = [r for r in delta["responses"]
                     if 400 <= r["status"] < 500 and r["resource_type"] in ("xhr", "fetch", "document")]
    body_text = ""
    try:
        body_text = (page.inner_text("body") or "")[:4000]
    except Exception:
        pass
    shows_error = bool(ERROR_TEXT_RE.search(body_text))
    accepted = navigated or (bool(posts) and not shows_error and not client_errors)

    for err in delta["page_errors"]:
        findings.append(Finding(
            severity="critical", category="JavaScript Error",
            title=f"Submitting the form ({label}) throws: {err['message'][:80]}",
            url=url, element=form.get("selector"),
            detail="Submitting this form raises an unhandled JavaScript exception.",
            evidence={"message": err["message"][:1200], "mode": label},
            screenshot=shot(f"form-{mode}-error")))
    for resp in server_errors:
        findings.append(Finding(
            severity="critical", category="Server Error",
            title=f"Form submission returns HTTP {resp['status']} ({label})",
            url=url, element=form.get("selector"),
            detail="The server failed while processing this form submission.",
            evidence={"request": resp["url"], "status": resp["status"],
                      "method": resp.get("method")},
            screenshot=shot(f"form-{mode}-5xx"),
            how_to_fix="Check the server-side handler and its logs."))

    if mode == "empty":
        if bypassed and accepted:
            findings.append(Finding(
                severity="high", category="Forms",
                title="Server accepts an empty submission (validation is browser-side only)",
                detail="The browser's own required-field check was removed and the same empty "
                       "submission was then accepted by the server. Anyone using a script, a "
                       "modified page or an old browser can post empty/garbage records.",
                url=url, element=form.get("selector"),
                evidence={"required_fields": [f["name"] or f["type"]
                                              for f in fields if f["required"]][:10],
                          "final_url": page.url},
                screenshot=shot("form-server-no-validation"),
                how_to_fix="Validate every required field on the server, not only in HTML."))
        elif bypassed:
            pass  # server rejected it - correct behaviour
        elif valid_before is False and not navigated and not posts:
            pass  # browser validation blocked it - correct behaviour
        elif accepted:
            findings.append(Finding(
                severity="high", category="Forms",
                title="Form accepts a completely empty submission",
                detail="Required fields were left blank and the form still submitted "
                       "successfully - validation is missing or is client-side only.",
                url=url, element=form.get("selector"),
                evidence={"required_fields": [f["name"] or f["type"]
                                              for f in fields if f["required"]][:10],
                          "navigated_to": page.url if navigated else None},
                screenshot=shot("form-empty-accepted"),
                how_to_fix="Validate required fields on the server as well as in the browser."))
        elif not shows_error and not navigated and not posts and valid_before is not False:
            findings.append(Finding(
                severity="medium", category="Forms",
                title="Empty submission is silently ignored",
                detail="Nothing happened and no error message was shown, so the user gets "
                       "no feedback about what is wrong.",
                url=url, element=form.get("selector"),
                screenshot=shot("form-empty-silent"),
                how_to_fix="Show a visible validation message when the form is incomplete."))

    elif mode == "bad_email":
        if accepted:
            findings.append(Finding(
                severity="medium", category="Forms",
                title="Form accepts an invalid e-mail address",
                detail="'not-an-email' was accepted without complaint.",
                url=url, element=form.get("selector"),
                evidence={"value_used": "not-an-email"},
                screenshot=shot("form-bad-email"),
                how_to_fix="Validate the e-mail format on the client and the server."))

    elif form.get("hasPassword"):
        # a credentials form fed with fake data: it MUST reject them
        still_has_password = False
        try:
            still_has_password = page.locator("input[type='password']").count() > 0
        except Exception:
            pass
        if not shows_error and not still_has_password and navigated:
            findings.append(Finding(
                severity="critical", category="Authentication",
                title="Credentials form accepted made-up login details",
                detail="TesterBot submitted an invented username and password and the site let "
                       "it through instead of rejecting them.",
                url=url, element=form.get("selector"),
                evidence={"username_used": "testerbot_qa / testerbot.qa@example.com",
                          "landed_on": page.url},
                screenshot=shot("login-accepts-anything"),
                how_to_fix="Verify credentials server-side before establishing a session."))
        elif not shows_error and not navigated and not posts:
            findings.append(Finding(
                severity="medium", category="Forms",
                title="Login form gives no feedback for wrong credentials",
                detail="Submitting invalid credentials produced no error message, no navigation "
                       "and no request. The user is left guessing.",
                url=url, element=form.get("selector"),
                screenshot=shot("login-no-feedback"),
                how_to_fix="Show a clear 'incorrect username or password' message."))

    else:  # valid
        if not navigated and not posts and not delta["dialogs"] and not shows_error \
                and not SUCCESS_TEXT_RE.search(body_text):
            findings.append(Finding(
                severity="high", category="Forms",
                title="Form does nothing when submitted with valid data",
                detail="No navigation, no network request and no message appeared. The form "
                       "looks non-functional.",
                url=url, element=form.get("selector"),
                evidence={"fields": [f["name"] or f["type"] for f in fields][:12]},
                screenshot=shot("form-noop"),
                how_to_fix="Wire the form up to its handler / endpoint."))
        elif shows_error and not client_errors and not server_errors:
            excerpt = _error_excerpt(body_text)
            findings.append(Finding(
                severity="medium", category="Forms",
                title="Valid test data produces an error message",
                detail="The bot filled every field with plausible values and the form still "
                       "reported an error. Either validation is too strict or the flow is broken.",
                url=url, element=form.get("selector"),
                evidence={"message": excerpt},
                screenshot=shot("form-valid-error")))
        for resp in client_errors:
            findings.append(Finding(
                severity="medium", category="Forms",
                title=f"Form submission returns HTTP {resp['status']}",
                url=url, element=form.get("selector"),
                evidence={"request": resp["url"], "status": resp["status"]},
                detail="The endpoint rejected a submission filled with valid-looking data."))

        if marker_used:
            findings += _check_escaping(page, url, form)

    return findings


def _error_excerpt(text: str) -> str:
    m = ERROR_TEXT_RE.search(text)
    if not m:
        return text[:200]
    start = max(0, m.start() - 80)
    return text[start:start + 240].replace("\n", " ")


def _disable_client_validation(page, selector: str) -> bool:
    """Remove required/pattern/novalidate so the request actually reaches the server."""
    try:
        return bool(page.evaluate(
            "(sel) => { const f = document.querySelector(sel); if (!f) return false;"
            " f.setAttribute('novalidate','');"
            " f.querySelectorAll('[required]').forEach(e => e.removeAttribute('required'));"
            " f.querySelectorAll('[pattern]').forEach(e => e.removeAttribute('pattern'));"
            " f.querySelectorAll('[minlength]').forEach(e => e.removeAttribute('minlength'));"
            " return true; }", selector))
    except Exception:
        return False


def _form_validity(page, selector: str) -> Optional[bool]:
    try:
        return page.evaluate(
            "(sel) => { const f = document.querySelector(sel);"
            " return f && f.checkValidity ? f.checkValidity() : null; }", selector)
    except Exception:
        return None


def _fill_form(page, cfg: Config, form: Dict[str, Any], fields: List[Dict[str, Any]],
               bad_email: bool = False) -> bool:
    """Fill every field with plausible data. Returns True if the escaping marker was used."""
    marker_used = False
    radio_groups: Set[str] = set()
    for field in fields:
        ftype = field["type"]
        sel = field["selector"]
        if ftype in ("file", "color", "range", "image", "reset", "submit", "button"):
            continue
        try:
            loc = page.locator(sel).first
            if not loc.count() or not loc.is_visible():
                continue
        except Exception:
            continue
        try:
            if ftype == "checkbox":
                loc.check(timeout=2500)
            elif ftype == "radio":
                name = field.get("name") or sel
                if name in radio_groups:
                    continue
                radio_groups.add(name)
                loc.check(timeout=2500)
            elif ftype == "select" or ftype == "select-one" or ftype == "select-multiple":
                values = page.evaluate(
                    "(s)=>{const e=document.querySelector(s); return e? Array.from(e.options)"
                    ".filter(o=>o.value!=='').map(o=>o.value):[]}", sel)
                if values:
                    loc.select_option(values[0], timeout=2500)
            else:
                value, is_marker = _value_for(field, bad_email)
                if value is None:
                    continue
                maxlen = field.get("maxlength")
                if maxlen and str(maxlen).isdigit():
                    value = value[: int(maxlen)]
                    if is_marker and len(value) < len(ESCAPE_PAYLOAD):
                        is_marker = False
                loc.fill(value, timeout=2500)
                marker_used = marker_used or is_marker
        except Exception:
            continue
    return marker_used


TEXT_HINTS = [
    (r"\b(cvv|cvc|iban|card[_ -]?number|cardnumber|creditcard|expiry|expiration)\b", None),
    (r"\b(user ?name|nickname|istifad[\u0259e][\u00e7c]i)\b", "testerbot_qa"),
    (r"\b(first[_ -]?name|given[_ -]?name|firstname|fname)\b", "Tester"),
    (r"\b(last[_ -]?name|sur ?name|family[_ -]?name|lastname|lname|soyad)\b", "Botov"),
    (r"\b(full[_ -]?name|your ?name|name|ad soyad)\b", "Tester Botov"),
    (r"\b(compan(y|ies)|organi[sz]ation|[\u015fs]irk[\u0259e]t)\b", "TesterBot QA"),
    (r"\b(phone|tel|mobile|mobil|n[\u00f6o]mr[\u0259e])\b", "+994501234567"),
    (r"\b(zip|post(al)?[_ -]?code|postcode|indeks)\b", "10001"),
    (r"\b(city|town|[\u015fs][\u0259e]h[\u0259e]r)\b", "Baku"),
    (r"\b(country|[\u00f6o]lk[\u0259e])\b", "Azerbaijan"),
    (r"\b(address|street|[\u00fcu]nvan)\b", "12 Test Street, Apt 4"),
    (r"\b(subject|topic|m[\u00f6o]vzu)\b", "TesterBot automated check"),
    (r"\b(age|ya[\u015fs])\b", "30"),
    (r"\b(quantity|qty|amount|say|miqdar)\b", "2"),
]


def _value_for(field: Dict[str, Any], bad_email: bool) -> Tuple[Optional[str], bool]:
    ftype = field["type"]
    blob = f"{field.get('name', '')} {field.get('id', '')} {field.get('placeholder', '')}"
    if ftype == "email":
        return ("not-an-email" if bad_email else "testerbot.qa@example.com"), False
    if ftype == "password":
        return "TesterBot!2026", False
    if ftype == "tel":
        return "+994501234567", False
    if ftype == "url":
        return "https://example.com", False
    if ftype == "number":
        return "3", False
    if ftype == "date":
        return "2026-06-15", False
    if ftype == "time":
        return "12:30", False
    if ftype == "datetime-local":
        return "2026-06-15T12:30", False
    if ftype == "month":
        return "2026-06", False
    if ftype == "week":
        return "2026-W24", False
    for pattern, value in TEXT_HINTS:
        if re.search(pattern, blob, re.I):
            return value, False
    if field.get("pattern"):
        return "TesterBot", False
    if ftype == "textarea":
        return (f"Automated QA check by TesterBot. {ESCAPE_PAYLOAD}"), True
    if ftype in ("text", "search", ""):
        return (f"TesterBot {ESCAPE_PAYLOAD}"), True
    return "TesterBot", False


def _submit(page, cfg: Config, form: Dict[str, Any]) -> None:
    sel = form["selector"]
    btn = page.locator(f"{sel} button[type='submit'], {sel} input[type='submit'], "
                       f"{sel} button:not([type='button']):not([type='reset'])").first
    if btn.count() and btn.is_visible():
        btn.click(timeout=5000, no_wait_after=True)
        return
    page.evaluate(
        "(s)=>{const f=document.querySelector(s); if(!f) return;"
        " if (f.requestSubmit) f.requestSubmit(); else f.submit();}", sel)


def _check_escaping(page, url: str, form: Dict[str, Any]) -> List[Finding]:
    """Did our <b>marker</b> come back rendered as real HTML?"""
    try:
        rendered = page.evaluate(
            "(m)=>{const els=document.querySelectorAll('b,i,strong,em');"
            " for(const e of els){ if((e.textContent||'').includes(m)) return e.outerHTML.slice(0,200);} "
            " return null;}", ESCAPE_MARKER)
    except Exception:
        return []
    if rendered:
        return [Finding(
            severity="high", category="Security",
            title="User input is rendered as raw HTML (output not escaped)",
            detail="TesterBot submitted the literal text '<b>TBQA7</b>' and the page rendered it "
                   "as a real bold element instead of showing it as text. Anything a user types "
                   "can therefore inject markup into the page.",
            url=url, element=form.get("selector"),
            evidence={"submitted": ESCAPE_PAYLOAD, "rendered_back_as": rendered},
            how_to_fix="HTML-escape user input before rendering it, or bind it as text content "
                       "rather than innerHTML.")]
    return []
