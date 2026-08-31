#!/usr/bin/env python3
"""
TesterBot - give it a URL, it tests the whole website like a human QA would.

    python tester_bot.py https://example.com

Only run it against sites you own or are authorised to test.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from testerbot import __version__
from testerbot.config import Config
from testerbot.crawler import TesterBot
from testerbot.diff import compare, load_report, print_diff, render_diff, worst_new_severity
from testerbot.report import print_summary, render
from testerbot.models import SEVERITY_ORDER

BANNER = r"""
  _____         _           ____        _
 |_   _|__  ___| |_ ___ _ _| __ )  ___ | |_
   | |/ _ \/ __| __/ _ \ '_|  _ \ / _ \| __|
   | |  __/\__ \ ||  __/ |  | |_) | (_) | |_
   |_|\___||___/\__\___|_|  |____/ \___/ \__|   v%s
""" % __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tester_bot.py",
        description="Autonomous website tester: crawls, clicks, fills forms and reports bugs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("url", nargs="?", help="Start URL, e.g. https://example.com")
    p.add_argument("--config", help="YAML or JSON config file with any of these options")
    p.add_argument("--version", action="version", version=f"TesterBot {__version__}")

    g = p.add_argument_group("scope")
    g.add_argument("--max-pages", type=int, help="Maximum pages to visit")
    g.add_argument("--max-depth", type=int, help="Maximum link depth from the start URL")
    g.add_argument("--include", action="append", help="Only crawl URLs matching this regex "
                                                      "(repeatable)")
    g.add_argument("--exclude", action="append", help="Never crawl URLs matching this regex "
                                                      "(repeatable)")
    g.add_argument("--extra-url", action="append", dest="extra_urls",
                   help="Additional URL to test (repeatable)")
    g.add_argument("--allow-subdomains", action="store_true", default=None)
    g.add_argument("--no-sitemap", dest="use_sitemap", action="store_false", default=None,
                   help="Do not seed the crawl from sitemap.xml")

    g = p.add_argument_group("login")
    g.add_argument("--login-url", help="Page containing the login form")
    g.add_argument("--username", "-u", help="Test account username / e-mail")
    g.add_argument("--password", "-p", help="Test account password "
                                            "(or set TESTERBOT_PASS)")
    g.add_argument("--user-selector", help="CSS selector for the username field")
    g.add_argument("--pass-selector", help="CSS selector for the password field")
    g.add_argument("--submit-selector", help="CSS selector for the login button")
    g.add_argument("--login-success-text", help="Text that proves the login worked")
    g.add_argument("--login-success-url", help="URL fragment that proves the login worked")
    g.add_argument("--storage-state", help="Reuse a saved session file")
    g.add_argument("--save-storage-state", help="Write the session to this file after login")

    g = p.add_argument_group("behaviour")
    g.add_argument("--no-click", dest="click_elements", action="store_false", default=None,
                   help="Do not click buttons")
    g.add_argument("--no-forms", dest="submit_forms", action="store_false", default=None,
                   help="Analyse forms but never submit them")
    g.add_argument("--max-clicks", type=int, dest="max_clicks_per_page")
    g.add_argument("--max-forms", type=int, dest="max_forms_per_page")
    g.add_argument("--danger-mode", action="store_true", default=None,
                   help="ALSO click delete/pay/logout controls. Staging sites only!")
    g.add_argument("--no-external-links", dest="check_external_links", action="store_false",
                   default=None)
    g.add_argument("--no-axe", dest="run_axe", action="store_false", default=None,
                   help="Skip the axe-core accessibility audit")
    g.add_argument("--no-hygiene", dest="hygiene_checks", action="store_false", default=None,
                   help="Skip the exposed-file checks (.env, .git, backups)")
    g.add_argument("--no-responsive", dest="responsive_checks", action="store_false", default=None)

    g = p.add_argument_group("intelligence")
    g.add_argument("--no-intel", dest="run_intelligence", action="store_false", default=None,
                   help="Skip site intelligence (authority / performance / tech stack)")
    g.add_argument("--no-perf", dest="run_performance", action="store_false", default=None,
                   help="Skip the PageSpeed performance check (it is the slow part)")
    g.add_argument("--opr-key", dest="opr_key",
                   help="OpenPageRank key for domain authority (free: domcop.com/openpagerank)")
    g.add_argument("--psi-key", dest="psi_key",
                   help="Google PageSpeed Insights API key (free, optional — raises the limit)")

    g = p.add_argument_group("browser")
    g.add_argument("--headed", dest="headless", action="store_false", default=None,
                   help="Show the browser window while testing")
    g.add_argument("--slow-mo", type=int, help="Milliseconds to slow each action (debugging)")
    g.add_argument("--timeout", type=int, dest="timeout_ms", help="Action timeout in ms")
    g.add_argument("--nav-timeout", type=int, dest="nav_timeout_ms",
                   help="Navigation timeout in ms")
    g.add_argument("--settle", type=int, dest="settle_ms",
                   help="Extra wait after load, for SPAs (ms)")
    g.add_argument("--viewport", help="Desktop viewport, e.g. 1440x900")
    g.add_argument("--user-agent")
    g.add_argument("--ignore-https-errors", action="store_true", default=None,
                   help="Accept self-signed certificates (staging)")

    g = p.add_argument_group("output")
    g.add_argument("--out", dest="out_dir", help="Output folder for the report")
    g.add_argument("--screenshot-all", action="store_true", default=None,
                   help="Screenshot every page, not only pages with findings")
    g.add_argument("--quiet", "-q", action="store_true", default=None)
    g.add_argument("--fail-on", choices=SEVERITY_ORDER + ["none"], default="none",
                   help="Exit with code 1 if a finding at this severity or worse exists "
                        "(useful in CI)")

    g = p.add_argument_group("compare with a previous run")
    g.add_argument("--baseline", help="An earlier report.json (or its folder). After the run, "
                                      "show what was fixed and what is new since then")
    g.add_argument("--fail-on-new", choices=SEVERITY_ORDER + ["none"], default="none",
                   help="With --baseline: exit 1 only if a NEW finding at this severity or "
                        "worse appeared. Ignores problems that were already there")
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cfg = Config.from_file(args.config) if args.config else Config()

    if args.viewport:
        try:
            w, h = args.viewport.lower().split("x")
            cfg.viewport_width, cfg.viewport_height = int(w), int(h)
        except Exception:
            parser.error("--viewport must look like 1440x900")

    skip = {"config", "viewport", "fail_on", "url", "baseline", "fail_on_new"}
    for key, value in vars(args).items():
        if key in skip or value is None:
            continue
        if hasattr(cfg, key):
            setattr(cfg, key, value)

    if args.url:
        cfg.url = args.url
    cfg.merge_env()

    if not cfg.url:
        parser.error("a start URL is required (positional argument or 'url:' in --config)")
    if not cfg.url.startswith(("http://", "https://")):
        cfg.url = "https://" + cfg.url

    if not cfg.quiet:
        print(BANNER)
        print(f"  Target      : {cfg.url}")
        print(f"  Budget      : up to {cfg.max_pages} pages, depth {cfg.max_depth}")
        print(f"  Interaction : clicks={'on' if cfg.click_elements else 'off'} "
              f"forms={'submit' if cfg.submit_forms else 'analyse only'} "
              f"danger-mode={'ON' if cfg.danger_mode else 'off'}")
        print(f"  Output      : {os.path.abspath(cfg.out_dir)}")
        print("")
        print("  Only test sites you own or have written permission to test.")
        print("")

    bot = TesterBot(cfg)
    try:
        data = bot.run()
    except KeyboardInterrupt:
        print("\nInterrupted - writing a report with what was collected so far…")
        data = bot.build_report()
    except Exception as exc:  # keep partial results usable
        print(f"\nRun aborted: {exc}", file=sys.stderr)
        try:
            data = bot.build_report()
        except Exception:
            return 2

    html_path = render(data, cfg.out_dir, cfg.report_name)
    if not cfg.quiet:
        print_summary(data, html_path)

    exit_code = 0

    if args.baseline:
        try:
            old = load_report(args.baseline)
        except (FileNotFoundError, ValueError) as exc:
            print("Baseline skipped: %s" % exc, file=sys.stderr)
        else:
            diff = compare(old, data)
            if not cfg.quiet:
                print_diff(diff)
                print("  Diff report: %s" % render_diff(diff, cfg.out_dir))
                print("=" * 72)
            else:
                render_diff(diff, cfg.out_dir)
            if args.fail_on_new != "none":
                worst = worst_new_severity(diff)
                if worst is not None and \
                        SEVERITY_ORDER.index(worst) <= SEVERITY_ORDER.index(args.fail_on_new):
                    if not cfg.quiet:
                        print("  FAIL: a new %s finding appeared since the baseline." % worst)
                    exit_code = 1
    elif args.fail_on_new != "none":
        print("--fail-on-new needs --baseline; ignoring it.", file=sys.stderr)

    if args.fail_on != "none":
        limit = SEVERITY_ORDER.index(args.fail_on)
        for f in data["findings"]:
            if SEVERITY_ORDER.index(f["severity"]) <= limit:
                exit_code = 1
                break
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
