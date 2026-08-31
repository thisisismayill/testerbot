"""In-process interlinked test 'web': 4 distinct domains via *.localhost,
served from one port routed by Host header. Used to prove cross-domain
Domain Authority works."""
import threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8090
B = lambda h: f"http://{h}.localhost:{PORT}"

# link structure (the "web"):
#   hub  : the authority. internal pages only + one link out to bloga.
#   bloga: links to hub (x2), blogb, and has internal pages
#   blogb: links to hub (x2), bloga
#   blogc: links to hub (x1) only
# expected authority order: hub >> bloga/blogb > blogc
SITES = {
    "hub": {
        "/":       [("/about","About us"),("/pricing","Pricing"),(B('bloga')+"/","our partner blog")],
        "/about":  [("/","Home"),("/pricing","Pricing")],
        "/pricing":[("/","Home"),("/about","About")],
    },
    "bloga": {
        "/":       [("/post-1","First post"),("/post-2","Second post"),
                    (B('hub')+"/","the hub tool"),(B('hub')+"/pricing","hub pricing"),
                    (B('blogb')+"/","blog b")],
        "/post-1": [("/","Home"),(B('hub')+"/","great hub")],
        "/post-2": [("/","Home")],
    },
    "blogb": {
        "/":       [("/article","Article"),(B('hub')+"/","hub homepage"),
                    (B('hub')+"/about","about the hub"),(B('bloga')+"/","blog a")],
        "/article":[("/","Home"),(B('hub')+"/","hub")],
    },
    "blogc": {
        "/":       [("/news","News"),(B('hub')+"/","check the hub")],
        "/news":   [("/","Home")],
    },
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def do_GET(self):
        host = self.headers.get("Host", "").split(".")[0]
        path = self.path
        if path == "/robots.txt":
            # hub disallows /pricing for all bots
            body = (b"User-agent: *\nDisallow: /pricing\n" if host == "hub"
                    else b"User-agent: *\nAllow: /\n")
            self.send_response(200)
            self.send_header("Content-Type","text/plain")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers(); self.wfile.write(body); return
        site = SITES.get(host)
        if not site or path not in site:
            body = b"<h1>404</h1>"
            self.send_response(404)
        else:
            links = "".join(f'<a href="{href}">{txt}</a> ' for href, txt in site[path])
            body = (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
                    f"<title>{host} {path}</title></head><body>"
                    f"<h1>{host}{path}</h1><nav>{links}</nav></body></html>").encode()
            self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
