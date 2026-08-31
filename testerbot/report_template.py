"""HTML shell for the report. {{PLACEHOLDERS}} are replaced by report.py."""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{
  --bg:#f6f7f9; --panel:#ffffff; --ink:#15181d; --muted:#5f6772; --line:#e3e6ea;
  --crit:#b3261e; --crit-bg:#fdecea; --high:#c2510a; --high-bg:#fdf0e6;
  --med:#8a6100; --med-bg:#fdf6e3; --low:#0b6b8a; --low-bg:#e8f4f8;
  --info:#4a5361; --info-bg:#eef0f3; --ok:#1e7a45; --accent:#2f5fd0;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#0f1216; --panel:#161a20; --ink:#e7eaee; --muted:#98a1ad; --line:#262c35;
    --crit:#ff7b70; --crit-bg:#2c1614; --high:#ffa45c; --high-bg:#2b1c10;
    --med:#e8c559; --med-bg:#2a2411; --low:#6fc7e6; --low-bg:#11242b;
    --info:#a8b2bf; --info-bg:#1d222a; --ok:#5fd08a; --accent:#7aa2f7;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
header.top{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;justify-content:space-between;
  padding-bottom:20px;border-bottom:1px solid var(--line);margin-bottom:24px}
h1{font-size:22px;margin:0 0 6px}
h1 .bot{color:var(--accent)}
.sub{color:var(--muted);font-size:13px}
.sub a{color:var(--accent)}
.meta-grid{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12.5px;color:var(--muted);margin-top:8px}
.meta-grid b{color:var(--ink);font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:26px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;
  cursor:pointer;transition:.12s;border-left-width:4px}
.tile:hover{transform:translateY(-1px);box-shadow:0 4px 14px rgba(0,0,0,.07)}
.tile.on{outline:2px solid var(--accent);outline-offset:1px}
.tile .n{font-size:26px;font-weight:700;line-height:1.1}
.tile .l{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-top:2px}
.tile[data-sev=critical]{border-left-color:var(--crit)} .tile[data-sev=critical] .n{color:var(--crit)}
.tile[data-sev=high]{border-left-color:var(--high)} .tile[data-sev=high] .n{color:var(--high)}
.tile[data-sev=medium]{border-left-color:var(--med)} .tile[data-sev=medium] .n{color:var(--med)}
.tile[data-sev=low]{border-left-color:var(--low)} .tile[data-sev=low] .n{color:var(--low)}
.tile[data-sev=info]{border-left-color:var(--info)} .tile[data-sev=info] .n{color:var(--info)}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:18px}
input[type=search]{flex:1;min-width:220px;padding:9px 12px;border:1px solid var(--line);
  border-radius:9px;background:var(--panel);color:var(--ink);font-size:14px}
select{padding:9px 10px;border:1px solid var(--line);border-radius:9px;background:var(--panel);
  color:var(--ink);font-size:14px}
.btn{padding:9px 13px;border:1px solid var(--line);border-radius:9px;background:var(--panel);
  color:var(--ink);cursor:pointer;font-size:13.5px}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.finding{background:var(--panel);border:1px solid var(--line);border-left-width:4px;
  border-radius:11px;margin-bottom:11px;overflow:hidden}
.finding[data-sev=critical]{border-left-color:var(--crit)}
.finding[data-sev=high]{border-left-color:var(--high)}
.finding[data-sev=medium]{border-left-color:var(--med)}
.finding[data-sev=low]{border-left-color:var(--low)}
.finding[data-sev=info]{border-left-color:var(--info)}
.fh{display:flex;gap:12px;align-items:flex-start;padding:13px 16px;cursor:pointer}
.fh:hover{background:rgba(127,127,127,.05)}
.badge{flex:none;font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  padding:4px 8px;border-radius:6px;margin-top:2px}
.badge.critical{background:var(--crit-bg);color:var(--crit)}
.badge.high{background:var(--high-bg);color:var(--high)}
.badge.medium{background:var(--med-bg);color:var(--med)}
.badge.low{background:var(--low-bg);color:var(--low)}
.badge.info{background:var(--info-bg);color:var(--info)}
.ft{flex:1;min-width:0}
.ft .t{font-weight:600;font-size:14.5px;word-break:break-word}
.ft .m{font-size:12.5px;color:var(--muted);margin-top:3px;display:flex;flex-wrap:wrap;gap:4px 12px}
.cat{font-size:11px;background:var(--info-bg);color:var(--info);padding:2px 7px;border-radius:20px}
.count{font-size:11px;background:var(--info-bg);color:var(--info);padding:2px 7px;border-radius:20px}
.caret{flex:none;color:var(--muted);transition:.15s;margin-top:4px}
.finding.open .caret{transform:rotate(90deg)}
.fb{display:none;padding:0 16px 16px 16px;border-top:1px solid var(--line);margin-top:-1px}
.finding.open .fb{display:block}
.fb h4{margin:15px 0 6px;font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;
  color:var(--muted);font-weight:700}
.fb p{margin:0;font-size:14px}
.fix{background:var(--low-bg);border-radius:8px;padding:10px 12px;font-size:13.5px}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:11px;
  overflow-x:auto;font-family:var(--mono);font-size:12px;margin:0;white-space:pre-wrap;
  word-break:break-word;max-height:340px}
code{font-family:var(--mono);font-size:12.5px;background:var(--bg);padding:1px 5px;border-radius:4px}
a.url{color:var(--accent);text-decoration:none;word-break:break-all}
a.url:hover{text-decoration:underline}
ul.urls{margin:4px 0 0;padding-left:18px;font-size:13px}
img.shot{max-width:100%;border:1px solid var(--line);border-radius:8px;margin-top:8px;display:block}
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--panel);
  border:1px solid var(--line);border-radius:11px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line)}
th{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
  background:rgba(127,127,127,.05)}
tbody tr:last-child td{border-bottom:none}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.tablewrap{overflow-x:auto;margin-bottom:30px}
h2{font-size:17px;margin:34px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.empty{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:34px;
  text-align:center;color:var(--muted)}
.pill{display:inline-block;font-size:11.5px;padding:3px 9px;border-radius:20px;
  background:var(--info-bg);color:var(--info);margin:0 5px 5px 0;cursor:pointer;border:1px solid transparent}
.pill.on{border-color:var(--accent);color:var(--accent)}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--line);
  font-size:12px;color:var(--muted)}
.hide{display:none !important}
/* ---- site intelligence panel ---- */
.intel{margin-bottom:26px}
.intel-head{display:flex;align-items:baseline;gap:12px;margin-bottom:14px}
.intel-head h2{font-size:15px;margin:0;font-weight:700;letter-spacing:.02em}
.intel-head .muted{font-size:12.5px;color:var(--muted)}
.intel-grid{display:grid;grid-template-columns:1.1fr 1.4fr 1.5fr;gap:14px}
.icard{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px}
.icard .cap{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
  font-weight:700;margin-bottom:12px}
/* authority gauge */
.auth{display:flex;align-items:center;gap:16px}
.gauge{--v:0;--col:var(--accent);position:relative;width:96px;height:96px;flex:none;border-radius:50%;
  background:conic-gradient(var(--col) calc(var(--v)*3.6deg),var(--bg) 0)}
.gauge::after{content:"";position:absolute;inset:9px;border-radius:50%;background:var(--panel)}
.gauge .val{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
  justify-content:center;z-index:1}
.gauge .val b{font-size:1.6rem;font-weight:700;line-height:1}
.gauge .val span{font-size:10.5px;color:var(--muted)}
.auth .meta{font-size:13px;color:var(--muted);line-height:1.5}
.auth .meta b{color:var(--ink)}
.na{color:var(--muted);font-size:13px;line-height:1.5}
.na a{color:var(--accent)}
/* performance */
.perf-score{display:flex;align-items:baseline;gap:8px;margin-bottom:12px}
.perf-score .n{font-size:2rem;font-weight:700;line-height:1}
.perf-score .lbl{font-size:12.5px;color:var(--muted)}
.cwv{display:flex;flex-direction:column;gap:7px}
.cwv .row{display:flex;align-items:center;gap:9px;font-size:12.5px}
.cwv .k{width:42px;color:var(--muted);font-weight:600}
.cwv .v{font-family:var(--mono);font-variant-numeric:tabular-nums}
.cwv .badge2{margin-left:auto;font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:20px}
.b-good{background:var(--low-bg);color:var(--ok)}
.b-avg{background:var(--med-bg);color:var(--med)}
.b-poor{background:var(--crit-bg);color:var(--crit)}
/* tech chips */
.tech-cat{margin-bottom:11px}
.tech-cat:last-child{margin-bottom:0}
.tech-cat .ct{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
  margin-bottom:5px;font-weight:600}
.tchips{display:flex;flex-wrap:wrap;gap:5px}
.tchip{font-size:12px;padding:3px 9px;border-radius:6px;background:var(--info-bg);color:var(--ink);
  border:1px solid var(--line)}
.host-line{font-size:12.5px;color:var(--muted);margin-top:2px;display:flex;flex-wrap:wrap;gap:3px 14px}
.host-line b{color:var(--ink);font-weight:600}
@media (max-width:820px){.intel-grid{grid-template-columns:1fr}}
/* ---- link graph ---- */
.lg{margin-bottom:26px}
.lg-head{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.lg-head h2{font-size:15px;margin:0;font-weight:700;letter-spacing:.02em}
.lg-head .muted{font-size:12.5px;color:var(--muted)}
.lg-sub{font-size:12.5px;color:var(--muted);margin-bottom:14px}
.lg-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-bottom:16px}
.lg-stat{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:12px 14px}
.lg-stat .n{font-family:var(--mono);font-size:1.35rem;font-weight:600}
.lg-stat .l{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-top:2px}
.lg-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.lg-card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.lg-card .cap{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
  font-weight:700;margin-bottom:12px}
.pr-row{display:flex;align-items:center;gap:10px;padding:7px 0;border-top:1px dashed var(--line);font-size:13px}
.pr-row:first-of-type{border-top:none}
.pr-path{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--mono);font-size:12.5px}
.pr-bar{flex:none;width:88px;height:7px;border-radius:4px;background:var(--info-bg);overflow:hidden}
.pr-bar span{display:block;height:100%;background:var(--accent);border-radius:4px}
.pr-val{flex:none;width:34px;text-align:right;font-family:var(--mono);font-size:12px;font-weight:600;color:var(--accent)}
.dom-row{display:flex;align-items:baseline;gap:8px;padding:7px 0;border-top:1px dashed var(--line);font-size:13px}
.dom-row:first-of-type{border-top:none}
.dom-row .d{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.dom-row .c{font-family:var(--mono);font-size:12px;color:var(--muted)}
.dom-row .nf{font-size:10px;padding:1px 6px;border-radius:20px;background:var(--med-bg);color:var(--med)}
@media (max-width:820px){.lg-grid{grid-template-columns:1fr}}
.legend{font-size:12.5px;color:var(--muted);margin:-8px 0 20px}
</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div>
    <h1><span class="bot">TesterBot</span> — QA report</h1>
    <div class="sub">Target: <a class="url" href="{{TARGET}}" target="_blank" rel="noopener">{{TARGET}}</a></div>
    <div class="meta-grid">{{METAGRID}}</div>
  </div>
  <div><button class="btn" onclick="expandAll()">Expand all</button>
       <button class="btn" onclick="collapseAll()">Collapse all</button></div>
</header>

{{INTELLIGENCE}}

{{LINKGRAPH}}

<div class="tiles">{{TILES}}</div>

<div class="legend">Click a tile to filter by severity, or a category chip below. Every finding
expands to show the evidence, the URL and a suggested fix.</div>

<div>{{CATCHIPS}}</div>

<div class="controls">
  <input type="search" id="q" placeholder="Search findings, URLs, evidence…">
  <select id="sort">
    <option value="sev">Sort: severity</option>
    <option value="count">Sort: most occurrences</option>
    <option value="cat">Sort: category</option>
  </select>
  <span class="sub" id="shown"></span>
</div>

<div id="list">{{FINDINGS}}</div>
<div class="empty hide" id="noresults">No findings match the current filter.</div>

<h2>Pages tested</h2>
<div class="tablewrap">{{PAGETABLE}}</div>

<footer>{{FOOTER}}</footer>
</div>

<script>
const list = document.getElementById('list');
const cards = Array.from(list.querySelectorAll('.finding'));
let sevFilter = null, catFilter = null;

document.querySelectorAll('.tile').forEach(t => t.addEventListener('click', () => {
  const s = t.dataset.sev;
  sevFilter = (sevFilter === s) ? null : s;
  document.querySelectorAll('.tile').forEach(x => x.classList.toggle('on', x.dataset.sev === sevFilter));
  apply();
}));
document.querySelectorAll('.pill').forEach(p => p.addEventListener('click', () => {
  const c = p.dataset.cat;
  catFilter = (catFilter === c) ? null : c;
  document.querySelectorAll('.pill').forEach(x => x.classList.toggle('on', x.dataset.cat === catFilter));
  apply();
}));
document.getElementById('q').addEventListener('input', apply);
document.getElementById('sort').addEventListener('change', () => {
  const mode = document.getElementById('sort').value;
  const sorted = cards.slice().sort((a, b) => {
    if (mode === 'count') return (+b.dataset.count) - (+a.dataset.count);
    if (mode === 'cat') return a.dataset.cat.localeCompare(b.dataset.cat) ||
                                (+a.dataset.weight) - (+b.dataset.weight);
    return (+a.dataset.weight) - (+b.dataset.weight) || (+b.dataset.count) - (+a.dataset.count);
  });
  sorted.forEach(c => list.appendChild(c));
});

function apply() {
  const q = document.getElementById('q').value.toLowerCase().trim();
  let n = 0;
  cards.forEach(c => {
    const okSev = !sevFilter || c.dataset.sev === sevFilter;
    const okCat = !catFilter || c.dataset.cat === catFilter;
    const okQ = !q || c.dataset.search.includes(q);
    const show = okSev && okCat && okQ;
    c.classList.toggle('hide', !show);
    if (show) n++;
  });
  document.getElementById('shown').textContent = n + ' of ' + cards.length + ' findings shown';
  document.getElementById('noresults').classList.toggle('hide', n > 0);
}
list.addEventListener('click', e => {
  const h = e.target.closest('.fh');
  if (h) h.parentElement.classList.toggle('open');
});
function expandAll(){ cards.forEach(c => { if(!c.classList.contains('hide')) c.classList.add('open'); }); }
function collapseAll(){ cards.forEach(c => c.classList.remove('open')); }
apply();
</script>
</body>
</html>
"""
