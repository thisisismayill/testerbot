"""The Index Explorer — a self-contained dashboard over the link index.

Domain Authority leaderboard + click-through into each domain's backlinks
(who links to it, with anchor text and follow/nofollow), all computed from
data we crawled ourselves. Data is embedded in the page as JSON so the file
is fully portable.
"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List

from . import __version__


def esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def _build_detail(store, leaderboard: List[Dict[str, Any]]) -> Dict[str, Any]:
    da = {r["domain"]: r["authority"] for r in leaderboard}
    detail: Dict[str, Any] = {}
    for r in leaderboard:
        d = r["domain"]
        refs = store.referring_domains(d)
        for ref in refs:
            ref["authority"] = da.get(ref["domain"], 0)
        refs.sort(key=lambda x: (x["authority"], x["links"]), reverse=True)
        bl = store.backlinks(d, limit=60)
        out = store.outbound_domains(d)
        for o in out:
            o["authority"] = da.get(o["domain"], 0)
        detail[d] = {
            "referring_domains": refs[:60],
            "backlinks": bl,
            "outbound": out[:60],
        }
    return detail


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root{
  --ground:#EBEEF2;--surface:#fff;--surface-2:#F4F6F9;--ink:#141C25;--muted:#5A6673;
  --faint:#8A94A0;--line:#DBE0E6;--line-2:#E7EBF0;--accent:#0C6D79;--accent-ink:#0C6D79;
  --accent-soft:#DCEDEF;--signal:#BB5E17;--good:#1C7A4B;--good-soft:#DCEFE3;
  --warn:#8A5A00;--warn-soft:#F5E9CE;--bad:#A93529;--bad-soft:#F4DDD8;
  --shadow:0 1px 2px rgba(20,28,37,.05),0 8px 30px rgba(20,28,37,.06);
  --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,sans-serif;
  --serif:"Fraunces",Georgia,serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#0D131A;--surface:#141D26;--surface-2:#101821;--ink:#E6ECF2;--muted:#96A2AF;
  --faint:#69747F;--line:#243039;--line-2:#1C262F;--accent:#3BB6C2;--accent-ink:#4FC5D0;
  --accent-soft:#13333A;--signal:#E28A46;--good:#54C489;--good-soft:#12301F;
  --warn:#D6A54A;--warn-soft:#2E2410;--bad:#E4715F;--bad-soft:#331714;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 30px rgba(0,0,0,.35);}}
:root[data-theme="dark"]{
  --ground:#0D131A;--surface:#141D26;--surface-2:#101821;--ink:#E6ECF2;--muted:#96A2AF;
  --faint:#69747F;--line:#243039;--line-2:#1C262F;--accent:#3BB6C2;--accent-ink:#4FC5D0;
  --accent-soft:#13333A;--signal:#E28A46;--good:#54C489;--good-soft:#12301F;
  --warn:#D6A54A;--warn-soft:#2E2410;--bad:#E4715F;--bad-soft:#331714;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 30px rgba(0,0,0,.35);}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 22px}
header.top{padding:34px 0 26px;border-bottom:1px solid var(--line);margin-bottom:26px}
.brand{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
h1{font-family:var(--serif);font-size:26px;font-weight:600;margin:0;letter-spacing:-.01em}
h1 .m{color:var(--accent-ink)}
.tag{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);border:1px solid var(--line);border-radius:100px;padding:4px 10px}
.sub{color:var(--muted);font-size:13.5px;margin-top:8px;max-width:70ch}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:26px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:15px 17px;box-shadow:var(--shadow)}
.tile .n{font-family:var(--mono);font-size:1.7rem;font-weight:600;letter-spacing:-.02em;line-height:1}
.tile .l{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-top:5px}
.layout{display:grid;grid-template-columns:1.15fr 1fr;gap:18px;align-items:start}
@media (max-width:900px){.layout{grid-template-columns:1fr}}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);overflow:hidden}
.phead{display:flex;align-items:center;gap:10px;padding:15px 18px;border-bottom:1px solid var(--line-2)}
.phead h2{font-size:14px;margin:0;font-weight:700;letter-spacing:.01em}
.phead .hint{margin-left:auto;font-size:12px;color:var(--faint)}
.lb{max-height:640px;overflow-y:auto}
.row{display:grid;grid-template-columns:34px 1fr auto;gap:12px;align-items:center;
  padding:12px 18px;border-top:1px solid var(--line-2);cursor:pointer}
.row:first-child{border-top:none}
.row:hover{background:var(--surface-2)}
.row.sel{background:var(--accent-soft)}
.rank{font-family:var(--mono);font-size:12px;color:var(--faint);text-align:right}
.dinfo{min-width:0}
.dname{font-weight:600;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;gap:7px}
.crawled{width:7px;height:7px;border-radius:50%;background:var(--good);flex:none}
.dmeta{font-size:12px;color:var(--muted);font-family:var(--mono);margin-top:2px}
.da{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex:none;width:112px}
.da .v{font-family:var(--mono);font-weight:600;font-size:15px;color:var(--accent-ink)}
.da .bar{width:100%;height:6px;border-radius:4px;background:var(--surface-2);overflow:hidden;border:1px solid var(--line-2)}
.da .bar span{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--signal));border-radius:4px}
#detail .empty{padding:40px 24px;text-align:center;color:var(--muted);font-size:13.5px}
.dh{padding:16px 18px;border-bottom:1px solid var(--line-2)}
.dh .dn{font-family:var(--serif);font-size:19px;font-weight:600}
.dh .ds{font-size:12.5px;color:var(--muted);font-family:var(--mono);margin-top:4px;display:flex;gap:14px;flex-wrap:wrap}
.dh .ds b{color:var(--ink)}
.sec{padding:14px 18px;border-top:1px solid var(--line-2)}
.sec .cap{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.sec .cap .ct{margin-left:auto;font-family:var(--mono);color:var(--faint);font-weight:500}
.ref{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px dashed var(--line-2);font-size:13px}
.ref:first-of-type{border-top:none}
.ref .rda{font-family:var(--mono);font-size:11px;font-weight:600;width:34px;text-align:center;
  padding:2px 0;border-radius:5px;background:var(--accent-soft);color:var(--accent-ink);flex:none}
.ref .rd{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ref .rl{font-family:var(--mono);font-size:11.5px;color:var(--muted);flex:none}
.nf{font-size:9.5px;padding:1px 6px;border-radius:20px;background:var(--warn-soft);color:var(--warn);flex:none}
.anchor{font-size:12px;color:var(--muted);padding:5px 0;border-top:1px dashed var(--line-2)}
.anchor:first-of-type{border-top:none}
.anchor b{color:var(--ink);font-weight:500}
.anchor .src{font-family:var(--mono);font-size:10.5px;color:var(--faint);display:block;margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.controls{padding:12px 18px;border-bottom:1px solid var(--line-2)}
input[type=search]{width:100%;padding:9px 12px;border:1px solid var(--line);border-radius:9px;
  background:var(--surface-2);color:var(--ink);font-size:14px;font-family:var(--sans)}
input[type=search]:focus{outline:2px solid var(--accent);outline-offset:-1px}
footer{margin-top:34px;padding:20px 0 50px;border-top:1px solid var(--line);color:var(--faint);font-size:12px}
.note{background:var(--warn-soft);color:var(--ink);border-radius:12px;padding:12px 16px;font-size:13px;margin-bottom:22px;border:1px solid color-mix(in srgb,var(--warn) 30%,transparent)}
.intersect{margin-top:18px}
.ix-controls{padding:14px 18px;border-bottom:1px solid var(--line-2);display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.ixl{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600}
#ix-me{padding:8px 12px;border:1px solid var(--line);border-radius:9px;background:var(--surface-2);color:var(--ink);font-size:14px;font-family:var(--sans);min-width:200px}
.ix-note{font-size:12px;color:var(--faint);flex:1;min-width:200px}
.ix-row{display:grid;grid-template-columns:34px 1fr auto auto;gap:12px;align-items:center;padding:11px 18px;border-top:1px solid var(--line-2)}
.ix-row:first-child{border-top:none}
.ix-da{font-family:var(--mono);font-size:11px;font-weight:600;text-align:center;padding:2px 0;border-radius:5px;background:var(--accent-soft);color:var(--accent-ink)}
.ix-dom{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ix-hits{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end;max-width:340px}
.ix-hit{font-family:var(--mono);font-size:10.5px;padding:2px 8px;border-radius:20px;background:var(--surface-2);border:1px solid var(--line-2);color:var(--muted)}
.ix-count{font-family:var(--mono);font-size:12px;font-weight:600;color:var(--signal);white-space:nowrap}
.ix-empty{padding:34px 24px;text-align:center;color:var(--muted);font-size:13.5px}
.hide{display:none!important}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand">
      <h1><span class="m">TesterBot</span> Index</h1>
      <span class="tag">our own link index · our own authority metric</span>
    </div>
    <p class="sub">These scores come from no third party — every one is computed from links we
      crawled ourselves. <b>Domain Authority</b> is computed with PageRank over the cross-domain
      link graph, the same principle as Ahrefs' DR and Moz's DA. Click a domain to see who links
      to it.</p>
  </header>

  __NOTE__

  <div class="tiles">__TILES__</div>

  <div class="layout">
    <div class="panel">
      <div class="phead"><h2>Domain Authority · ranking</h2><span class="hint">click a domain</span></div>
      <div class="controls"><input type="search" id="q" placeholder="Search domains…"></div>
      <div class="lb" id="lb"></div>
    </div>
    <div class="panel" id="detail">
      <div class="empty">Pick a domain on the left — its referring domains, backlinks
        and anchor text will appear here.</div>
    </div>
  </div>

  <div class="panel intersect" id="intersect">
    <div class="phead">
      <h2>Link Intersect · opportunities</h2>
      <span class="hint">domains that link to your rivals but not to you</span>
    </div>
    <div class="ix-controls">
      <label class="ixl" for="ix-me">Your domain</label>
      <select id="ix-me"></select>
      <span class="ix-note">These domains link to other sites in the index (your rivals) but
        not to you — the backlink opportunities within reach.</span>
    </div>
    <div id="ix-out"></div>
  </div>

  <footer>TesterBot Index v__VER__ · __STAMP__ · authority computed from our own crawl data,
    no third party.</footer>
</div>

<script>
const DATA = __DATA__;
const DETAIL = __DETAIL__;
const lb = document.getElementById('lb');

function daColor(v){ return v>=60?'var(--good)':(v>=25?'var(--signal)':'var(--muted)'); }

function renderList(filter){
  filter = (filter||'').toLowerCase();
  lb.innerHTML='';
  DATA.leaderboard.filter(r=>!filter||r.domain.toLowerCase().includes(filter))
    .forEach((r,i)=>{
    const row=document.createElement('div');
    row.className='row'; row.dataset.domain=r.domain;
    row.innerHTML =
      '<div class="rank">'+(i+1)+'</div>'+
      '<div class="dinfo"><div class="dname">'+(r.crawled?'<span class="crawled" title="crawled"></span>':'')+
        esc(r.domain)+'</div>'+
        '<div class="dmeta">'+r.referring_domains+' ref.domains · '+r.backlinks+' backlinks</div></div>'+
      '<div class="da"><span class="v">'+r.authority+'</span>'+
        '<span class="bar"><span style="width:'+Math.max(2,r.authority)+'%"></span></span></div>';
    row.addEventListener('click',()=>select(r.domain));
    lb.appendChild(row);
  });
}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

function select(domain){
  document.querySelectorAll('.row').forEach(x=>x.classList.toggle('sel',x.dataset.domain===domain));
  const r = DATA.leaderboard.find(x=>x.domain===domain);
  const d = DETAIL[domain] || {referring_domains:[],backlinks:[],outbound:[]};
  const el = document.getElementById('detail');
  let h = '<div class="dh"><div class="dn">'+esc(domain)+'</div>'+
    '<div class="ds"><span>Domain Authority: <b>'+r.authority+'</b></span>'+
    '<span>Ref. domains: <b>'+r.referring_domains+'</b></span>'+
    '<span>Backlinks: <b>'+r.backlinks+'</b></span>'+
    (r.crawled?'<span>crawled</span>':'<span>seen as a link only</span>')+'</div></div>';

  h += '<div class="sec"><div class="cap">Domains linking to it'+
       '<span class="ct">'+d.referring_domains.length+'</span></div>';
  if(d.referring_domains.length){
    d.referring_domains.slice(0,30).forEach(ref=>{
      h += '<div class="ref"><span class="rda" style="color:'+daColor(ref.authority)+'">'+ref.authority+'</span>'+
        '<span class="rd">'+esc(ref.domain)+'</span>'+
        (ref.follow?'':'<span class="nf">nofollow</span>')+
        '<span class="rl">'+ref.links+(ref.links==1?' link':' links')+'</span></div>';
    });
  } else { h += '<div class="ref" style="color:var(--muted)">No backlinks found yet.</div>'; }
  h += '</div>';

  if(d.backlinks && d.backlinks.length){
    h += '<div class="sec"><div class="cap">Anchor text · samples<span class="ct">'+d.backlinks.length+'</span></div>';
    d.backlinks.slice(0,14).forEach(b=>{
      h += '<div class="anchor"><b>'+(b.anchor?esc(b.anchor):'<i style="color:var(--faint)">(no text)</i>')+'</b>'+
        (b.nofollow?' <span class="nf">nofollow</span>':'')+
        '<span class="src">'+esc(b.from_url)+'</span></div>';
    });
    h += '</div>';
  }

  if(d.outbound && d.outbound.length){
    h += '<div class="sec"><div class="cap">Who this domain links to<span class="ct">'+d.outbound.length+'</span></div>';
    d.outbound.slice(0,20).forEach(o=>{
      h += '<div class="ref"><span class="rda" style="color:'+daColor(o.authority||0)+'">'+(o.authority||0)+'</span>'+
        '<span class="rd">'+esc(o.domain)+'</span><span class="rl">'+o.links+(o.links==1?' link':' links')+'</span></div>';
    });
    h += '</div>';
  }
  el.innerHTML = h;
}

document.getElementById('q').addEventListener('input',e=>renderList(e.target.value));

// ---- Link Intersect ----
function refSet(domain){
  const d = DETAIL[domain]; if(!d) return new Map();
  const m = new Map();
  (d.referring_domains||[]).forEach(r=>{ if(r.follow!==false || true) m.set(r.domain, r); });
  return m;
}
function buildIntersect(){
  const me = document.getElementById('ix-me').value;
  const out = document.getElementById('ix-out');
  const others = DATA.leaderboard.map(r=>r.domain).filter(d=>d!==me);
  const mine = refSet(me);
  // candidate referrer -> {competitors:Set, authority}
  const cand = new Map();
  others.forEach(comp=>{
    refSet(comp).forEach((info, referrer)=>{
      if(referrer===me) return;
      if(mine.has(referrer)) return;           // already links to you
      if(referrer===comp) return;
      const cur = cand.get(referrer) || {competitors:new Set(), authority:info.authority||0};
      cur.competitors.add(comp);
      cur.authority = Math.max(cur.authority, info.authority||0);
      cand.set(referrer, cur);
    });
  });
  const rows = [...cand.entries()]
    .map(([dom,v])=>({domain:dom, competitors:[...v.competitors], authority:v.authority}))
    .sort((a,b)=> b.competitors.length-a.competitors.length || b.authority-a.authority);
  if(!rows.length){
    out.innerHTML = '<div class="ix-empty">No opportunities found — either too few domains have been '
      + 'crawled, or this domain already has every shared referrer. '
      + 'Add more rival sites to the index.</div>';
    return;
  }
  out.innerHTML = rows.slice(0,40).map(r=>
    '<div class="ix-row"><span class="ix-da" style="color:'+daColor(r.authority)+'">'+r.authority+'</span>'
    + '<span class="ix-dom">'+esc(r.domain)+'</span>'
    + '<span class="ix-count">'+r.competitors.length+' rivals</span>'
    + '<span class="ix-hits">'+r.competitors.slice(0,4).map(c=>'<span class="ix-hit">'+esc(c)+'</span>').join('')+'</span>'
    + '</div>').join('');
}
(function initIntersect(){
  const sel = document.getElementById('ix-me');
  const crawled = DATA.leaderboard.filter(r=>r.crawled);
  const opts = (crawled.length?crawled:DATA.leaderboard);
  sel.innerHTML = opts.map(r=>'<option value="'+esc(r.domain)+'">'+esc(r.domain)+'</option>').join('');
  sel.addEventListener('change', buildIntersect);
  if(opts.length) buildIntersect();
})();

renderList('');
if(DATA.leaderboard.length) select(DATA.leaderboard[0].domain);
</script>
</body>
</html>
"""


def render_index(data: Dict[str, Any], store, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    st = data["stats"]
    detail = _build_detail(store, data["leaderboard"])

    tiles = [
        (st["domains"], "Domains"),
        (st["crawled_domains"], "Crawled"),
        (st["pages"], "Pages"),
        (st["edges"], "Links (edges)"),
        (st["cross_domain_edges"], "Cross-domain"),
        (data["computed_over_domains"], "In graph"),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="n">{v}</div><div class="l">{esc(l)}</div></div>'
        for v, l in tiles)

    note = ""
    if st["cross_domain_edges"] == 0:
        note = ('<div class="note">Only one domain has been crawled so far, so there are no '
                'cross-domain links yet. Crawl several sites together — that is when the '
                'backlink graph and the authority ranking start to mean something.</div>')

    import datetime
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    out = (TEMPLATE
           .replace("__TITLE__", "TesterBot Index")
           .replace("__NOTE__", note)
           .replace("__TILES__", tiles_html)
           .replace("__VER__", esc(__version__))
           .replace("__STAMP__", esc(stamp))
           .replace("__DATA__", json.dumps(data, ensure_ascii=False))
           .replace("__DETAIL__", json.dumps(detail, ensure_ascii=False)))

    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(out)
    with open(os.path.join(out_dir, "index-data.json"), "w", encoding="utf-8") as fh:
        json.dump({"leaderboard": data["leaderboard"], "stats": st,
                   "detail": detail}, fh, indent=2, ensure_ascii=False)
    return path
