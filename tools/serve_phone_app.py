"""Serve the exported phone app on the tailnet so iOS can install it.

    python tools/serve_phone_app.py            # binds the Tailscale IP, port 8766
    python tools/serve_phone_app.py --port 9000

A free Apple developer account cannot sign an installable iOS build - that
needs the paid Developer Program - so the shipping route is Safari's "Add to
Home Screen". The app then launches fullscreen with Nebula's own icon and no
browser chrome (see the PWA tags in `mobile/app/+html.tsx`).

Binds to the Tailscale address only, matching `obsauto/phone_agent.py`. This
surface proxies to the agent with the token attached, so anyone who can reach
it can read studio state - it must not exist on the home LAN. Serving is
read-only and confined to `mobile/dist`.

Installed as a boot-time scheduled task by `tools/install_phone_app_task.ps1`.

Rebuild the bundle after any app change:

    cd mobile && npx expo export --platform web
"""
import argparse
import io
import json
import os
import sys
import time
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
    #: Set when the agent is unreachable, or by --standalone. Shared so the
    #: clip-scan cache survives across requests.
    disk = None
    standalone = False

    def log_message(self, *_args):
        """Quiet; this runs alongside the app, not in a terminal being watched."""

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
        if self.path.startswith("/v1/"):
            return self._proxy()
        return SimpleHTTPRequestHandler.do_GET(self)

    def _proxy(self):
        """Answer one /v1 GET: from the agent if it is up, else from disk.

        The agent inside desktop Nebula is richer - it has OBS, so it knows the
        scene and bitrate - but it only exists in a logged-in session. When it
        is unreachable the same payload is built from files instead, which is
        what makes the phone work after a reboot with nobody logged in.

        An HTTP error from the agent is passed through rather than papered
        over: a 401 means the token is wrong, and silently serving disk data
        would hide that.
        """
        if self.standalone:
            return self._send_json(*self._from_disk())

        req = urllib.request.Request(self.agent_url + self.path)
        if self.agent_token:
            req.add_header("Authorization", "Bearer " + self.agent_token)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body, code = resp.read(), resp.status
        except urllib.error.HTTPError as exc:
            body, code = exc.read() or b"{}", exc.code
        except Exception:
            body, code = self._from_disk()
        return self._send_json(body, code)

    def _from_disk(self):
        """Build the payload locally. Never raises into the response."""
        import time as _time
        try:
            from obsauto.phone_agent import PAYLOAD_VERSION, project
            if self.path.rstrip("/") == "/v1/health":
                return json.dumps({"ok": True, "v": PAYLOAD_VERSION,
                                   "source": "disk"}).encode(), 200
            payload = project(Handler.disk.snapshot(), _time.time())
            payload["source"] = "disk"
            return json.dumps(payload).encode(), 200
        except Exception as exc:
            return json.dumps({"error": "no studio state: %s" % exc}).encode(), 503

    def _send_json(self, body, code):
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
        status = ts.status(force=True)
    except Exception:
        return None
    ips = ((status or {}).get("self") or {}).get("ips") or []
    return ips[0] if ips else None


def wait_for_tailscale(deadline_s, log=print):
    """Poll until the tailnet address exists, or give up after `deadline_s`.

    Run from a boot-time scheduled task this matters: the task fires before
    tailscaled has an address, and exiting immediately would leave the phone
    app dead until someone noticed. Retrying costs nothing and turns a race
    into a wait.
    """
    started = time.monotonic()
    announced = False
    while True:
        ip = tailscale_ip()
        if ip:
            return ip
        if time.monotonic() - started >= deadline_s:
            return None
        if not announced:
            log("waiting for a Tailscale address...")
            announced = True
        time.sleep(5)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="", help="override the bind address")
    ap.add_argument("--standalone", action="store_true",
                    help="always build /v1 from disk, never ask the agent")
    ap.add_argument("--wait", type=int, default=0,
                    help="seconds to wait for a Tailscale address before giving "
                         "up (boot-time tasks should pass a few minutes)")
    args = ap.parse_args()

    if not os.path.isdir(DIST):
        sys.exit("No build at %s\nRun: cd mobile && npx expo export --platform web" % DIST)

    host = args.host or (wait_for_tailscale(args.wait) if args.wait
                         else tailscale_ip())
    if not host:
        sys.exit("No Tailscale address. Refusing to bind wider - this surface "
                 "reaches the agent and must stay off the home LAN.")

    cfg = {}
    try:
        cfg = json.load(io.open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    except Exception:
        pass
    Handler.agent_token = str(cfg.get("phone_agent_token") or "")
    Handler.agent_url = "http://%s:%s" % (host, cfg.get("phone_agent_port") or 8765)
    Handler.standalone = args.standalone
    from obsauto.phone_state import DiskSnapshot
    Handler.disk = DiskSnapshot(root=ROOT)
    if not Handler.agent_token and not args.standalone:
        print("warning: no phone_agent_token in config.json - /v1 will 401")

    httpd = ThreadingHTTPServer((host, args.port),
                                partial(Handler, directory=DIST))
    print("Nebula phone app: http://%s:%d" % (host, args.port))
    if args.standalone:
        print("  /v1/* built from disk (standalone)")
    else:
        print("  /v1/* -> %s, falling back to disk when it is down"
              % Handler.agent_url)
    print("On the iPhone: open that in Safari, then Share -> Add to Home Screen.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
