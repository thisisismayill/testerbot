#!/usr/bin/env python3
"""
TesterBot - graphical interface (opens in the browser, no terminal needed).

    python3 testerbot_ui.py

Opens http://localhost:8777 in the browser: type a link, press "Start test".
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ui_page import PAGE  # noqa: E402

REPORTS = os.path.join(HERE, "reports")
STATE_FILE = os.path.join(HERE, ".testerbot-ui.json")
DEFAULT_PORT = 8777
MAX_LOG = 4000


# ---------------------------------------------------------------- run state
class Runner:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lines: list[str] = []
        self.proc: subprocess.Popen | None = None
        self.status = "idle"          # idle | running | done | error | stopped
        self.error = ""
        self.progress = ""
        self.out_dir = ""
        self.summary = None
        self.intel_summary = None
        self.index_summary = None
        self.mode = "qa"
        self.report_url = ""

    # -- helpers
    def _log(self, line: str) -> None:
        with self.lock:
            self.lines.append(line.rstrip("\n"))
            if len(self.lines) > MAX_LOG:
                del self.lines[: len(self.lines) - MAX_LOG]
            m = re.match(r"\s*\[(\d+)/(\d+)\]", line)
            if m:
                self.progress = f"Checking page {m.group(1)} of {m.group(2)}…"
            elif line.startswith("→"):
                self.progress = line.strip()[:90]

    def snapshot(self, since: int) -> dict:
        with self.lock:
            lines = self.lines[since:]
            return {
                "lines": lines, "next": len(self.lines), "status": self.status,
                "error": self.error, "progress": self.progress,
                "summary": self.summary, "report": self.report_url,
                "intel": self.intel_summary,
                "index": self.index_summary,
                "mode": getattr(self, "mode", "qa"),
                "folder": self.out_dir.replace(os.path.expanduser("~"), "~") if self.out_dir else "",
            }

    # -- lifecycle
    def start(self, cfg: dict) -> str | None:
        if self.status == "running":
            return "A test is already running."
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # ---- index mode: crawl several domains into the growing link index
        if cfg.get("mode") == "index":
            domains = [d.strip() for d in (cfg.get("domains") or "").replace(",", "\n").splitlines()
                       if d.strip()]
            if not domains:
                return "Enter at least one domain."
            out_dir = os.path.join(REPORTS, f"{stamp}-index")
            os.makedirs(out_dir, exist_ok=True)
            cmd = [sys.executable, os.path.join(HERE, "tb_index.py"),
                   "--db", os.path.join(HERE, "testerbot-index.db"),
                   "--out", out_dir,
                   "--max-pages", str(int(cfg.get("max_pages") or 25)),
                   "--max-depth", str(int(cfg.get("max_depth") or 3))]
            if cfg.get("allow_subdomains"):
                cmd.append("--allow-subdomains")
            cmd += domains
            env = dict(os.environ)
            env["PYTHONUNBUFFERED"] = "1"
            with self.lock:
                self.lines, self.status, self.error = [], "running", ""
                self.progress, self.out_dir = "Building the index…", out_dir
                self.summary, self.report_url, self.intel_summary = None, "", None
                self.mode = "index"
            save_state(cfg)
            threading.Thread(target=self._run, args=(cmd, env, out_dir), daemon=True).start()
            return None

        # ---- QA mode
        url = (cfg.get("url") or "").strip()
        if not url:
            return "The site address is empty."
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        host = re.sub(r"[^a-z0-9.-]+", "-", (urlparse(url).netloc or "site").lower())
        out_dir = os.path.join(REPORTS, f"{stamp}-{host}")
        os.makedirs(out_dir, exist_ok=True)
        self.mode = "qa"

        cmd = [sys.executable, os.path.join(HERE, "tester_bot.py"), url,
               "--out", out_dir,
               "--max-pages", str(int(cfg.get("max_pages") or 40)),
               "--max-depth", str(int(cfg.get("max_depth") or 3))]
        if not cfg.get("submit_forms"):
            cmd.append("--no-forms")
        if not cfg.get("click_elements"):
            cmd.append("--no-click")
        if not cfg.get("check_external_links"):
            cmd.append("--no-external-links")
        if not cfg.get("run_axe"):
            cmd.append("--no-axe")
        if not cfg.get("responsive_checks"):
            cmd.append("--no-responsive")
        if not cfg.get("headless"):
            cmd.append("--headed")
        if cfg.get("screenshot_all"):
            cmd.append("--screenshot-all")
        if cfg.get("danger_mode"):
            cmd.append("--danger-mode")
        if not cfg.get("run_intelligence", True):
            cmd.append("--no-intel")
        if not cfg.get("run_performance", True):
            cmd.append("--no-perf")

        if cfg.get("include"):
            cmd += ["--include", cfg["include"]]
        if cfg.get("exclude"):
            cmd += ["--exclude", cfg["exclude"]]
        if cfg.get("username"):
            cmd += ["--username", cfg["username"]]
        if cfg.get("login_url"):
            cmd += ["--login-url", cfg["login_url"]]
        if cfg.get("login_success_url"):
            cmd += ["--login-success-url", cfg["login_success_url"]]

        env = dict(os.environ)
        if cfg.get("password"):
            env["TESTERBOT_PASS"] = cfg["password"]   # never on the command line
        if cfg.get("psi_key"):
            env["TESTERBOT_PSI_KEY"] = cfg["psi_key"]
        if cfg.get("opr_key"):
            env["TESTERBOT_OPR_KEY"] = cfg["opr_key"]
        env["PYTHONUNBUFFERED"] = "1"

        with self.lock:
            self.lines, self.status, self.error = [], "running", ""
            self.progress, self.out_dir = "Starting…", out_dir
            self.summary, self.report_url = None, ""
            self.intel_summary = None
        save_state(cfg)
        threading.Thread(target=self._run, args=(cmd, env, out_dir), daemon=True).start()
        return None

    def _run(self, cmd, env, out_dir) -> None:
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, bufsize=1, env=env, cwd=HERE)
        except Exception as exc:
            with self.lock:
                self.status, self.error = "error", f"The bot failed to start: {exc}"
            return
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self._log(line)
        code = self.proc.wait()
        base = os.path.basename(out_dir)

        # ---- index mode completion
        if getattr(self, "mode", "qa") == "index":
            data_path = os.path.join(out_dir, "index-data.json")
            ok = os.path.exists(os.path.join(out_dir, "index.html"))
            index_summary = None
            if os.path.exists(data_path):
                try:
                    with open(data_path, encoding="utf-8") as fh:
                        index_summary = json.load(fh).get("stats")
                except Exception:
                    index_summary = None
            with self.lock:
                if self.status == "stopped":
                    pass
                elif not ok:
                    self.status = "error"
                    self.error = ("The index was not created — check the log (this happens if a domain "
                                  "is wrong or will not open).")
                else:
                    self.status = "done"
                self.index_summary = index_summary
                if ok:
                    self.report_url = "/report/" + base + "/index.html"
                self.progress = ""
            return

        report = os.path.join(out_dir, "report.json")
        summary = None
        intel = None
        if os.path.exists(report):
            try:
                with open(report, encoding="utf-8") as fh:
                    rep = json.load(fh)
                summary = rep["summary"]
                intel = rep.get("intelligence")
            except Exception:
                summary = None
        with self.lock:
            if self.status == "stopped":
                pass
            elif summary is None:
                self.status = "error"
                self.error = ("No report was created. The log above says why "
                              "(a wrong address, a site that will not open, or no internet).")
            else:
                self.status = "done"
            self.summary = summary
            self.intel_summary = intel
            if os.path.exists(os.path.join(out_dir, "report.html")):
                self.report_url = "/report/" + base + "/report.html"
            self.progress = ""
        _ = code

    def stop(self) -> None:
        with self.lock:
            if self.status != "running":
                return
            self.status = "stopped"
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass


runner = Runner()


# ---------------------------------------------------------------- state file
def save_state(cfg: dict) -> None:
    keep = {k: cfg.get(k) for k in
            ("url", "max_pages", "max_depth", "login_url", "username", "login_success_url",
             "opr_key", "psi_key", "domains", "mode")}
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(keep, fh)
    except Exception:
        pass


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def list_runs(limit: int = 15) -> list:
    if not os.path.isdir(REPORTS):
        return []
    out = []
    for name in sorted(os.listdir(REPORTS), reverse=True):
        path = os.path.join(REPORTS, name, "report.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            sev = data["summary"].get("severity", {})
            out.append({
                "when": name[:8][:4] + "-" + name[4:6] + "-" + name[6:8] + " " +
                        name[9:11] + ":" + name[11:13],
                "target": data["meta"]["target"][:52],
                "pages": data["meta"]["pages_tested"],
                "total": data["summary"]["total"],
                "critical": sev.get("critical", 0), "high": sev.get("high", 0),
                "report": "/report/" + name + "/report.html",
            })
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, data: bytes, ctype: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # -- GET
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            return self._bytes(PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if path == "/api/state":
            return self._json({"last": load_state(), "running": runner.status == "running"})
        if path == "/api/log":
            since = int((parse_qs(parsed.query).get("since") or ["0"])[0] or 0)
            return self._json(runner.snapshot(since))
        if path == "/api/runs":
            return self._json({"runs": list_runs()})
        if path.startswith("/report/"):
            return self._serve_report(path[len("/report/"):])
        return self._bytes(b"Not found", "text/plain; charset=utf-8", 404)

    def _serve_report(self, rel: str):
        rel = rel.replace("\\", "/")
        if ".." in rel or rel.startswith("/"):
            return self._bytes(b"Forbidden", "text/plain", 403)
        full = os.path.abspath(os.path.join(REPORTS, rel))
        if not full.startswith(os.path.abspath(REPORTS)) or not os.path.isfile(full):
            return self._bytes(b"Not found", "text/plain", 404)
        ext = os.path.splitext(full)[1].lower()
        ctype = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8",
                 ".png": "image/png", ".jpg": "image/jpeg",
                 ".css": "text/css", ".js": "text/javascript"}.get(ext, "application/octet-stream")
        with open(full, "rb") as fh:
            return self._bytes(fh.read(), ctype)

    # -- POST
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            body = {}
        path = urlparse(self.path).path
        if path == "/api/run":
            err = runner.start(body)
            return self._json({"error": err} if err else {"ok": True})
        if path == "/api/stop":
            runner.stop()
            return self._json({"ok": True})
        if path == "/api/quit":
            runner.stop()
            self._json({"ok": True})
            threading.Timer(0.4, lambda: os._exit(0)).start()
            return
        return self._json({"error": "unknown endpoint"}, 404)


def find_port(start: int) -> int:
    import socket
    for port in range(start, start + 25):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def already_running(port: int) -> bool:
    """Another TesterBot window is already open on this port."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> None:
    os.makedirs(REPORTS, exist_ok=True)
    open_browser = "--no-browser" not in sys.argv

    if already_running(DEFAULT_PORT):
        url = f"http://localhost:{DEFAULT_PORT}"
        print(f"TesterBot is already running: {url}")
        if open_browser:
            webbrowser.open(url)
        return

    port = find_port(DEFAULT_PORT)
    url = f"http://localhost:{port}"
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("")
    print("  ╭──────────────────────────────────────────────╮")
    print("  │   The TesterBot interface is running         │")
    print(f"  │   {url:<42} │")
    print("  │                                              │")
    print("  │   If the browser did not open, paste the     │")
    print("  │   address above into it yourself.            │")
    print("  │                                              │")
    print("  │   To stop it: press Ctrl+C in this window    │")
    print("  ╰──────────────────────────────────────────────╯")
    print("")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down…")
        runner.stop()
        server.shutdown()


if __name__ == "__main__":
    main()
