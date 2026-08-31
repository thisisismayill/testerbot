"""Render the run into an HTML report plus machine-readable JSON."""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List

from .models import SEVERITY_ORDER, SEVERITY_WEIGHT
from .report_template import TEMPLATE

SEV_LABEL = {"critical": "Critical", "high": "High", "medium": "Medium",
             "low": "Low", "info": "Info"}


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _pretty(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False)[:6000]
    return str(value)[:4000]


def _meta_grid(meta: Dict[str, Any]) -> str:
    login = ("yes — " + esc(meta.get("login_note", ""))) if meta.get("logged_in") else "no"
    items = [
        ("Generated", meta["generated_at"]),
        ("Duration", f"{meta['duration_s']}s"),
        ("Pages tested", meta["pages_tested"]),
        ("Links checked", meta["links_checked"]),
        ("Controls clicked", meta["controls_clicked"]),
        ("Forms tested", meta["forms_tested"]),
        ("Logged in", login),
        ("Danger mode", "ON" if meta.get("danger_mode") else "off"),
    ]
    return "".join(f"<span>{esc(k)}: <b>{v if k == 'Logged in' else esc(v)}</b></span>"
                   for k, v in items)


def _tiles(summary: Dict[str, Any]) -> str:
    sev = summary.get("severity", {})
    out = []
    for name in SEVERITY_ORDER:
        out.append(
            f'<div class="tile" data-sev="{name}">'
            f'<div class="n">{sev.get(name, 0)}</div>'
            f'<div class="l">{SEV_LABEL[name]}</div></div>')
    return "".join(out)


def _cat_chips(summary: Dict[str, Any]) -> str:
    cats = sorted(summary.get("category", {}).items(), key=lambda kv: -kv[1])
    return "".join(f'<span class="pill" data-cat="{esc(c)}">{esc(c)} · {n}</span>'
                   for c, n in cats)


def _finding_card(f: Dict[str, Any]) -> str:
    sev = f.get("severity", "info")
    search_blob = " ".join([
        f.get("title", ""), f.get("detail", ""), f.get("category", ""),
        f.get("url", ""), f.get("element") or "", _pretty(f.get("evidence", {})),
    ]).lower()[:4000]

    parts = [
        f'<div class="finding" data-sev="{sev}" data-cat="{esc(f.get("category", ""))}" '
        f'data-count="{f.get("occurrences", 1)}" data-weight="{SEVERITY_WEIGHT.get(sev, 9)}" '
        f'data-search="{esc(search_blob)}">',
        '<div class="fh">',
        f'<span class="badge {sev}">{SEV_LABEL.get(sev, sev)}</span>',
        '<div class="ft">',
        f'<div class="t">{esc(f.get("title", ""))}</div>',
        '<div class="m">',
        f'<span class="cat">{esc(f.get("category", ""))}</span>',
    ]
    if f.get("occurrences", 1) > 1:
        parts.append(f'<span class="count">{f["occurrences"]}× across the site</span>')
    if f.get("url"):
        parts.append(f'<span>{esc(f["url"][:110])}</span>')
    parts.append('</div></div><span class="caret">▶</span></div>')

    body = ['<div class="fb">']
    if f.get("detail"):
        body.append(f'<h4>What this means</h4><p>{esc(f["detail"])}</p>')
    body.append('<h4>Where</h4><p><a class="url" href="%s" target="_blank" rel="noopener">%s</a></p>'
                % (esc(f.get("url", "")), esc(f.get("url", "—"))))
    if f.get("other_urls"):
        items = "".join(f'<li><a class="url" href="{esc(u)}" target="_blank" rel="noopener">'
                        f'{esc(u)}</a></li>' for u in f["other_urls"][:20])
        body.append(f'<h4>Also on</h4><ul class="urls">{items}</ul>')
    if f.get("element"):
        body.append(f'<h4>Element</h4><pre>{esc(f["element"])}</pre>')
    if f.get("evidence"):
        body.append(f'<h4>Evidence</h4><pre>{esc(_pretty(f["evidence"]))}</pre>')
    if f.get("screenshot"):
        body.append(f'<h4>Screenshot</h4><a href="{esc(f["screenshot"])}" target="_blank">'
                    f'<img class="shot" src="{esc(f["screenshot"])}" alt="screenshot"></a>')
    if f.get("how_to_fix"):
        body.append(f'<h4>Suggested fix</h4><div class="fix">{esc(f["how_to_fix"])}</div>')
    body.append('</div>')
    parts.append("".join(body))
    parts.append('</div>')
    return "".join(parts)


def _page_table(pages: List[Dict[str, Any]]) -> str:
    rows = []
    for p in pages:
        status = p.get("status")
        status_txt = str(status) if status else (p.get("error", "error")[:40] or "—")
        load = f"{p['load_ms']:.0f} ms" if p.get("load_ms") else "—"
        rows.append(
            "<tr>"
            f'<td><a class="url" href="{esc(p["url"])}" target="_blank" rel="noopener">'
            f'{esc(p["url"][:90])}</a></td>'
            f'<td>{esc(p.get("title", "")[:60])}</td>'
            f'<td class="num">{esc(status_txt)}</td>'
            f'<td class="num">{esc(load)}</td>'
            f'<td class="num">{p.get("links_found", 0)}</td>'
            f'<td class="num">{p.get("buttons_clicked", 0)}</td>'
            f'<td class="num">{p.get("forms_tested", 0)}</td>'
            f'<td class="num">{p.get("findings", 0)}</td>'
            "</tr>")
    return ("<table><thead><tr><th>URL</th><th>Title</th><th>Status</th><th>Load</th>"
            "<th>Links</th><th>Clicks</th><th>Forms</th><th>Findings</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


CWV_LABELS = {"lcp_ms": "LCP", "inp_ms": "INP", "cls": "CLS",
              "fcp_ms": "FCP", "ttfb_ms": "TTFB"}


def _cwv_badge(cat: str) -> str:
    return {"FAST": ("b-good", "good"), "AVERAGE": ("b-avg", "average"),
            "SLOW": ("b-poor", "poor")}.get(cat or "", ("b-avg", "—"))[0]


def _cwv_label(cat: str) -> str:
    return {"FAST": "good", "AVERAGE": "average", "SLOW": "poor"}.get(cat or "", "—")


def _fmt_ms(v: Any) -> str:
    try:
        v = float(v)
        return f"{v/1000:.2f} s" if v >= 1000 else f"{v:.0f} ms"
    except Exception:
        return "—"


def _intel_panel(intel: Dict[str, Any]) -> str:
    if not intel or intel.get("error"):
        return ""
    parts = ['<section class="intel">',
             '<div class="intel-head"><h2>Site intelligence</h2>'
             '<span class="muted">Authority · performance · technology · hosting for the home page</span></div>',
             '<div class="intel-grid">']

    # ---- authority
    auth = intel.get("authority", {})
    parts.append('<div class="icard"><div class="cap">Domain authority</div>')
    if auth.get("found"):
        score = auth.get("score", 0)
        pct = round((score / 10.0) * 100)
        col = "var(--ok)" if score >= 6 else ("var(--med)" if score >= 3 else "var(--crit)")
        rank = auth.get("rank")
        rank_txt = f'<b>#{esc(rank)}</b> global rank<br>' if rank else ""
        parts.append(
            f'<div class="auth"><div class="gauge" style="--v:{pct};--col:{col}">'
            f'<div class="val"><b>{esc(score)}</b><span>/ 10</span></div></div>'
            f'<div class="meta">{rank_txt}OpenPageRank<br>0–10 authority score</div></div>')
    else:
        reason = auth.get("reason") or auth.get("note") or "No data available."
        extra = ('<br><a href="https://www.domcop.com/openpagerank/" target="_blank" '
                 'rel="noopener">Get a free key →</a>' if not auth.get("available") else "")
        parts.append(f'<div class="na">{esc(reason)}{extra}</div>')
    parts.append('</div>')

    # ---- performance
    perf = intel.get("performance", {})
    parts.append('<div class="icard"><div class="cap">Performance · mobile</div>')
    if perf.get("available"):
        ls = perf.get("lab_score")
        if ls is not None:
            col = "var(--ok)" if ls >= 90 else ("var(--med)" if ls >= 50 else "var(--crit)")
            parts.append(f'<div class="perf-score"><span class="n" style="color:{col}">{ls}</span>'
                         '<span class="lbl">/ 100 · Lighthouse lab</span></div>')
        field = perf.get("field", {})
        if field:
            parts.append('<div class="cwv">')
            for key, short in CWV_LABELS.items():
                if key in field:
                    m = field[key]
                    val = f"{m['p75']/1000:.2f} s" if key.endswith("_ms") and m.get("p75") else \
                          (str(m.get("p75")) if not key.endswith("_ms") else "—")
                    if key == "cls" and m.get("p75") is not None:
                        val = f"{m['p75']/100:.2f}"
                    badge = _cwv_badge(m.get("category"))
                    parts.append(f'<div class="row"><span class="k">{short}</span>'
                                 f'<span class="v">{esc(val)}</span>'
                                 f'<span class="badge2 {badge}">{_cwv_label(m.get("category"))}</span></div>')
            parts.append('</div>')
        elif ls is None:
            parts.append('<div class="na">No performance data was returned.</div>')
        else:
            parts.append('<div class="na" style="margin-top:6px">No real-user (CrUX) data for this '
                         'domain yet — it appears once the site gathers enough traffic.</div>')
    else:
        reason = perf.get("reason") or "Performance was not checked."
        parts.append(f'<div class="na">{esc(reason)}</div>')
    parts.append('</div>')

    # ---- tech stack + hosting
    tech = intel.get("tech", {})
    host = intel.get("hosting", {})
    parts.append('<div class="icard"><div class="cap">Technology stack'
                 + (f' · {tech.get("count", 0)}' if tech.get("count") else "") + '</div>')
    by_cat = tech.get("by_category", {})
    if by_cat:
        priority = ["CMS", "Ecommerce", "JavaScript frameworks", "Web frameworks",
                    "Programming languages", "Web servers", "PaaS", "CDN",
                    "Analytics", "Tag managers", "Databases"]
        ordered = sorted(by_cat.items(),
                         key=lambda kv: (priority.index(kv[0]) if kv[0] in priority else 99, kv[0]))
        for cat, names in ordered[:6]:
            chips = "".join(f'<span class="tchip">{esc(n)}</span>' for n in names[:8])
            parts.append(f'<div class="tech-cat"><div class="ct">{esc(cat or "Other")}</div>'
                         f'<div class="tchips">{chips}</div></div>')
    else:
        parts.append('<div class="na">No technologies detected.</div>')
    # hosting line
    hbits = []
    if host.get("server"):
        hbits.append(f'<span>Server: <b>{esc(host["server"][:40])}</b></span>')
    if host.get("cdn"):
        hbits.append(f'<span>CDN: <b>{esc(host["cdn"])}</b></span>')
    if host.get("ip"):
        hbits.append(f'<span>IP: <b>{esc(host["ip"])}</b></span>')
    if hbits:
        parts.append('<div class="host-line">' + "".join(hbits) + '</div>')
    parts.append('</div>')

    parts.append('</div></section>')
    return "".join(parts)


def _linkgraph_panel(lg: Dict[str, Any]) -> str:
    if not lg or lg.get("error") or not lg.get("stats"):
        return ""
    st = lg["stats"]
    parts = ['<section class="lg">',
             '<div class="lg-head"><h2>Link graph</h2>'
             '<span class="muted">data we crawled ourselves — the same core as Ahrefs</span></div>',
             '<div class="lg-sub">Every link was recorded while the site was crawled. The '
             '<b>PageRank</b> below is the same calculation Google and Ahrefs use — it '
             'ranks the site\'s own "strongest" pages by its internal link structure. '
             'Raw data: <code>linkgraph.json</code> and <code>linkgraph-edges.csv</code>.</div>']

    # stats row
    stat_defs = [("pages", "Pages"), ("edges", "Links (edges)"),
                 ("internal_edges", "Internal"), ("external_edges", "External"),
                 ("external_domains", "External domains"), ("nofollow_edges", "nofollow")]
    parts.append('<div class="lg-stats">')
    for key, label in stat_defs:
        parts.append(f'<div class="lg-stat"><div class="n">{st.get(key, 0)}</div>'
                     f'<div class="l">{label}</div></div>')
    parts.append('</div>')

    parts.append('<div class="lg-grid">')

    # top pages by internal PageRank
    parts.append('<div class="lg-card"><div class="cap">Strongest pages · internal PageRank</div>')
    top = lg.get("top_pages", [])[:8]
    if top:
        for pg in top:
            pr = pg.get("pagerank", 0)
            path = pg.get("path") or "/"
            parts.append(
                f'<div class="pr-row"><span class="pr-path" title="{esc(pg.get("url", ""))}">'
                f'{esc(path)}</span>'
                f'<span class="pr-bar"><span style="width:{min(100, pr)}%"></span></span>'
                f'<span class="pr-val">{esc(pr)}</span></div>')
    else:
        parts.append('<div class="pr-row">No data available.</div>')
    parts.append('</div>')

    # outbound domains
    parts.append('<div class="lg-card"><div class="cap">Domains linked out to</div>')
    out = lg.get("outbound_domains", [])[:8]
    if out:
        for d in out:
            nf = (f'<span class="nf">{d["nofollow"]} nofollow</span>'
                  if d.get("nofollow") else "")
            parts.append(
                f'<div class="dom-row"><span class="d">{esc(d["domain"])}</span>{nf}'
                f'<span class="c">{d["links"]} link · {d["from_pages"]} pages</span></div>')
    else:
        parts.append('<div class="dom-row">No external links found.</div>')
    parts.append('</div>')

    parts.append('</div></section>')
    return "".join(parts)


def render(data: Dict[str, Any], out_dir: str, report_name: str = "report.html") -> str:
    os.makedirs(out_dir, exist_ok=True)
    meta, summary = data["meta"], data["summary"]
    findings = data["findings"]

    cards = "".join(_finding_card(f) for f in findings)
    if not cards:
        cards = ('<div class="empty">No problems were found with the checks that ran. '
                 'Consider raising --max-pages or adding --danger-mode on a staging copy.</div>')

    footer = (f"TesterBot v{esc(meta.get('version', ''))} · accessibility checks powered by "
              f"axe-core (Mozilla Public License 2.0) · this report is a starting point, not a "
              f"substitute for human judgement.")

    html_out = (TEMPLATE
                .replace("{{TITLE}}", esc(f"TesterBot report — {meta['target']}"))
                .replace("{{TARGET}}", esc(meta["target"]))
                .replace("{{METAGRID}}", _meta_grid(meta))
                .replace("{{INTELLIGENCE}}", _intel_panel(data.get("intelligence", {})))
                .replace("{{LINKGRAPH}}", _linkgraph_panel(data.get("linkgraph", {})))
                .replace("{{TILES}}", _tiles(summary))
                .replace("{{CATCHIPS}}", _cat_chips(summary))
                .replace("{{FINDINGS}}", cards)
                .replace("{{PAGETABLE}}", _page_table(data["pages"]))
                .replace("{{FOOTER}}", footer))

    html_path = os.path.join(out_dir, report_name)
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html_out)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return html_path


def print_summary(data: Dict[str, Any], html_path: str) -> None:
    meta, summary = data["meta"], data["summary"]
    sev = summary.get("severity", {})
    line = " · ".join(f"{SEV_LABEL[s]}: {sev.get(s, 0)}" for s in SEVERITY_ORDER)
    print("")
    print("=" * 72)
    print(f"  TesterBot finished  ·  {meta['target']}")
    print("=" * 72)
    print(f"  Pages tested : {meta['pages_tested']}"
          f"   Links checked: {meta['links_checked']}")
    print(f"  Clicks       : {meta['controls_clicked']}"
          f"   Forms tested : {meta['forms_tested']}")
    print(f"  Duration     : {meta['duration_s']}s"
          f"   Screenshots  : {meta['screenshots']}")
    print(f"  Findings     : {summary['total']}  ({line})")
    print("-" * 72)
    top = [f for f in data["findings"] if f["severity"] in ("critical", "high")][:12]
    if top:
        print("  Most urgent:")
        for f in top:
            print(f"   [{f['severity'].upper():8}] {f['title'][:88]}")
    else:
        print("  No critical or high-severity findings.")
    print("-" * 72)
    print(f"  Report: {html_path}")
    print(f"  JSON  : {os.path.join(os.path.dirname(html_path), 'report.json')}")
    print("=" * 72)
