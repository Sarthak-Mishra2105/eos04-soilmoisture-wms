"""Read-only gateway that exposes only the public parts of the local GeoServer.

A tunnel (e.g. `cloudflared tunnel --url http://127.0.0.1:8099`) points at this proxy,
never at GeoServer directly, so the admin UI (/web) and REST API (/rest) stay private.

Allowed:  the bhoonidhi WMS, the Natural Earth basemap WMS used by the demo,
          the demo page, and GeoServer's bundled XML schemas. GET/HEAD only.
Blocked:  everything else, plus WMS parameters that make GeoServer fetch remote URLs.

The proxy passes X-Forwarded-Host/Proto so GeoServer writes the public URL into
GetCapabilities (the bhoonidhi workspace has "use headers for proxy URL" enabled).

    python scripts/public_proxy.py [--port 8099] [--geoserver http://127.0.0.1:8080]
"""

import argparse
import http.client
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

ALLOWED_PATHS = [
    re.compile(r"^/geoserver/(bhoonidhi|ne)/(wms|ows)$"),
    re.compile(r"^/geoserver/www/eos04-demo/[A-Za-z0-9_\-/]+(\.[A-Za-z0-9]+)?$"),
    re.compile(r"^/geoserver/schemas/[A-Za-z0-9_\-/.]+\.xsd$"),
]
# Parameters that make GeoServer load styles or data from an arbitrary URL.
BLOCKED_PARAMS = {"sld", "remote_ows_url", "remote_ows_type", "sld_body"}
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
              "trailers", "transfer-encoding", "upgrade", "host", "content-length"}
DEMO = "/geoserver/www/eos04-demo/index.html"


class Gateway(BaseHTTPRequestHandler):
    upstream = ("127.0.0.1", 8080)
    protocol_version = "HTTP/1.1"

    def do_HEAD(self):
        self.handle_request(head=True)

    def do_GET(self):
        self.handle_request(head=False)

    def deny(self, code, msg):
        body = msg.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_request(self, head):
        parts = urlsplit(self.path)
        if parts.path in ("", "/", "/geoserver", "/geoserver/"):
            self.send_response(302)
            self.send_header("Location", DEMO)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if ".." in parts.path or not any(p.match(parts.path) for p in ALLOWED_PATHS):
            return self.deny(404, "Not found. Public paths: /geoserver/bhoonidhi/wms and " + DEMO)
        if any(k.lower() in BLOCKED_PARAMS for k, _ in parse_qsl(parts.query, keep_blank_values=True)):
            return self.deny(403, "Remote style and data parameters are disabled on this endpoint.")

        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        public_host = self.headers.get("Host", "")
        headers["X-Forwarded-Host"] = public_host
        headers["X-Forwarded-Proto"] = self.headers.get("X-Forwarded-Proto", "https")
        conn = http.client.HTTPConnection(*self.upstream, timeout=120)
        try:
            conn.request("HEAD" if head else "GET", self.path, headers=headers)
            resp = conn.getresponse()
            body = resp.read()
        except OSError as e:
            return self.deny(502, f"GeoServer unavailable: {e}")
        finally:
            conn.close()
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() not in HOP_BY_HOP:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {self.command} {self.path[:160]} -> {args[1] if len(args) > 1 else ''}",
              flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--geoserver", default="http://127.0.0.1:8080")
    a = ap.parse_args()
    u = urlsplit(a.geoserver)
    Gateway.upstream = (u.hostname, u.port or 80)
    print(f"Public gateway on http://127.0.0.1:{a.port} -> {a.geoserver} (read-only allowlist)")
    ThreadingHTTPServer(("127.0.0.1", a.port), Gateway).serve_forever()


if __name__ == "__main__":
    main()
