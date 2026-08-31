"""Compare two TesterBot reports: what got fixed, what is new, what regressed.

A finding's identity is the ``id`` already written into report.json
(category + title + url + element).  Findings that keep their identity but move
to a different page are reported as *moved* rather than as a fix plus a new
problem, so a URL change does not look like progress.
"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .models import SEVERITY_ORDER

SEV_LABEL = {"critical": "Critical", "high": "High", "medium": "Medium",
             "low": "Low", "info": "Info"}


def load_report(path: str) -> Dict[str, Any]:
    """Read a report.json.  ``path`` may be the file itself or its folder."""
    if os.path.isdir(path):
        candidate = os.path.join(path, "report.json")
        if not os.path.exists(candidate):
            raise FileNotFoundError(
                "no report.json in %s - point at the file or the run folder" % path)
        path = candidate
    if not os.path.exists(path):
        raise FileNotFoundError("no such report: %s" % path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if "findings" not in data:
        raise ValueError("%s does not look like a TesterBot report" % path)
    data.setdefault("_path", path)
    return data


def _shape(f: Dict[str, Any]) -> Tuple[str, str, str]:
    """Identity that survives a page moving: category, title, element."""
    return (f.get("category", ""), f.get("title", ""), f.get("element") or "")


def _tally(findings: List[Dict[str, Any]]) -> Dict[str, int]:
    out = {s: 0 for s in SEVERITY_ORDER}
    for f in findings:
        sev = f.get("severity", "info")
        out[sev] = out.get(sev, 0) + 1
    return out


def compare(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Diff two report payloads."""
    old_by_id = {f["id"]: f for f in old.get("findings", []) if f.get("id")}
    new_by_id = {f["id"]: f for f in new.get("findings", []) if f.get("id")}

    same_ids = set(old_by_id) & set(new_by_id)
    gone_ids = set(old_by_id) - set(new_by_id)
    born_ids = set(new_by_id) - set(old_by_id)

    unchanged: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []
    for fid in same_ids:
        o, n = old_by_id[fid], new_by_id[fid]
        if o.get("severity") != n.get("severity"):
            item = dict(n)
            item["was_severity"] = o.get("severity")
            changed.append(item)
        else:
            unchanged.append(n)

    # a problem that only moved to another page is not a fix
    moved: List[Dict[str, Any]] = []
    gone_by_shape: Dict[Tuple[str, str, str], List[str]] = {}
    for fid in gone_ids:
        gone_by_shape.setdefault(_shape(old_by_id[fid]), []).append(fid)

    matched_gone = set()
    matched_born = set()
    for fid in sorted(born_ids):
        bucket = gone_by_shape.get(_shape(new_by_id[fid]))
        if not bucket:
            continue
        partner = bucket.pop(0)
        item = dict(new_by_id[fid])
        item["was_url"] = old_by_id[partner].get("url", "")
        moved.append(item)
        matched_gone.add(partner)
        matched_born.add(fid)

    fixed = [old_by_id[i] for i in sorted(gone_ids - matched_gone)]
    added = [new_by_id[i] for i in sorted(born_ids - matched_born)]

    order = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    key = lambda f: (order.get(f.get("severity", "info"), 9), f.get("title", ""))
    for lst in (fixed, added, changed, moved, unchanged):
        lst.sort(key=key)

    worse = [f for f in changed
             if order.get(f.get("severity"), 9) < order.get(f.get("was_severity"), 9)]
    better = [f for f in changed
              if order.get(f.get("severity"), 9) > order.get(f.get("was_severity"), 9)]

    return {
        "old_meta": old.get("meta", {}),
        "new_meta": new.get("meta", {}),
        "old_path": old.get("_path", ""),
        "new_path": new.get("_path", ""),
        "fixed": fixed,
        "new": added,
        "moved": moved,
        "changed": changed,
        "worse": worse,
        "better": better,
        "unchanged": unchanged,
        "counts": {
            "old_total": len(old.get("findings", [])),
            "new_total": len(new.get("findings", [])),
            "fixed": len(fixed),
            "new": len(added),
            "moved": len(moved),
            "changed": len(changed),
            "unchanged": len(unchanged),
            "fixed_by_severity": _tally(fixed),
            "new_by_severity": _tally(added),
        },
    }


def worst_new_severity(diff: Dict[str, Any]) -> Optional[str]:
    """The most serious severity among newly appeared findings, or None."""
    order = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    fresh = diff["new"] + diff["worse"]
    if not fresh:
        return None
    return min((f.get("severity", "info") for f in fresh), key=lambda s: order.get(s, 9))


def print_diff(diff: Dict[str, Any]) -> None:
    c = diff["counts"]
    old_t, new_t = c["old_total"], c["new_total"]
    delta = new_t - old_t
    arrow = "+%d" % delta if delta > 0 else str(delta) if delta else "no change"

    print("")
    print("=" * 72)
    print("  TesterBot diff  ·  %s" % (diff["new_meta"].get("target", "")))
    print("=" * 72)
    print("  Before : %s   (%s)" % (old_t, diff["old_meta"].get("generated_at", "?")))
    print("  After  : %s   (%s)   %s" % (new_t, diff["new_meta"].get("generated_at", "?"), arrow))
    print("-" * 72)
    print("  Fixed      : %-4d" % c["fixed"])
    print("  New        : %-4d" % c["new"])
    if c["moved"]:
        print("  Moved page : %-4d  (same problem, different URL)" % c["moved"])
    if c["changed"]:
        print("  Re-graded  : %-4d" % c["changed"])
    print("  Still open : %-4d" % c["unchanged"])
    print("-" * 72)

    def _list(title: str, items: List[Dict[str, Any]], limit: int = 15) -> None:
        if not items:
            return
        print("  %s" % title)
        for f in items[:limit]:
            extra = ""
            if f.get("was_severity"):
                extra = "  (was %s)" % f["was_severity"]
            elif f.get("was_url"):
                extra = "  (was %s)" % f["was_url"]
            print("   [%-8s] %s%s" % (f.get("severity", "").upper(), f.get("title", "")[:80], extra))
        if len(items) > limit:
            print("   ... and %d more" % (len(items) - limit))
        print("")

    _list("Fixed since the last run:", diff["fixed"])
    _list("New since the last run:", diff["new"])
    _list("Now more serious:", diff["worse"])
    _list("Same problem, different page:", diff["moved"])

    if not diff["fixed"] and not diff["new"] and not diff["moved"] and not diff["changed"]:
        print("  Nothing changed between the two runs.")
        print("-" * 72)


_DIFF_CSS = r"""
:root{
  --bg:#f6f7f9; --panel:#ffffff; --ink:#15181d; --muted:#5f6772; --line:#e3e6ea;
  --crit:#b3261e; --crit-bg:#fdecea; --high:#c2510a; --high-bg:#fdf0e6;
  --med:#8a6100; --med-bg:#fdf6e3; --low:#0b6b8a; --low-bg:#e8f4f8;
  --info:#4a5361; --info-bg:#eef0f3; --ok:#1e7a45; --ok-bg:#e4f3ea; --accent:#2f5fd0;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1216; --panel:#161a20; --ink:#e7eaee; --muted:#98a1ad; --line:#262c35;
  --crit:#ff7b70; --crit-bg:#2c1614; --high:#ffa45c; --high-bg:#2b1c10;
  --med:#e8c559; --med-bg:#2a2411; --low:#6fc7e6; --low-bg:#11242b;
  --info:#a8b2bf; --info-bg:#1d222a; --ok:#5fd08a; --ok-bg:#12271a; --accent:#7aa2f7;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 80px}
header.top{padding-bottom:20px;border-bottom:1px solid var(--line);margin-bottom:24px}
h1{font-size:22px;margin:0 0 6px}
h1 .bot{color:var(--accent)}
.sub{color:var(--muted);font-size:13px}
.runs{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px;font-size:12.5px;color:var(--muted)}
.run{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:8px 12px}
.run b{color:var(--ink)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:24px 0 30px}
.tile{background:var(--panel);border:1px solid var(--line);border-left-width:4px;
  border-radius:12px;padding:14px 16px}
.tile .n{font-size:26px;font-weight:700;line-height:1.1}
.tile .l{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-top:2px}
.tile.fixed{border-left-color:var(--ok)} .tile.fixed .n{color:var(--ok)}
.tile.new{border-left-color:var(--crit)} .tile.new .n{color:var(--crit)}
.tile.moved{border-left-color:var(--med)} .tile.moved .n{color:var(--med)}
.tile.open{border-left-color:var(--info)} .tile.open .n{color:var(--info)}
h2{font-size:16px;margin:30px 0 12px;display:flex;align-items:center;gap:9px}
h2 .dot{width:9px;height:9px;border-radius:3px;display:inline-block}
h2 .c{font-size:12.5px;color:var(--muted);font-weight:400}
.row{background:var(--panel);border:1px solid var(--line);border-left-width:4px;border-radius:11px;
  padding:12px 15px;margin-bottom:9px}
.row[data-sev=critical]{border-left-color:var(--crit)}
.row[data-sev=high]{border-left-color:var(--high)}
.row[data-sev=medium]{border-left-color:var(--med)}
.row[data-sev=low]{border-left-color:var(--low)}
.row[data-sev=info]{border-left-color:var(--info)}
.row .t{font-weight:600;font-size:14.5px}
.row .m{margin-top:5px;font-size:12.5px;color:var(--muted);font-family:var(--mono);
  word-break:break-all}
.badge{display:inline-block;font-size:11px;font-weight:700;text-transform:uppercase;
  letter-spacing:.05em;padding:2px 7px;border-radius:5px;margin-right:8px;vertical-align:1px}
.badge.critical{background:var(--crit-bg);color:var(--crit)}
.badge.high{background:var(--high-bg);color:var(--high)}
.badge.medium{background:var(--med-bg);color:var(--med)}
.badge.low{background:var(--low-bg);color:var(--low)}
.badge.info{background:var(--info-bg);color:var(--info)}
.note{background:var(--ok-bg);color:var(--ok);border-radius:10px;padding:14px 16px;font-size:14px}
.empty{color:var(--muted);font-size:14px;padding:10px 0}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12.5px}
"""


def _rows(items: List[Dict[str, Any]], kind: str = "") -> str:
    if not items:
        return '<div class="empty">None.</div>'
    out = []
    for f in items:
        sev = f.get("severity", "info")
        meta = html.escape(f.get("url", "") or "")
        if f.get("was_severity"):
            meta = "was %s &middot; %s" % (html.escape(f["was_severity"]), meta)
        elif f.get("was_url"):
            meta = "was %s &rarr; %s" % (html.escape(f["was_url"]), meta)
        if f.get("element"):
            meta += " &middot; %s" % html.escape(str(f["element"])[:120])
        out.append(
            '<div class="row" data-sev="%s"><div class="t">'
            '<span class="badge %s">%s</span>%s</div><div class="m">%s</div></div>'
            % (sev, sev, html.escape(SEV_LABEL.get(sev, sev)),
               html.escape(f.get("title", "")), meta))
    return "".join(out)


def render_diff(diff: Dict[str, Any], out_dir: str, name: str = "diff.html") -> str:
    """Write an HTML page describing the difference between two runs."""
    os.makedirs(out_dir, exist_ok=True)
    c = diff["counts"]
    target = html.escape(diff["new_meta"].get("target", ""))
    delta = c["new_total"] - c["old_total"]
    verdict = ("Nothing changed between the two runs."
               if not (c["fixed"] or c["new"] or c["moved"] or c["changed"])
               else "%d fixed, %d new." % (c["fixed"], c["new"]))

    sections = [
        ("Fixed", "var(--ok)", diff["fixed"],
         "Present in the earlier run, gone from the later one."),
        ("New", "var(--crit)", diff["new"],
         "Not in the earlier run. These appeared since."),
        ("Now more serious", "var(--high)", diff["worse"],
         "Same problem, graded worse than before."),
        ("Same problem, different page", "var(--med)", diff["moved"],
         "The URL changed but the problem did not, so this is not a fix."),
        ("Now less serious", "var(--low)", diff["better"],
         "Same problem, graded lower than before."),
        ("Still open", "var(--info)", diff["unchanged"],
         "Unchanged in both runs."),
    ]
    body = []
    for title, colour, items, blurb in sections:
        if not items and title in ("Now more serious", "Same problem, different page",
                                   "Now less serious"):
            continue
        body.append(
            '<h2><span class="dot" style="background:%s"></span>%s '
            '<span class="c">%d &middot; %s</span></h2>%s'
            % (colour, html.escape(title), len(items), html.escape(blurb), _rows(items)))

    page = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TesterBot diff &mdash; {target}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <h1><span class="bot">TesterBot</span> &mdash; what changed</h1>
  <div class="sub">{target}</div>
  <div class="runs">
    <span class="run">Before: <b>{old_total}</b> findings &middot; {old_when}</span>
    <span class="run">After: <b>{new_total}</b> findings &middot; {new_when}</span>
    <span class="run">Net: <b>{delta}</b></span>
  </div>
</header>
<div class="note">{verdict}</div>
<div class="tiles">
  <div class="tile fixed"><div class="n">{fixed}</div><div class="l">Fixed</div></div>
  <div class="tile new"><div class="n">{new}</div><div class="l">New</div></div>
  <div class="tile moved"><div class="n">{moved}</div><div class="l">Moved page</div></div>
  <div class="tile open"><div class="n">{unchanged}</div><div class="l">Still open</div></div>
</div>
{body}
<footer>Compared {old_path} with {new_path}. A finding keeps its identity across runs, so a
fix disappearing from the list is evidence the fix landed.</footer>
</div>
</body>
</html>
""".format(
        target=target,
        css=_DIFF_CSS,
        old_total=c["old_total"], new_total=c["new_total"],
        old_when=html.escape(str(diff["old_meta"].get("generated_at", "?"))),
        new_when=html.escape(str(diff["new_meta"].get("generated_at", "?"))),
        delta=("+%d" % delta) if delta > 0 else str(delta),
        verdict=html.escape(verdict),
        fixed=c["fixed"], new=c["new"], moved=c["moved"], unchanged=c["unchanged"],
        body="".join(body),
        old_path=html.escape(os.path.basename(diff.get("old_path", "") or "old")),
        new_path=html.escape(os.path.basename(diff.get("new_path", "") or "new")),
    )
    path = os.path.join(out_dir, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(os.path.join(out_dir, "diff.json"), "w", encoding="utf-8") as fh:
        json.dump({k: v for k, v in diff.items() if k != "unchanged"}, fh,
                  indent=2, ensure_ascii=False)
    return path
