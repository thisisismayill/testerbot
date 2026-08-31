"""The HTML page served by testerbot_ui.py (Azerbaijani interface)."""

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TesterBot</title>
<style>
:root{
  --bg:#f6f7f9; --panel:#fff; --ink:#15181d; --muted:#5f6772; --line:#e3e6ea;
  --accent:#2f5fd0; --accent-ink:#fff; --ok:#1e7a45; --warn:#8a6100; --warn-bg:#fdf6e3;
  --crit:#b3261e; --crit-bg:#fdecea; --high:#c2510a; --med:#8a6100; --low:#0b6b8a; --info:#4a5361;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root{--bg:#0f1216;--panel:#161a20;--ink:#e7eaee;--muted:#98a1ad;--line:#262c35;
    --accent:#4f7ae0;--ok:#5fd08a;--warn:#e8c559;--warn-bg:#2a2411;
    --crit:#ff7b70;--crit-bg:#2c1614;--high:#ffa45c;--med:#e8c559;--low:#6fc7e6;--info:#a8b2bf;}
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:30px 20px 70px}
h1{font-size:22px;margin:0 0 4px}
h1 span{color:var(--accent)}
.sub{color:var(--muted);font-size:13.5px;margin-bottom:26px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;
  margin-bottom:16px}
label.fl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--muted);font-weight:700;margin-bottom:6px}
.urlrow{display:flex;gap:10px}
.modes{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}
.mode{display:flex;flex-direction:column;align-items:flex-start;gap:2px;text-align:left;
  padding:13px 16px;border:1px solid var(--line);border-radius:12px;background:var(--panel);
  color:var(--ink);cursor:pointer}
.mode b{font-size:14.5px}
.mode small{color:var(--muted);font-size:12px}
.mode:hover{border-color:var(--accent)}
.mode.on{border-color:var(--accent);background:var(--accent);color:#fff}
.mode.on small{color:rgba(255,255,255,.85)}
textarea{flex:1;padding:12px 14px;border:1px solid var(--line);border-radius:10px;
  background:var(--bg);color:var(--ink);font:14px/1.5 var(--mono, ui-monospace),monospace;resize:vertical;min-height:120px}
textarea:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:transparent}
input[type=text],input[type=password],input[type=number]{width:100%;padding:13px 14px;
  border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink);font-size:15px}
input:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:transparent}
#url{font-size:16px}
button{font:inherit;cursor:pointer;border-radius:10px;border:1px solid var(--line);
  background:var(--panel);color:var(--ink);padding:12px 16px}
button:hover{border-color:var(--accent);color:var(--accent)}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600;
  padding:13px 26px;white-space:nowrap}
button.primary:hover{filter:brightness(1.08);color:#fff}
button:disabled{opacity:.5;cursor:not-allowed;filter:none}
button.danger{border-color:var(--crit);color:var(--crit)}
details{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}
summary{cursor:pointer;font-size:13.5px;color:var(--muted);font-weight:600;user-select:none}
summary:hover{color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:14px}
.chk{display:flex;gap:9px;align-items:flex-start;font-size:14px;padding:9px 11px;
  border:1px solid var(--line);border-radius:10px;background:var(--bg)}
.chk input{margin-top:3px;flex:none}
.chk small{display:block;color:var(--muted);font-size:12px;line-height:1.4}
.chk.warn{background:var(--warn-bg);border-color:var(--warn)}
.hint{font-size:12.5px;color:var(--muted);margin-top:8px}
#log{display:none;background:#0b0e12;color:#c8d3e0;border-radius:10px;padding:14px;
  font-family:var(--mono);font-size:12.5px;line-height:1.5;height:300px;overflow-y:auto;
  white-space:pre-wrap;word-break:break-word;border:1px solid var(--line)}
#log .g{color:#7ee0a2}.b{color:#ffb86b}.r{color:#ff8a80}
.status{display:flex;align-items:center;gap:10px;font-size:14px;margin-bottom:12px}
.dot{width:9px;height:9px;border-radius:50%;background:var(--muted);flex:none}
.dot.run{background:var(--accent);animation:pulse 1.1s infinite}
.dot.ok{background:var(--ok)}.dot.err{background:var(--crit)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.tiles{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:16px 0}
.tile{border:1px solid var(--line);border-left-width:4px;border-radius:10px;padding:11px 12px;
  background:var(--bg)}
.tile .n{font-size:22px;font-weight:700;line-height:1.1}
.tile .l{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.tile.c{border-left-color:var(--crit)}.tile.c .n{color:var(--crit)}
.tile.h{border-left-color:var(--high)}.tile.h .n{color:var(--high)}
.tile.m{border-left-color:var(--med)}.tile.m .n{color:var(--med)}
.tile.l{border-left-color:var(--low)}.tile.l .n{color:var(--low)}
.tile.i{border-left-color:var(--info)}.tile.i .n{color:var(--info)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:9px 6px;border-bottom:1px solid var(--line)}
th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
tr:last-child td{border-bottom:none}
a{color:var(--accent)}
.err-box{background:var(--crit-bg);color:var(--crit);border-radius:10px;padding:11px 13px;
  font-size:13.5px;margin-bottom:12px}
.hide{display:none!important}
.intel-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.icell{background:var(--bg);border:1px solid var(--line);border-radius:11px;padding:12px 14px}
.icell .il{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700}
.icell .ib{font-family:var(--mono);font-size:1.35rem;font-weight:600;margin-top:3px;color:var(--accent)}
.icell .ib small{font-size:.7rem;color:var(--muted);font-weight:400}
.icell .is{font-size:12px;color:var(--muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media (max-width:560px){.urlrow{flex-direction:column}.tiles{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="wrap">
  <h1><span>TesterBot</span> — website test bot</h1>
  <div class="sub" id="tagline">Paste a site address and press <b>Start test</b>. The bot walks the
    site, clicks the buttons, tries the forms and writes you a report.</div>

  <div class="modes">
    <button class="mode on" id="mode-qa" data-mode="qa">
      <b>One site · QA</b><small>bugs, intelligence, link graph</small></button>
    <button class="mode" id="mode-index" data-mode="index">
      <b>Many sites · Index</b><small>backlinks + Domain Authority</small></button>
  </div>

  <div class="card">
    <div id="qa-input">
      <label class="fl" for="url">Site address</label>
      <div class="urlrow">
        <input type="text" id="url" placeholder="https://your-site.com" autocomplete="off" spellcheck="false">
        <button class="primary" id="run">Start test</button>
      </div>
      <div class="hint">Only test a site you own, or one you have written permission to test.</div>
    </div>
    <div id="index-input" class="hide">
      <label class="fl" for="domains">Domains — one per line</label>
      <div class="urlrow">
        <textarea id="domains" rows="5" placeholder="site-1.com&#10;site-2.com&#10;rival-3.com" spellcheck="false"></textarea>
        <button class="primary" id="run-index">Build index</button>
      </div>
      <div class="hint">Crawls several sites together, collects the links between them and computes
        <b>our own Domain Authority</b>. The index grows every run. Only add sites you are allowed to crawl.</div>
    </div>

    <details id="opt">
      <summary>Settings</summary>
      <div class="grid">
        <div><label class="fl" for="pages">Maximum pages</label>
          <input type="number" id="pages" value="40" min="1" max="1000"></div>
        <div><label class="fl" for="depth">Depth</label>
          <input type="number" id="depth" value="3" min="1" max="10"></div>
      </div>
      <div class="grid">
        <label class="chk"><input type="checkbox" id="forms" checked>
          <span>Submit forms<small>Fills them with test data and sends</small></span></label>
        <label class="chk"><input type="checkbox" id="clicks" checked>
          <span>Click controls<small>Tabs, menus, modals — everything</small></span></label>
        <label class="chk"><input type="checkbox" id="ext" checked>
          <span>External links<small>Check links to other sites too</small></span></label>
        <label class="chk"><input type="checkbox" id="axe" checked>
          <span>Accessibility audit<small>axe-core, WCAG 2.1</small></span></label>
        <label class="chk"><input type="checkbox" id="resp" checked>
          <span>Mobile check<small>390px and 820px screens</small></span></label>
        <label class="chk"><input type="checkbox" id="intel" checked>
          <span>Site intelligence<small>authority, performance, technology</small></span></label>
        <label class="chk"><input type="checkbox" id="perf" checked>
          <span>Performance (PageSpeed)<small>a little slow — you can turn it off</small></span></label>
        <label class="chk"><input type="checkbox" id="headed">
          <span>Show the browser<small>Watch what it does</small></span></label>
        <label class="chk"><input type="checkbox" id="shots">
          <span>Screenshot every page<small>Even where nothing is wrong</small></span></label>
        <label class="chk warn"><input type="checkbox" id="danger">
          <span>Danger mode<small>Also clicks delete and payment buttons.
            TEST SITES ONLY!</small></span></label>
      </div>
      <div class="grid">
        <div><label class="fl" for="inc">Only these URLs (regex)</label>
          <input type="text" id="inc" placeholder="/blog/"></div>
        <div><label class="fl" for="exc">Skip these URLs (regex)</label>
          <input type="text" id="exc" placeholder="/admin"></div>
      </div>
    </details>

    <details id="auth">
      <summary>Test behind a login too</summary>
      <div class="grid">
        <div><label class="fl" for="luser">Username / email</label>
          <input type="text" id="luser" autocomplete="off"></div>
        <div><label class="fl" for="lpass">Password</label>
          <input type="password" id="lpass" autocomplete="new-password"></div>
        <div><label class="fl" for="lurl">Login page</label>
          <input type="text" id="lurl" placeholder="https://site.com/login"></div>
        <div><label class="fl" for="lok">Success marker (part of the URL)</label>
          <input type="text" id="lok" placeholder="/dashboard"></div>
      </div>
      <div class="hint">Use a TEST account only. The password stays on this computer and is never
        sent anywhere.</div>
    </details>

    <details id="keys">
      <summary>Intelligence keys (free — once)</summary>
      <div class="grid">
        <div><label class="fl" for="oprk">OpenPageRank key</label>
          <input type="text" id="oprk" autocomplete="off" placeholder="for domain authority"></div>
        <div><label class="fl" for="psik">PageSpeed key <span style="text-transform:none;color:var(--faint)">(optional)</span></label>
          <input type="text" id="psik" autocomplete="off" placeholder="Google API key"></div>
      </div>
      <div class="hint">
        For the authority score, get a free OpenPageRank key:
        <a href="https://www.domcop.com/openpagerank/" target="_blank" rel="noopener">domcop.com/openpagerank</a> →
        sign up → “Add a domain” → copy the key. Performance works without a key too (the limit is just lower);
        a <a href="https://developers.google.com/speed/docs/insights/v5/get-started" target="_blank" rel="noopener">free Google key</a>
        raises it. Keys are stored on this computer only.
      </div>
    </details>
  </div>

  <div class="card hide" id="runcard">
    <div class="status">
      <span class="dot" id="dot"></span><span id="stat">Waiting…</span>
      <span style="flex:1"></span>
      <button id="stop" class="danger hide">Stop</button>
    </div>
    <div class="err-box hide" id="err"></div>
    <div class="intel-strip hide" id="intelStrip"></div>
    <div class="tiles hide" id="tiles">
      <div class="tile c"><div class="n" id="t-c">0</div><div class="l">Critical</div></div>
      <div class="tile h"><div class="n" id="t-h">0</div><div class="l">High</div></div>
      <div class="tile m"><div class="n" id="t-m">0</div><div class="l">Medium</div></div>
      <div class="tile l"><div class="n" id="t-l">0</div><div class="l">Low</div></div>
      <div class="tile i"><div class="n" id="t-i">0</div><div class="l">Info</div></div>
    </div>
    <div id="openrow" class="hide" style="margin-bottom:14px">
      <button class="primary" id="open">Open the report</button>
      <span class="hint" id="where"></span>
    </div>
    <div id="log"></div>
  </div>

  <div class="card" id="histcard">
    <label class="fl">Previous tests</label>
    <table><tbody id="hist"><tr><td class="hint">Nothing tested yet.</td></tr></tbody></table>
  </div>

  <div style="text-align:center;margin-top:22px">
    <button id="quit" style="font-size:13px;padding:9px 16px">Close the app</button>
    <div class="hint" style="margin-top:6px">If you close it, double-click the TesterBot icon to
      open it again.</div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let MODE = 'qa';
function setMode(m){
  MODE = m;
  document.querySelectorAll('.mode').forEach(b=>b.classList.toggle('on', b.dataset.mode===m));
  $('qa-input').classList.toggle('hide', m!=='qa');
  $('index-input').classList.toggle('hide', m!=='qa'?false:true);
  $('index-input').classList.toggle('hide', m!=='index');
  // QA-only option blocks
  ['auth','keys'].forEach(id=>{ const e=$(id); if(e) e.classList.toggle('hide', m!=='qa'); });
  $('tagline').innerHTML = (m==='index')
    ? 'Crawls several domains together, collects the backlinks between them and computes <b>our own Domain Authority</b> — the same core as Ahrefs.'
    : 'Paste a site address and press <b>Start test</b>. The bot walks the site, clicks the buttons, tries the forms and writes you a report.';
}
document.querySelectorAll('.mode').forEach(b=> b.addEventListener('click',()=>setMode(b.dataset.mode)));

let polling = null, lastLine = 0, currentReport = null;

function el(v){ return $(v).value.trim(); }

async function api(path, body){
  const r = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json'},
                                      body:JSON.stringify(body)} : {});
  return r.json();
}

$('run').addEventListener('click', async () => {
  let url = el('url');
  if (!url) { alert('Enter a site address first.'); $('url').focus(); return; }
  if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
  if ($('danger').checked &&
      !confirm('Danger mode is on. The bot will also click delete and payment buttons, '
             + 'and may destroy data on the site.\n\nContinue?')) return;

  const cfg = {
    url: url,
    max_pages: +el('pages') || 40, max_depth: +el('depth') || 3,
    submit_forms: $('forms').checked, click_elements: $('clicks').checked,
    check_external_links: $('ext').checked, run_axe: $('axe').checked,
    responsive_checks: $('resp').checked, headless: !$('headed').checked,
    screenshot_all: $('shots').checked, danger_mode: $('danger').checked,
    include: el('inc'), exclude: el('exc'),
    run_intelligence: $('intel').checked, run_performance: $('perf').checked,
    opr_key: el('oprk'), psi_key: el('psik'),
    username: el('luser'), password: el('lpass'),
    login_url: el('lurl'), login_success_url: el('lok'),
  };
  cfg.mode = 'qa';
  const res = await api('/api/run', cfg);
  if (res.error) { alert(res.error); return; }
  startUI();
});

$('run-index').addEventListener('click', async () => {
  const domains = $('domains').value.trim();
  if (!domains) { alert('Enter at least one domain.'); $('domains').focus(); return; }
  const cfg = {
    mode: 'index', domains: domains,
    max_pages: +el('pages') || 25, max_depth: +el('depth') || 3,
    headless: !$('headed').checked,
  };
  const res = await api('/api/run', cfg);
  if (res.error) { alert(res.error); return; }
  startUI();
});

function startUI(){
  lastLine = 0; currentReport = null;
  $('runcard').classList.remove('hide');
  $('log').style.display='block'; $('log').textContent='';
  $('tiles').classList.add('hide'); $('openrow').classList.add('hide');
  $('intelStrip') && $('intelStrip').classList.add('hide');
  $('err').classList.add('hide');
  $('stop').classList.remove('hide');
  const idx = MODE === 'index';
  const btn = idx ? $('run-index') : $('run');
  btn.disabled = true; btn.dataset.label = btn.textContent; btn.textContent = 'Working…';
  $('dot').className = 'dot run';
  $('stat').textContent = idx ? 'Building the index…' : 'Testing…';
  $('open').textContent = idx ? 'Open the index' : 'Open the report';
  $('runcard').scrollIntoView({behavior:'smooth', block:'nearest'});
  if (polling) clearInterval(polling);
  polling = setInterval(poll, 800);
  poll();
}

$('stop').addEventListener('click', async () => { await api('/api/stop', {}); });
$('open').addEventListener('click', () => { if (currentReport) window.open(currentReport, '_blank'); });

function colour(line){
  const e = document.createElement('div');
  if (/CRITICAL|\bcritical\b|Run aborted|Traceback/.test(line)) e.className='r';
  else if (/HIGH|finished|✓/.test(line)) e.className='g';
  else if (/^\s*\[|→/.test(line)) e.className='b';
  e.textContent = line;
  return e;
}

async function poll(){
  let d;
  try { d = await api('/api/log?since=' + lastLine); } catch(e){ return; }
  const box = $('log');
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
  (d.lines || []).forEach(l => box.appendChild(colour(l)));
  lastLine = d.next || lastLine;
  if (atBottom) box.scrollTop = box.scrollHeight;

  if (d.status === 'running') {
    $('stat').textContent = d.progress || 'Testing…';
    return;
  }
  clearInterval(polling); polling = null;
  $('stop').classList.add('hide');
  $('run').disabled = false; $('run').textContent = 'Start test';
  const rib = $('run-index'); if (rib){ rib.disabled = false; rib.textContent = 'Build index'; }
  const idx = d.mode === 'index';
  if (d.status === 'stopped') {
    $('dot').className='dot err'; $('stat').textContent='Stopped.';
  } else if (d.status === 'error') {
    $('dot').className='dot err'; $('stat').textContent='Something went wrong.';
    $('err').textContent = d.error || 'Unknown error.'; $('err').classList.remove('hide');
  } else if (idx) {
    $('dot').className='dot ok';
    const st = d.index || {};
    $('stat').textContent = 'Index ready · ' + (st.domains||0) + ' domains · '
      + (st.cross_domain_edges||0) + ' backlink';
  } else {
    $('dot').className='dot ok';
    $('stat').textContent = 'Done · ' + (d.summary ? d.summary.total : 0) + ' findings';
  }
  if (!idx && d.intel && (d.intel.tech || d.intel.authority)){
    renderIntel(d.intel);
  }
  if (!idx && d.summary){
    const s = d.summary.severity || {};
    $('t-c').textContent=s.critical||0; $('t-h').textContent=s.high||0;
    $('t-m').textContent=s.medium||0; $('t-l').textContent=s.low||0;
    $('t-i').textContent=s.info||0;
    $('tiles').classList.remove('hide');
  }
  if (idx && d.index){
    renderIndexStrip(d.index);
  }
  if (d.report){
    currentReport = d.report;
    $('where').textContent = d.folder || '';
    $('open').textContent = idx ? 'Open the index' : 'Open the report';
    $('openrow').classList.remove('hide');
  }
  loadHistory();
}

function renderIndexStrip(st){
  const strip = $('intelStrip'); if(!strip) return;
  const cells = [
    ['Domains', st.domains||0, (st.crawled_domains||0)+' crawled'],
    ['Backlinks', st.cross_domain_edges||0, 'cross-domain'],
    ['Pages', st.pages||0, ''],
    ['Links (edges)', st.edges||0, 'total'],
  ];
  strip.innerHTML = cells.map(c =>
    '<div class="icell"><div class="il">'+c[0]+'</div><div class="ib">'+c[1]+'</div>'
    + (c[2]?'<div class="is">'+c[2]+'</div>':'') + '</div>').join('');
  strip.classList.remove('hide');
}

async function loadHistory(){
  const d = await api('/api/runs');
  const t = $('hist');
  if (!d.runs || !d.runs.length){
    t.innerHTML = '<tr><td class="hint">Nothing tested yet.</td></tr>'; return;
  }
  t.innerHTML = '<tr><th>Date</th><th>Site</th><th>Pages</th><th>Findings</th><th></th></tr>' +
    d.runs.map(r => `<tr><td>${r.when}</td><td>${r.target}</td><td>${r.pages}</td>
      <td>${r.critical+r.high} ciddi / ${r.total}</td>
      <td><a href="${r.report}" target="_blank">Open</a></td></tr>`).join('');
}

$('quit').addEventListener('click', async () => {
  if (!confirm('Close TesterBot?')) return;
  try { await fetch('/api/quit', {method:'POST'}); } catch(e){}
  document.body.innerHTML = '<div style="max-width:600px;margin:120px auto;text-align:center;'
    + 'font:16px system-ui;color:#888">TesterBot is closed.<br><br>'
    + 'Double-click the <b>TesterBot</b> icon to open it again.<br>'
    + 'You can close this window.</div>';
});

function renderIntel(i){
  const strip = $('intelStrip'); if(!strip) return;
  const parts = [];
  const a = i.authority || {};
  if (a.found) parts.push(cell('Avtoritet', a.score + '<small>/10</small>', a.rank ? '#'+a.rank : ''));
  const p = i.performance || {};
  if (p.available && p.lab_score != null) parts.push(cell('Performans', p.lab_score + '<small>/100</small>', 'mobil'));
  const t = i.tech || {};
  if (t.count) parts.push(cell('Texnologiya', t.count, techList(t.by_category)));
  const h = i.hosting || {};
  if (h.cdn || h.server) parts.push(cell('Hosting', h.cdn || (h.server||'').split('/')[0], h.ip||''));
  if(!parts.length){ strip.classList.add('hide'); return; }
  strip.innerHTML = parts.join('');
  strip.classList.remove('hide');
}
function cell(label,big,sub){
  return '<div class="icell"><div class="il">'+label+'</div><div class="ib">'+big+'</div>'
    + (sub?'<div class="is">'+sub+'</div>':'')+'</div>';
}
function techList(bycat){
  if(!bycat) return '';
  const names=[]; for(const k in bycat){ for(const n of bycat[k]){ if(names.length<4) names.push(n);} }
  return names.join(' · ');
}

(async function init(){
  const d = await api('/api/state');
  if (d.last){
    $('url').value = d.last.url || '';
    if (d.last.max_pages) $('pages').value = d.last.max_pages;
    if (d.last.max_depth) $('depth').value = d.last.max_depth;
    if (d.last.login_url){ $('lurl').value=d.last.login_url; $('auth').open=true; }
    if (d.last.username) $('luser').value = d.last.username;
    if (d.last.login_success_url) $('lok').value = d.last.login_success_url;
    if (d.last.opr_key){ $('oprk').value = d.last.opr_key; $('keys').open = true; }
    if (d.last.psi_key) $('psik').value = d.last.psi_key;
    if (d.last.domains) $('domains').value = d.last.domains;
    if (d.last.mode === 'index') setMode('index');
  }
  $('url').focus();
  loadHistory();
  if (d.running) startUI();
})();
</script>
</body>
</html>
"""
