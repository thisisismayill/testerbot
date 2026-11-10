"""Attaches to a Playwright page and records everything the browser reports."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


class Recorder:
    def __init__(self) -> None:
        self.console: List[Dict[str, Any]] = []
        self.page_errors: List[Dict[str, Any]] = []
        self.failed: List[Dict[str, Any]] = []
        self.responses: List[Dict[str, Any]] = []
        self.dialogs: List[Dict[str, Any]] = []
        self.popups: List[str] = []
        self.downloads: List[str] = []
        self._errors: Dict[Any, Any] = {}     # (url, status) -> failed API response
        self._page = None

    # -- lifecycle -----------------------------------------------------
    def attach(self, page) -> None:
        self._page = page
        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)
        page.on("requestfailed", self._on_request_failed)
        page.on("response", self._on_response)
        page.on("dialog", self._on_dialog)
        page.on("download", self._on_download)

    def attach_context(self, context) -> None:
        context.on("page", self._on_popup)

    def reset(self) -> None:
        self.console.clear()
        self.page_errors.clear()
        self.failed.clear()
        self.responses.clear()
        self.dialogs.clear()
        self.popups.clear()
        self.downloads.clear()
        self._errors.clear()

    # -- handlers ------------------------------------------------------
    def _on_console(self, msg) -> None:
        try:
            loc = msg.location or {}
            self.console.append({
                "type": msg.type,
                "text": (msg.text or "")[:2000],
                "location": f"{loc.get('url', '')}:{loc.get('lineNumber', '')}",
            })
        except Exception:
            pass

    def _on_page_error(self, err) -> None:
        try:
            message = getattr(err, "message", None) or str(err)
            stack = getattr(err, "stack", "") or ""
            self.page_errors.append({"message": message[:2000], "stack": stack[:3000]})
        except Exception:
            pass

    def _on_request_failed(self, request) -> None:
        try:
            failure = request.failure
            if failure and "ERR_ABORTED" in str(failure):
                return
            self.failed.append({
                "url": request.url, "method": request.method,
                "resource_type": request.resource_type,
                "failure": str(failure)[:300] if failure else "unknown",
            })
        except Exception:
            pass

    def _on_response(self, response) -> None:
        try:
            size = 0
            try:
                headers = response.headers
                size = int(headers.get("content-length", 0) or 0)
            except Exception:
                pass
            self.responses.append({
                "url": response.url, "status": response.status,
                "method": response.request.method,
                "resource_type": response.request.resource_type,
                "size": size,
            })
            if response.status >= 400 and response.request.resource_type in ("xhr", "fetch"):
                if len(self._errors) < 60:
                    self._errors[(response.url, response.status)] = response
        except Exception:
            pass

    def _on_dialog(self, dialog) -> None:
        try:
            self.dialogs.append({"type": dialog.type, "message": (dialog.message or "")[:500]})
            dialog.dismiss()
        except Exception:
            pass

    def _on_download(self, download) -> None:
        try:
            self.downloads.append(download.url)
            download.cancel()
        except Exception:
            pass

    def _on_popup(self, page) -> None:
        # fires for our own main page too - never close that one
        if self._page is not None and page == self._page:
            return
        try:
            self.popups.append(page.url)
            page.close()
        except Exception:
            pass

    # -- query ---------------------------------------------------------
    def mark(self) -> Tuple[int, int, int, int, int]:
        return (len(self.console), len(self.page_errors), len(self.failed),
                len(self.responses), len(self.dialogs))

    def delta(self, mark: Tuple[int, int, int, int, int]) -> Dict[str, List[Dict[str, Any]]]:
        c, p, f, r, d = mark
        return {
            "console": self.console[c:],
            "page_errors": self.page_errors[p:],
            "failed": self.failed[f:],
            "responses": self.responses[r:],
            "dialogs": self.dialogs[d:],
        }

    def bad_responses(self, ignore_urls: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        ignore = set(ignore_urls or [])
        seen = set()
        out = []
        for resp in self.responses:
            if resp["status"] < 400 or resp["url"] in ignore:
                continue
            key = (resp["url"], resp["status"])
            if key in seen:
                continue
            seen.add(key)
            out.append(resp)
        return out

    def body_of(self, resp: Dict[str, Any], limit: int = 300) -> str:
        """The start of a failed API call's answer - it usually says what was wrong
        ("date_from is required", "account not verified"). Tokens are blanked out."""
        obj = self._errors.get((resp.get("url"), resp.get("status")))
        if obj is None:
            return ""
        try:
            text = obj.text()
        except Exception:
            return ""
        text = re.sub(r"eyJ[\w-]+\.[\w-]+\.[\w-]*", "<token>", " ".join((text or "").split()))
        return text[:limit]

    def weight_kb(self) -> float:
        return sum(r.get("size", 0) for r in self.responses) / 1024.0
