"""Read-only tailnet HTTP surface for the iOS companion in `mobile/`.

    from obsauto.phone_agent import PhoneAgent
    agent = PhoneAgent(api, config); agent.start()

Wire contract: `docs/PHONE-AGENT.md`. This module owns no state and collects
nothing. `spike/app.py`'s `Api.snapshot()` already computes every section the
phone needs and is fault-isolated per section, so `project()` is a pure
translation of that payload into the phone's shape - adding a phone stat means
projecting an existing field, never writing new collection logic.

Five rules the tests pin, all of them load-bearing:

  * binds to the Tailscale IPv4 only, so the socket does not exist on the
    home LAN even with a valid token;
  * every request needs `Authorization: Bearer <token>`, compared in constant
    time;
  * missing data serialises as null - never a plausible substitute;
  * no footage path ever leaves this process;
  * read-only. A stale phone view issuing Stop would end a live recording,
    which is what the sacred-footage rule exists to prevent.

Imported lazily by the app so `requests`-free stdlib stays off the startup
import chain (`tests/test_import_budget.py`).
"""
import hmac
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from obsauto.app_log import log_to_file

PAYLOAD_VERSION = 1
DEFAULT_PORT = 8765

#: Substrings that mark a value as a footage path. Rule 4 in the contract:
#: catalogue metadata may travel, locations never do.
_FOOTAGE_MARKERS = ("z:\\obs", "z:/obs", "d:\\obs", "d:/obs", "obs-recovered")


def looks_like_footage_path(value):
    """True if ``value`` smells like a recording location rather than a label."""
    if not isinstance(value, str):
        return False
    low = value.lower()
    return any(marker in low for marker in _FOOTAGE_MARKERS)


def _scrub(value):
    """Drop anything that looks like a footage path. Labels survive, paths do not."""
    return None if looks_like_footage_path(value) else value


def _text(value):
    """Non-empty string, or None. The desktop's empty-string idiom means 'unknown'."""
    if value is None:
        return None
    text = str(value).strip()
    return _scrub(text) if text else None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _hero_status(hero):
    """Map the desktop hero state enum onto the phone's recording status."""
    state = (hero.get("state") or "").lower()
    if state in ("recording", "live"):
        return "recording"
    if state == "paused":
        return "paused"
    if state in ("saved", "stopped"):
        return "stopped"
    return "idle"


def project(snapshot, now):
    """Translate an `Api.snapshot()` payload into the phone contract.

    Tolerates missing sections throughout: `Api.snapshot()` substitutes a
    fallback when a section faults, and a fallback must read as "unknown" on
    the phone rather than as a real zero.
    """
    snapshot = snapshot or {}
    hero = snapshot.get("hero") or {}
    forecast = snapshot.get("forecast") or {}
    remote = snapshot.get("remote") or {}

    return {
        "v": PAYLOAD_VERSION,
        "at": now,
        "connection": "online",
        "recording": _recording(hero, forecast),
        "activity": _activity(snapshot.get("activity")),
        "clips": _clips(snapshot.get("clips_panel")),
        "moonlight": _moonlight_state(remote),
        "moonlightPaired": remote.get("paired") if isinstance(remote.get("paired"), bool) else None,
        "peers": _peers(remote),
        "offload": _offload(remote, snapshot),
        "detectedGames": _games(snapshot.get("games")),
        "notGamesCount": _non_games_count(snapshot.get("games")),
        "classifyQueue": _classify_queue(snapshot.get("games")),
    }


def disk_warning(label):
    """True when the disk forecast falls inside the app's own projection window.

    `_forecast` in spike/app.py returns only ``{label, rate, used_pct}`` - there
    is no boolean to read - so the warning is derived from the label vocabulary
    `forecast.days_left_label()` produces: "N hours", "N days", "60+ days", or
    an empty/explanatory string. Anything measured in hours is a warning; days
    are a warning inside `forecast.PROJECTION_DAYS`, which is the horizon the
    desktop already projects against rather than a threshold invented here.

    Unknown ("", "drive unavailable", "needs history") is never a warning -
    not knowing is not the same as knowing it is bad.
    """
    if not label:
        return False
    low = str(label).lower()
    if "hour" in low:
        return True
    match = re.search(r"(\d+)\s*day", low)
    if not match or "+" in low:
        return False
    from obsauto.forecast import PROJECTION_DAYS
    return int(match.group(1)) <= PROJECTION_DAYS


def _recording(hero, forecast):
    status = _hero_status(hero)
    live = status in ("recording", "paused")
    # Readouts are only meaningful while a session exists; the desktop leaves
    # them as empty strings otherwise, which must not become "0".
    return {
        "status": status,
        "encoder": _text(hero.get("video")) if live else None,
        "gameTitle": _text(hero.get("title")) if live else None,
        "sceneName": _text(hero.get("scene")) if live else None,
        "elapsedSec": _elapsed_seconds(hero.get("elapsed")) if live else None,
        "fileSizeLabel": _text(hero.get("size")) if live else None,
        "bitrateLabel": _text(hero.get("bitrate")) if live else None,
        "diskLeftLabel": _text(forecast.get("label")),
        "diskWarning": disk_warning(forecast.get("label")),
    }


def _elapsed_seconds(label):
    """"01:12:33" -> 4353. Returns None for anything that is not a clock."""
    if not label:
        return None
    parts = str(label).strip().split(":")
    if not (2 <= len(parts) <= 3):
        return None
    total = 0
    for part in parts:
        value = _int(part)
        if value is None or value < 0:
            return None
        total = total * 60 + value
    return total


def _activity(activity):
    rows = (activity or {}).get("rows") or []
    out = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        label = _text(row.get("label") or row.get("text"))
        if not label:
            continue
        out.append({
            "id": str(row.get("id") or "act-%d" % i),
            "at": _number(row.get("ts") or row.get("at")),
            "label": label,
            "kind": _activity_kind(row.get("kind") or row.get("tag")),
        })
    return out


def _activity_kind(raw):
    kind = (str(raw or "")).lower()
    if "rec" in kind:
        return "recording"
    if "offline" in kind or "error" in kind:
        return "offline"
    return "info"


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_CLIP_STATES = {"recording", "local", "offloading", "on-nas"}


def _clips(panel):
    """Clip rows from `_clips_panel`.

    That payload carries `title` (name without extension), `size_label`, and
    `location` - "remote" meaning the copy lives on the NAS. It has no
    phone-style `state` field, so on-NAS/local is derived from `location`;
    "offloading" needs the live offloader queue and is not in this payload.
    `path` is a footage location and is deliberately never read.
    """
    entries = (panel or {}).get("clips") or []
    out = []
    for i, clip in enumerate(entries):
        if not isinstance(clip, dict):
            continue
        title = _text(clip.get("title") or clip.get("name"))
        if not title:
            continue
        out.append({
            "id": str(clip.get("rel") or clip.get("id") or "clip-%d" % i),
            "title": title,
            "durationLabel": _text(clip.get("duration") or clip.get("duration_label")),
            "sizeLabel": _text(clip.get("size_label")),
            "state": _clip_state(clip),
            "startedAt": _number(clip.get("mtime") or clip.get("when")),
            "game": _text(clip.get("game")),
        })
    return out


def _clip_state(clip):
    explicit = str(clip.get("state") or "").lower()
    if explicit in _CLIP_STATES:
        return explicit
    return "on-nas" if clip.get("location") == "remote" else "local"


def _moonlight_state(remote):
    """Desktop reports idle/live/unknown; the phone's 'busy' is a handshake it owns."""
    state = ((remote.get("moonlight") or {}).get("state") or "").lower()
    return "live" if state == "live" else "ready"


def _peers(remote):
    """Peer rows from `_remote`'s tailscale section.

    That payload carries no RTT - `tailscale.ping_rtt_ms()` shells out per peer,
    which is too slow for a snapshot - so `pingMs` is null until a cheaper
    source exists. Null renders as an em-dash, which is the honest answer.
    """
    peers = (remote.get("tailscale") or {}).get("peers") or remote.get("peers") or []
    out = []
    for i, peer in enumerate(peers):
        if not isinstance(peer, dict):
            continue
        name = _text(peer.get("name") or peer.get("host"))
        if not name:
            continue
        out.append({
            "id": str(peer.get("id") or name or "peer-%d" % i),
            "name": name,
            "online": bool(peer.get("online")),
            "pingMs": _int(peer.get("ping_ms") or peer.get("rtt_ms")),
            # `status` is the desktop's human label ("direct", "relayed").
            "route": _text(peer.get("status")),
        })
    return out


def _offload(remote, snapshot=None):
    job = remote.get("offload") or (snapshot or {}).get("offload")
    if not isinstance(job, dict):
        return None
    total = _int(job.get("total"))
    if not total:
        return None
    return {
        "done": _int(job.get("done")) or 0,
        "total": total,
        "sizeLabel": _text(job.get("size_label")),
        "currentFile": _text(job.get("current")),
        "throughputLabel": _text(job.get("throughput")),
    }


def _games(games):
    """Titles the classifier has ruled games.

    `_games` emits `{name, exes[], meta, icon}` - there is no per-title record
    switch on the desktop, because membership in this list *is* the recording
    decision (which is what the frame's "Recording · N" counter counts). So
    `recording` is True for every row here, and the phone's switch is a
    read-only reflection of that until the agent grows a write path.
    """
    rows = (games or {}).get("games") or []
    out = []
    for i, game in enumerate(rows):
        if not isinstance(game, dict):
            continue
        name = _text(game.get("name") or game.get("title"))
        if not name:
            continue
        exes = game.get("exes")
        exe = _text(exes[0]) if isinstance(exes, list) and exes else _text(game.get("exe"))
        out.append({
            "id": str(game.get("key") or exe or name or "game-%d" % i),
            "name": name,
            "exe": exe or "",
            "recording": True,
        })
    return out


def _non_games_count(games):
    rows = (games or {}).get("non_games")
    return len(rows) if isinstance(rows, list) else None


def _classify_queue(games):
    """Pending detections awaiting a verdict. Empty until the classifier reports."""
    pending = (games or {}).get("pending") or []
    out = []
    for i, item in enumerate(pending):
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name") or item.get("title"))
        if not name:
            continue
        out.append({
            "id": str(item.get("id") or item.get("exe") or "pending-%d" % i),
            "name": name,
            "exe": _text(item.get("exe")) or "",
            "publisher": _text(item.get("publisher")) or "",
            "confidence": "high" if item.get("confidence") == "high" else "low",
            "signals": _signals(item.get("signals")),
            "verdictLabel": _text(item.get("verdict")) or "",
            "warn": item.get("confidence") != "high",
        })
    return out


def _signals(raw):
    out = []
    for signal in (raw or []):
        if isinstance(signal, (list, tuple)) and len(signal) == 2:
            text, lean = signal
        elif isinstance(signal, dict):
            text, lean = signal.get("text"), signal.get("lean")
        else:
            continue
        text = _text(text)
        if text:
            out.append({"lean": "game" if lean == "game" else "not", "text": text})
    return out


class PhoneAgent:
    """Serves `project(api.snapshot())` on the tailnet. Read-only, opt-in."""

    def __init__(self, api, config=None, clock=None):
        self._api = api
        self._config = config or {}
        self._clock = clock or __import__("time").time
        self._server = None
        self._thread = None

    @property
    def enabled(self):
        return bool(self._config.get("phone_agent_enabled"))

    @property
    def token(self):
        return str(self._config.get("phone_agent_token") or "")

    @property
    def port(self):
        return _int(self._config.get("phone_agent_port")) or DEFAULT_PORT

    def bind_host(self):
        """The Tailscale IPv4, or None when the tailnet is unavailable.

        Returning None is a refusal to start, not a fallback to `0.0.0.0` -
        binding wider would expose the surface to the home LAN.
        """
        from obsauto import tailscale as ts
        try:
            status = ts.status()
        except Exception:
            return None
        ips = ((status or {}).get("self") or {}).get("ips") or []
        return ips[0] if ips else None

    def snapshot(self):
        """The phone payload. Never raises - a fault degrades to an empty shape."""
        try:
            raw = self._api.snapshot()
        except Exception as exc:
            log_to_file("[PHONE] snapshot failed: %s" % exc)
            raw = {}
        return project(raw, self._clock())

    def authorised(self, header):
        """Constant-time bearer check. An unset token refuses everything."""
        token = self.token
        if not token:
            return False
        prefix = "Bearer "
        if not header or not header.startswith(prefix):
            return False
        return hmac.compare_digest(header[len(prefix):].strip(), token)

    def start(self):
        """Start the listener. Returns the bound (host, port), or None."""
        if not self.enabled:
            return None
        if not self.token:
            log_to_file("[PHONE] refusing to start: phone_agent_token is unset")
            return None
        host = self.bind_host()
        if not host:
            log_to_file("[PHONE] refusing to start: no Tailscale address")
            return None
        try:
            self._server = ThreadingHTTPServer((host, self.port), _make_handler(self))
        except OSError as exc:
            log_to_file("[PHONE] bind %s:%s failed: %s" % (host, self.port, exc))
            return None
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="phone-agent", daemon=True,
        )
        self._thread.start()
        log_to_file("[PHONE] serving on %s:%s" % (host, self.port))
        return host, self.port

    def stop(self):
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
        self._server = None
        self._thread = None


def _make_handler(agent):
    class Handler(BaseHTTPRequestHandler):
        server_version = "NebulaPhoneAgent/1"
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            """Silence per-request stderr spam; real events go to the app log."""

        def _send(self, code, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
            try:
                if not agent.authorised(self.headers.get("Authorization")):
                    self._send(401, {"error": "unauthorised"})
                    return
                path = (self.path or "").split("?")[0].rstrip("/")
                if path == "/v1/health":
                    self._send(200, {"ok": True, "v": PAYLOAD_VERSION})
                elif path == "/v1/snapshot":
                    self._send(200, agent.snapshot())
                else:
                    self._send(404, {"error": "not found"})
            except Exception as exc:
                # Rule 5: the agent degrades to a 500, it never takes the app down.
                log_to_file("[PHONE] request failed: %s" % exc)
                try:
                    self._send(500, {"error": "internal"})
                except Exception:
                    pass

    return Handler
