"""A single-page app (the React kind) with a login, used to check TesterBot on
the things plain HTML test sites do not have:

  * every address answers 200 with the same page (robots.txt and sitemap.xml too)
  * the menu is made of <div>s with click handlers, not links
  * a "who am I" API call answers 401 to visitors
  * the login checks the password over the API, then the app redraws
  * the dashboard can only be reached by clicking, never by a link
  * a slider that is too wide only while the window is being resized
  * slips a human tester spots: a typo, "Forget Password?", a contact link that
    opens another address, an "optional" field that is required, a label wired
    to the wrong id

    TB_TEST_PASSWORD=... python testsite/spa_server.py      # http://localhost:8098

The test account is qa@example.test with the password from TB_TEST_PASSWORD.
"""
import json
import os
import secrets
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("TB_SPA_PORT", "8098"))
USER = "qa@example.test"
PASSWORD = os.environ.get("TB_TEST_PASSWORD") or secrets.token_urlsafe(12)
TOKENS = set()

SHELL = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Partner Program</title><meta name="description" content="Demo partner program.">
<style>
body{font-family:system-ui;margin:0}header{display:flex;gap:18px;align-items:center;padding:14px 20px;background:#2a0a55;color:#fff}
.nav{cursor:pointer;font-weight:600}.grow{flex:1}main{padding:20px;max-width:900px}
#slider{height:30px;background:#ddd}.wide{width:900px;background:#eee}
label{display:block;margin-top:10px}footer{padding:20px;background:#eee}
</style></head><body><div id="root"></div>
<script>
const $ = (t, a, ...kids) => { const e = document.createElement(t); Object.assign(e, a || {});
  for (const k of kids) e.append(k); return e; };
const token = () => localStorage.getItem('tok');
function go(path) { history.pushState(null, '', path); render(); }
window.addEventListener('popstate', render);
async function api(path, opts) {
  const h = {'Content-Type': 'application/json'};
  if (token()) h.Authorization = 'Bearer ' + token();
  return fetch(path, Object.assign({headers: h}, opts || {}));
}
function navItem(text, fn) { const d = $('div', {className: 'nav', textContent: text}); d.onclick = fn; return d; }
function header() {
  const h = $('header');
  if (token()) {
    h.append(navItem('Dashboard', () => go('/dashboard')), navItem('Reports', () => go('/reports')),
             navItem('Statistics', () => go('/statistics')),
             navItem('Settings', () => go('/settings')), $('div', {className: 'grow'}),
             navItem('Log out', () => { localStorage.removeItem('tok'); go('/'); }));
  } else {
    h.append(navItem('COMMISION', () => document.getElementById('commission').scrollIntoView()),
             navItem('FAQ', () => document.getElementById('faq').scrollIntoView()),
             $('div', {className: 'grow'}),
             $('button', {textContent: 'SIGN UP', onclick: () => go('/registration')}),
             $('button', {textContent: 'LOG IN', onclick: () => go('/login')}));
  }
  return h;
}
function footer() {
  const f = $('footer');
  const p = $('p', null, 'Email: ');
  p.append($('a', {href: 'mailto:partnership@example.test', textContent: 'info@example.test'}));
  f.append(p);
  return f;
}
function home() {
  const m = $('main');
  const slider = $('div', {id: 'slider'});
  const size = () => { slider.style.width = Math.max(0, window.innerWidth - 60) + 'px'; };
  size(); let t = 0;
  window.onresize = () => { clearTimeout(t); t = setTimeout(size, 600); };   // re-measures late
  m.append($('h3', {textContent: 'Join the best affiliate program'}), slider,
           $('p', {textContent: 'Earn big commissions advertising high-profile brands. ' +
                                'Partners get weekly payouts and a personal manager.'}),
           $('h5', {id: 'commission', textContent: 'COMMISSION'}),
           $('p', {textContent: 'Our commission is paid every week. The commission rate grows with your traffic.'}),
           $('h5', {id: 'faq', textContent: 'FAQ'}),
           $('p', {textContent: 'How do I get paid? Every Monday, to the wallet in your profile.'}),
           $('p', {textContent: 'Which brands can I promote? Every brand in the network, in every country ' +
                                'where online gaming is legal. You get banners, landing pages and tracking ' +
                                'links for each of them, and a dashboard that shows clicks, sign-ups and ' +
                                'earnings in real time. Questions go to your personal manager.'}));
  return m;
}
function login() {
  const m = $('main'), msg = $('p', {id: 'msg'});
  const f = $('form');
  f.append($('h1', {textContent: 'Log in'}),
    $('label', {htmlFor: 'em', textContent: 'Email'}), $('input', {id: 'em', type: 'email', required: true}),
    $('label', {htmlFor: 'pw', textContent: 'Password'}), $('input', {id: 'pw', type: 'password', required: true}),
    $('button', {type: 'submit', textContent: 'LOG IN'}), msg);
  const a = $('a', {href: '/password-recovery', textContent: 'Forget Password?'});
  a.onclick = (e) => { e.preventDefault(); go('/password-recovery'); };
  f.onsubmit = async (e) => {
    e.preventDefault(); msg.textContent = '';
    const r = await api('/api/login', {method: 'POST', body: JSON.stringify({email: f.em.value, password: f.pw.value})});
    if (r.ok) { localStorage.setItem('tok', (await r.json()).token); setTimeout(() => go('/dashboard'), 400); }
    else msg.textContent = 'Invalid email or password.';
  };
  m.append(f, a);
  return m;
}
function registration() {
  const m = $('main'), f = $('form');
  f.append($('h1', {textContent: 'Sign up'}),
    $('label', {htmlFor: 'co', textContent: 'Company Name (optional)'}), $('input', {id: 'co', type: 'text', required: true}),
    $('label', {htmlFor: 'em2', textContent: 'Email'}), $('input', {id: 'em2', type: 'email'}),
    $('input', {type: 'tel'}),
    $('label', {htmlFor: 'p1', textContent: 'Password'}), $('input', {id: 'p1', type: 'password', required: true}),
    $('button', {type: 'button', innerHTML: '<svg width="16" height="16"><circle cx="8" cy="8" r="4"/></svg>'}),
    $('button', {type: 'submit', textContent: 'Register'}));
  f.onsubmit = (e) => e.preventDefault();
  m.append(f);
  return m;
}
function recovery() {
  const m = $('main');
  m.append($('h1', {textContent: 'Request password reset'}),
    $('label', {htmlFor: 'field-:r0:', textContent: 'Email'}), $('input', {id: 'email', type: 'email'}));
  return m;
}
function dashboard() {
  const m = $('main'), stats = $('p', {textContent: 'Loading…'});
  api('/api/stats').then(r => r.json()).then(d => { stats.textContent = 'Clicks: ' + d.clicks + ' · Earnings: ' + d.earnings; });
  const pw = $('form', {id: 'pwform'});
  pw.append($('label', {htmlFor: 'np', textContent: 'New password'}), $('input', {id: 'np', type: 'password', autocomplete: 'new-password'}),
            $('button', {type: 'submit', textContent: 'Change password'}));
  pw.onsubmit = (e) => { e.preventDefault(); localStorage.removeItem('tok'); };
  api('/api/revenue').catch(() => {});                       // answers 400 with a reason
  api('/api/overview').catch(() => {});                      // answers 400 "No referred users"
  m.append($('h1', {textContent: 'Partner dashboard'}), $('p', {textContent: 'Welcome back, partner.'}), stats,
           $('button', {textContent: 'Copy referral link',
                        onclick: () => navigator.clipboard.writeText('https://example.test/r/qa')}),
           $('button', {textContent: 'Payment History', onclick: () => go('/payments')}),
           $('button', {textContent: 'Withdraw earnings'}), pw);
  return m;
}
function reports() {
  const m = $('main');
  m.append($('h1', {textContent: 'Reports'}), $('div', {className: 'wide', textContent: 'A 900px wide table of clicks per day.'}));
  return m;
}
function statistics() {
  const m = $('main'), chart = $('canvas', {width: 300, height: 80});
  const draw = (n) => { const g = chart.getContext('2d'); g.clearRect(0, 0, 300, 80);
    g.fillStyle = '#4c7dff'; for (let i = 0; i < 10; i++) g.fillRect(i * 30, 80 - (i * n * 7) % 80, 20, 80); };
  const tabs = ['Clicks', 'Sign ups', 'Deposits'].map((t, i) => $('button', {type: 'button', className: i ? 'tab' : 'tab sel', textContent: t}));
  tabs.forEach((b, i) => b.addEventListener('click', () => {
    tabs.forEach(x => x.className = 'tab'); b.className = 'tab sel'; draw(i + 2); }));
  draw(1);
  m.append($('h1', {textContent: 'Statistics'}), ...tabs, chart);
  return m;
}
function payments() {
  const m = $('main');
  m.append($('h1', {textContent: 'Payment history'}), $('p', {textContent: 'No payouts yet.'}));
  return m;
}
function settings() {
  const m = $('main');
  m.append($('h1', {textContent: 'Settings'}), $('p', {textContent: 'Payout wallet and notification settings.'}));
  return m;
}
async function render() {
  const root = document.getElementById('root'), p = location.pathname;
  const pages = {'/': home, '/login': login, '/registration': registration, '/password-recovery': recovery,
                 '/dashboard': dashboard, '/reports': reports, '/settings': settings,
                 '/statistics': statistics, '/payments': payments};
  const inside = ['/dashboard', '/reports', '/settings', '/statistics', '/payments'];
  if (inside.includes(p) && !token()) { history.replaceState(null, '', '/login'); return render(); }
  root.replaceChildren(header(), (pages[p] || (() => $('main')))(), footer());
}
api('/api/token/refresh/', {method: 'POST', body: '{}'}).catch(() => {});
api('/api/profile/?ignore403').catch(() => {});
render();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, body, status=200, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _authed(self):
        auth = self.headers.get("Authorization") or ""
        return auth.startswith("Bearer ") and auth[7:] in TOKENS

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/profile/":
            return self._send('{"email":"%s"}' % USER if self._authed() else '{"detail":"no"}',
                              200 if self._authed() else 401, "application/json")
        if path == "/api/overview":
            if not self._authed():
                return self._send('{"detail":"no"}', 401, "application/json")
            return self._send('{"message":"No referred users"}', 400, "application/json")
        if path == "/api/revenue":
            if not self._authed():
                return self._send('{"detail":"no"}', 401, "application/json")
            return self._send('{"detail":"date_from is required"}', 400, "application/json")
        if path == "/api/stats":
            if not self._authed():
                return self._send('{"detail":"no"}', 401, "application/json")
            return self._send('{"clicks":1204,"earnings":"$318"}', 200, "application/json")
        return self._send(SHELL)            # every other address: the app itself, with 200

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/token/refresh/":
            return self._send('{"detail":"no refresh token"}', 400, "application/json")
        if path == "/api/login":
            try:
                data = json.loads(raw or b"{}")
            except ValueError:
                data = {}
            if data.get("email") == USER and data.get("password") == PASSWORD:
                tok = secrets.token_hex(8)
                TOKENS.add(tok)
                return self._send(json.dumps({"token": tok}), 200, "application/json")
            return self._send('{"detail":"Invalid credentials"}', 401, "application/json")
        return self._send('{"detail":"not found"}', 404, "application/json")


if __name__ == "__main__":
    print(f"single-page test app on http://localhost:{PORT}  (user {USER})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
