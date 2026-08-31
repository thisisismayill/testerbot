"""A deliberately buggy website used to verify TesterBot finds real defects."""
import re, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8099
BASE = f"http://localhost:{PORT}"

HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>%s
<style>body{font-family:system-ui;margin:0;padding:24px;max-width:900px}
nav a{margin-right:12px}.wide{width:1500px;background:#eee;height:40px}</style>
</head><body>
<nav><a href="/">Home</a><a href="/about">About</a><a href="/team">Team</a>
<a href="/contact">Contact</a><a href="/pricing">Pricing</a><a href="/broken">Broken</a>
<a href="/slow">Slow</a><a href="/login">Login</a>
<a href="/does-not-exist">Dead link</a></nav><hr>"""
FOOT = "</body></html>"


def page(title, body, extra_head=""):
    return (HEAD % (title, extra_head)) + body + FOOT


HOME = page("Buggy Demo Shop", """
<h1>Buggy Demo Shop</h1>
<p>Everything on this page is broken on purpose.</p>
<img src="/img/missing-photo.png" width="120" height="80">
<img src="/img/logo.png" alt="Logo" width="60" height="60">
<button id="boom">Show offers</button>
<button id="dead">Click me</button>
<button aria-hidden="false"><span class="icon">&#9776;</span></button>
<a href="https://example.com/definitely-missing-page-xyz" target="_blank">External broken link</a>
<a href="/team"></a>
<div class="wide">This block is 1500px wide and overflows on mobile.</div>
<p>Status: undefined</p>
<script>
document.getElementById('boom').addEventListener('click', function(){
  window.missingFunction();
});
document.getElementById('dead').addEventListener('click', function(){ /* nothing */ });
fetch('/api/offers').then(r=>r.json()).catch(e=>console.error('offers api failed', e));
</script>""", '<meta name="description" content="A deliberately broken demo shop.">')

ABOUT = page("Company", "<h1>About</h1><p>We build broken things.</p>")
TEAM = page("Company", """<h2>Team</h2><h4>Engineering</h4>
<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
<img src="/img/team.png" width="200" height="100">""")

PRICING = page("Pricing", """<h1>Pricing</h1>
<form id="nl" action="/subscribe-newsletter" method="post">
  <label for="e">E-mail</label><input id="e" type="email" name="email" required>
  <button type="submit">Join</button>
</form>
<form id="noop"><input type="text" name="promo" placeholder="Promo code">
<button type="submit">Apply</button></form>
<button>Delete my account</button>
<script>document.getElementById('noop').addEventListener('submit',e=>e.preventDefault());</script>""")

CONTACT = page("Contact us", """<h1>Contact</h1>
<form action="/contact" method="post">
  <input type="text" name="name" placeholder="Your name" required>
  <input type="email" name="email" placeholder="E-mail" required>
  <textarea name="message" placeholder="Message" required></textarea>
  <button type="submit">Send message</button>
</form>""")

HIDDEN = page("Secret Offer", "<h1>Hidden offer</h1><p>Only listed in sitemap.xml.</p>")

LOGIN = page("Login", """<h1>Login</h1>
<form action="/login" method="post">
  <label for="u">User</label><input id="u" type="text" name="user">
  <label for="p">Password</label><input id="p" type="password" name="pass">
  <button type="submit">Sign in</button>
</form>""")

DASHBOARD = page("Dashboard", """<h1>Dashboard</h1>
<p>Welcome back, tester.</p>
<input type="text" name="search_orders">
<button id="tab1">Orders</button>
<button id="crash">Load report</button>
<button>Delete all orders</button>
<a href="/logout">Log out</a>
<div id="panel"></div>
<script>
document.getElementById('tab1').addEventListener('click',()=>{
  document.getElementById('panel').textContent='Order list loaded at ' + Date.now();});
document.getElementById('crash').addEventListener('click',()=>{
  fetch('/api/report').then(r=>{ if(!r.ok) throw new Error('report endpoint failed: '+r.status);});
  null.x = 1;});
</script>""")

ROBOTS = f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n"
SITEMAP = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{BASE}/</loc></url><url><loc>{BASE}/about</loc></url>
<url><loc>{BASE}/hidden-offer</loc></url><url><loc>{BASE}/pricing</loc></url>
</urlset>"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _send(self, body, status=200, ctype="text/html; charset=utf-8", headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def logged_in(self):
        return "session=yes" in (self.headers.get("Cookie") or "")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        routes = {
            "/": HOME, "/about": ABOUT, "/team": TEAM, "/pricing": PRICING,
            "/contact": CONTACT, "/login": LOGIN, "/hidden-offer": HIDDEN,
        }
        if path in routes:
            return self._send(routes[path])
        if path == "/robots.txt":
            return self._send(ROBOTS, ctype="text/plain; charset=utf-8")
        if path == "/sitemap.xml":
            return self._send(SITEMAP, ctype="application/xml")
        if path == "/.env":
            return self._send("DB_PASSWORD=hunter2\nAPI_KEY=sk-test-123\n",
                              ctype="text/plain; charset=utf-8")
        if path == "/broken":
            return self._send("<h1>500</h1>", status=500)
        if path == "/slow":
            time.sleep(2.0)
            return self._send(page("Slow page", "<h1>Slow</h1><p>Took two seconds.</p>"))
        if path == "/dashboard":
            if not self.logged_in():
                return self._send("", status=302, headers={"Location": "/login"})
            return self._send(DASHBOARD)
        if path == "/logout":
            return self._send("", status=302,
                              headers={"Location": "/", "Set-Cookie": "session=; Max-Age=0; Path=/"})
        if path.startswith("/img/"):
            if path.endswith("logo.png"):
                png = bytes.fromhex(
                    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
                    "01f15c4890000000a49444154789c6360000002000100ffff03000006"
                    "0005570cf5f10000000049454e44ae426082")
                return self._send(png, ctype="image/png")
            return self._send("not found", status=404, ctype="text/plain")
        if path == "/api/offers":
            return self._send('{"error":"boom"}', status=500, ctype="application/json")
        if path == "/api/report":
            return self._send('{"error":"nope"}', status=404, ctype="application/json")
        # deliberate bug: unknown URLs answer 200
        return self._send(page("Not found", "<h1>Page not found</h1>"), status=200)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        data = dict(urllib.parse.parse_qsl(raw, keep_blank_values=True))
        path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            if data.get("user") == "tester" and data.get("pass") == "secret123":
                return self._send("", status=302, headers={
                    "Location": "/dashboard", "Set-Cookie": "session=yes; Path=/"})
            return self._send(page("Login", "<h1>Login</h1><p>Wrong credentials.</p>"
                                            + LOGIN.split("<h1>Login</h1>")[1]), status=200)
        if path == "/contact":
            # bug 1: accepts empty submissions; bug 2: echoes input unescaped
            return self._send(page("Thanks", "<h1>Thank you</h1><p>We received: "
                                             + data.get("message", "") + "</p>"))
        if path == "/subscribe-newsletter":
            return self._send(page("Subscribed", "<h1>Subscribed</h1><p>Welcome!</p>"))
        return self._send(page("Posted", "<h1>OK</h1>"))


if __name__ == "__main__":
    print(f"buggy test site on {BASE}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
