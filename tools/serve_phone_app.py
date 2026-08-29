"""Serve the exported phone app on the tailnet so iOS can install it.

    python tools/serve_phone_app.py            # binds the Tailscale IP, port 8766
    python tools/serve_phone_app.py --port 9000

A free Apple developer account cannot sign an installable iOS build - that
needs the paid Developer Program - so the shipping route is Safari's "Add to
Home Screen". The app then launches fullscreen with Nebula's own icon and no
browser chrome (see the PWA tags in `mobile/app/+html.tsx`).

Binds to the Tailscale address only, matching `obsauto/phone_agent.py`: the
bundle has the agent token inlined by `EXPO_PUBLIC_*`, so it must not be
reachable from the home LAN. Serving is read-only and confined to `mobile/dist`.

Rebuild the bundle after any app change:

    cd mobile && npx expo export --platform web
"""
import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DIST = os.path.join(ROOT, "mobile", "dist")
DEFAULT_PORT = 8766


class Handler(SimpleHTTPRequestHandler):
    """Static files, an SPA fallback, and a same-origin proxy to the agent.

    Proxying `/v1/*` rather than letting the page call port 8765 directly buys
    two things. The fetch becomes same-origin, so no CORS is involved at all;
    and the bearer token stays here on the server instead of being inlined into
    the JavaScript bundle by `EXPO_PUBLIC_*`, so the shipped app carries no
    secret. Both surfaces are already Tailscale-bound, so the reachable
    audience is identical either way.
    """

    extensions_map = dict(SimpleHTTPRequestHandler.extensions_map)
    extensions_map[".webmanifest"] = "application/manifest+json"

    agent_url = ""
    agent_token = ""

    def log_message(self, *_args):
        """Quiet; this runs alongside the app, not in a terminal being watched."""

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
        if self.path.startswith("/v1/"):
            return self._proxy()
        return SimpleHTTPRequestHandler.do_GET(self)

    def _proxy(self):
        """Forward one GET to the agent, adding the token. Read-only by design:
        only GET reaches here, and the agent refuses everything else anyway."""
        req = urllib.request.Request(self.agent_url + self.path)
        if self.agent_token:
            req.add_header("Authorization", "Bearer " + self.agent_token)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body, code = resp.read(), resp.status
        except urllib.error.HTTPError as exc:
            body, code = exc.read() or b"{}", exc.code
        except Exception as exc:
            body = json.dumps({"error": "agent unreachable: %s" % exc}).encode()
            code = 503
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_head(self):
        # Expo exports one HTML file per route, but a deep link that misses
        # still has to land somewhere rather than 404 into a blank screen.
        path = self.translate_path(self.path)
        if not os.path.exists(path) and "." not in os.path.basename(path):
            self.path = "/index.html"
        return SimpleHTTPRequestHandler.send_head(self)


def tailscale_ip():
    from obsauto import tailscale as ts
    try:
        status = ts.status()
    except Exception:
        return None
    ips = ((status or {}).get("self") or {}).get("ips") or []
    return ips[0] if ips else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="", help="override the bind address")
    args = ap.parse_args()

    if not os.path.isdir(DIST):
        sys.exit("No build at %s\nRun: cd mobile && npx expo export --platform web" % DIST)

    host = args.host or tailscale_ip()
    if not host:
        sys.exit("No Tailscale address. Refusing to bind wider - the bundle "
                 "carries the agent token and must stay off the home LAN.")

    cfg = {}
    try:
        cfg = json.load(io.open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    except Exception:
        pass
    Handler.agent_token = str(cfg.get("phone_agent_token") or "")
    Handler.agent_url = "http://%s:%s" % (host, cfg.get("phone_agent_port") or 8765)
    if not Handler.agent_token:
        print("warning: no phone_agent_token in config.json - /v1 will 401")

    httpd = ThreadingHTTPServer((host, args.port),
                                partial(Handler, directory=DIST))
    print("Nebula phone app: http://%s:%d" % (host, args.port))
    print("  proxying /v1/* -> %s" % Handler.agent_url)
    print("On the iPhone: open that in Safari, then Share -> Add to Home Screen.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
