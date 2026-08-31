#!/usr/bin/env python3
"""
Compare two TesterBot runs and show what changed.

    python tb_diff.py reports/old-run reports/new-run
    python tb_diff.py old/report.json new/report.json --out reports/compare

Each argument is either a report.json or the folder that contains one.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from testerbot import __version__
from testerbot.diff import compare, load_report, print_diff, render_diff, worst_new_severity
from testerbot.models import SEVERITY_ORDER


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tb_diff.py",
        description="Compare two TesterBot reports: what got fixed, what is new.")
    p.add_argument("before", help="Earlier report.json, or the folder holding it")
    p.add_argument("after", help="Later report.json, or the folder holding it")
    p.add_argument("--out", dest="out_dir",
                   help="Write diff.html and diff.json here (default: next to the later report)")
    p.add_argument("--no-html", action="store_true", help="Only print the summary")
    p.add_argument("--quiet", "-q", action="store_true", help="Print nothing on success")
    p.add_argument("--fail-on-new", choices=SEVERITY_ORDER + ["none"], default="none",
                   help="Exit 1 if a NEW finding at this severity or worse appeared (for CI)")
    p.add_argument("--version", action="version", version="TesterBot %s" % __version__)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        old = load_report(args.before)
        new = load_report(args.after)
    except (FileNotFoundError, ValueError) as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 2

    old_target = old.get("meta", {}).get("target", "")
    new_target = new.get("meta", {}).get("target", "")
    if old_target and new_target and old_target != new_target and not args.quiet:
        print("Note: the two runs targeted different sites:\n  %s\n  %s"
              % (old_target, new_target), file=sys.stderr)

    diff = compare(old, new)
    if not args.quiet:
        print_diff(diff)

    if not args.no_html:
        out_dir = args.out_dir or os.path.dirname(os.path.abspath(new.get("_path", ".")))
        path = render_diff(diff, out_dir)
        if not args.quiet:
            print("  Diff report: %s" % path)
            print("=" * 72)

    if args.fail_on_new != "none":
        worst = worst_new_severity(diff)
        if worst is not None:
            limit = SEVERITY_ORDER.index(args.fail_on_new)
            if SEVERITY_ORDER.index(worst) <= limit:
                if not args.quiet:
                    print("  FAIL: a new %s finding appeared." % worst)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
