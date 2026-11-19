"""Mock-first phone contract from the 18 Nov 2026 mobile build spec (§4, §15.1).

The phone will speak JSON over a WebSocket. This module is the PC side of
that conversation, with an in-memory studio so the protocol can be proven
before it is wired to OBS. Nothing here opens, moves, or deletes a recording.

The spec names port 47990. That port is Sunshine's HTTPS UI, which Moonlight
already uses on this machine, so the listener default sits beside it.
"""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import threading
from datetime import datetime, timedelta, timezone

# Sunshine owns 47990. Configurable; this is the default that does not collide.
DEFAULT_PORT = 8770
MOCK_TOKEN = "mock-device"
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

ALLOWED_SETTINGS = (
    "launchCapture",
    "replaySeconds",
    "idleTimeout",
    "discardUnder",
    "keepAliveApps",
    "offload.auto",
    "gameListSync.provider",
)
_CAPTURES = ("default", "record", "buffer", "both")
_LAUNCH = ("record", "buffer", "both")
_REPLAY = (15, 30, 60, 120)
_PROVIDERS = ("onedrive", "none")
_PAGE = 50


def _iso(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now():
    return datetime.now(timezone.utc)


def seed_mock(now=None):
    """A studio sat at idle: one pending app, twenty clips, a foreground game."""
    moment = now or _now()
    games = [
        _game("sifu", "Sifu", "steam", "both", 12, 8_400_000_000, moment),
        _game("hades", "Hades", "user", "default", 8, 3_200_000_000, moment),
    ]
    clips = []
    for index in range(20):
        created = moment - timedelta(hours=index + 1)
        game = games[index % 2]
        clips.append({
            "id": "clip-%02d" % (index + 1),
            "game": {"id": game["id"], "name": game["name"]},
            "file": "clip-%02d.mkv" % (index + 1),
            "folder": game["name"],
            "kind": "recording",
            "createdAt": _iso(created),
            "duration": 600.0 + index,
            "bytes": 1_000_000_000 + index * 10_000_000,
            "resolution": "1920x1080",
            "fps": 60,
            "encoder": "NVENC",
            "highlights": [],
            "locations": ["pc", "nas"] if index % 3 == 0 else ["pc"],
            "offload": "done" if index % 3 == 0 else "none",
            "thumbnailURL": "/files/thumb/clip-%02d.jpg" % (index + 1),
            "writing": False,
        })
    # One clip still being written, one still copying. Trim must refuse both.
    clips[1]["writing"] = True
    clips[1]["duration"] = None
    clips[1]["bytes"] = None
    clips[2]["offload"] = {"progress": 0.42, "bytesLeft": 1_200_000_000}
    pending = {
        "id": "pending-sandfall",
        "exe": "Sandfall-Win64-Shipping.exe",
        "window": {"fullscreen": True, "width": 2560, "height": 1440},
        "inSteam": False,
        "seenAt": _iso(moment - timedelta(seconds=12)),
    }
    return MobileAgent(
        token=MOCK_TOKEN,
        games=games,
        non_games=[{"exe": "blender.exe", "displayName": "Blender"}],
        pending=[pending],
        clips=clips,
        foreground={"id": "sifu", "name": "Sifu"},
        now=moment,
    )


def _game(gid, name, source, capture, count, size, moment):
    return {
        "id": gid,
        "name": name,
        "source": source,
        "capture": capture,
        "clipCount": count,
        "bytes": size,
        "coverURL": None,
        "lastPlayed": _iso(moment),
        "weekPlaytime": [0.0] * 7,
    }


class MobileAgent:
    """One studio the phone talks to. `handle` is the whole wire contract."""

    def __init__(self, token, games, non_games, pending, clips, foreground, now=None):
        self.token = token
        self.games = games
        self.non_games = non_games
        self.pending = pending
        self.clips = clips
        self.foreground = foreground
        self.clock = now or _now()
        self.paired = False
        self.stats_on = False
        self.streaming = False
        self.obs_connected = True
        self.session = _idle_session()
        self.settings = {
            "launchCapture": "record",
            "replaySeconds": 30,
            "idleTimeout": 4,
            "discardUnder": 0,
            "keepAliveApps": [],
            "recordingRoot": "Videos/Nebula",
            "gameListSync": {"provider": "none", "path": ""},
            "offload": {"target": "nas-vault", "auto": True},
            "remote": {"tailscale": True, "moonlightInstalled": True},
            "hotkey": "`",
            "appVersion": "source",
            "updateAvailable": None,
        }
        self.peers = [
            {"name": "Studio PC", "online": True, "isHost": True},
            {"name": "nas-vault", "online": True, "isHost": False},
        ]
        self._lock = threading.Lock()

    def handle(self, message):
        with self._lock:
            return self._handle(message)

    def note_launch(self, capture):
        """PC-side game launch. Not a phone command. Used by the scripted session."""
        with self._lock:
            if capture not in _LAUNCH:
                return [_error(None, "invalid", "Unknown capture mode.")]
            if not self.foreground:
                return [_error(None, "noGame", "No game in the foreground on Studio PC.")]
            self._begin(capture)
            return [self._event("session", self.session_view())]

    def stats_tick(self):
        with self._lock:
            if not self.stats_on:
                return None
            return self._event("stats", {
                "bitrateMbps": 48.2,
                "droppedFrames": 0,
                "gameFps": 60,
                "gpuTempC": 62,
                "audio": {"game": 0.4, "mic": 0.0, "chat": 0.1},
            })

    def _handle(self, message):
        if not isinstance(message, dict):
            return [_error(None, "malformed", "Message must be an object.")]
        kind = message.get("type")
        mid = message.get("id") if isinstance(message.get("id"), str) else None
        data = message.get("data") if isinstance(message.get("data"), dict) else {}
        if not isinstance(kind, str) or not kind:
            return [_error(mid, "malformed", "Message needs a type.")]
        handler = _DISPATCH.get(kind)
        if handler is None:
            return [_error(mid, "unknown", "Unknown message type.")]
        if kind != "hello" and not self.paired:
            return [_error(mid, "unpaired", "Say hello before sending commands.")]
        # Resolved through the instance so a subclass (the real-state studio)
        # can override a verb without touching the table.
        return getattr(self, handler.__name__)(mid, data)

    def _hello(self, mid, data):
        if data.get("deviceToken") != self.token:
            self.paired = False
            return [_error(mid, "unauthorised", "Device token was rejected.")]
        self.paired = True
        return [_ack(mid), self._event("snapshot", self.snapshot())]

    def _start(self, mid, _data):
        if self.session["state"] not in ("idle", "bufferOnly"):
            return [_error(mid, "busy", "A recording is already open.")]
        if not self.foreground:
            return [_error(mid, "noGame", "No game in the foreground on Studio PC.")]
        self._begin("record")
        return [_ack(mid), self._event("session", self.session_view())]

    def _pause(self, mid, _data):
        if self.session["state"] != "recording":
            return [_error(mid, "invalid", "Nothing is recording.")]
        self.session["state"] = "paused"
        self.session["pausedAt"] = _iso(self.clock)
        return [_ack(mid), self._event("session", self.session_view())]

    def _resume(self, mid, _data):
        if self.session["state"] != "paused":
            return [_error(mid, "invalid", "The recording is not paused.")]
        paused_at = _parse(self.session["pausedAt"])
        self.session["pausedTotal"] += max(0.0, (self.clock - paused_at).total_seconds())
        self.session["pausedAt"] = None
        self.session["state"] = "recording"
        return [_ack(mid), self._event("session", self.session_view())]

    def _stop(self, mid, _data):
        if self.session["state"] not in ("recording", "paused", "bufferOnly"):
            return [_error(mid, "invalid", "Nothing is playing.")]
        events = [_ack(mid)]
        last = self.session.get("lastSession")
        if self.session["state"] != "bufferOnly":
            duration = self._elapsed()
            limit = self.settings["discardUnder"]
            kept = not (limit and duration < limit)
            if kept:
                clip = self._finalise(duration)
                self.clips.insert(0, clip)
                events.append(self._event("clip.added", clip))
            last = self._last_view(duration)
        self.session = _idle_session()
        self.session["lastSession"] = last
        events.append(self._event("session", self.session_view()))
        return events

    def _mark(self, mid, data):
        if self.session["state"] not in ("recording", "paused", "bufferOnly"):
            return [_error(mid, "invalid", "Nothing is playing.")]
        label = data.get("label") if isinstance(data.get("label"), str) else None
        self.session["highlights"].append({
            "at": round(self._elapsed(), 3),
            "label": label,
            "kind": "manual",
        })
        return [_ack(mid), self._event("session", self.session_view())]

    def _replay_save(self, mid, _data):
        if self.session["state"] != "bufferOnly":
            return [_error(mid, "invalid", "The replay buffer is not armed.")]
        clip = self._finalise(float(self.settings["replaySeconds"]))
        clip["kind"] = "replay"
        self.clips.insert(0, clip)
        return [_ack(mid), self._event("clip.added", clip)]

    def _stats_on(self, mid, _data):
        self.stats_on = True
        return [_ack(mid)]

    def _stats_off(self, mid, _data):
        self.stats_on = False
        return [_ack(mid)]

    def _classify(self, mid, data):
        pending_id = data.get("pendingId")
        item = next((row for row in self.pending if row["id"] == pending_id), None)
        if item is None:
            return [_error(mid, "notFound", "That app is no longer waiting.")]
        is_game = data.get("isGame")
        if not isinstance(is_game, bool):
            return [_error(mid, "invalid", "isGame must be true or false.")]
        capture = data.get("capture") or "default"
        if is_game and capture not in _CAPTURES:
            return [_error(mid, "invalid", "Unknown capture mode.")]
        self.pending = [row for row in self.pending if row["id"] != pending_id]
        if is_game:
            self.games.insert(0, _game(
                item["id"], item["exe"], "prompt", capture, 0, 0, self.clock,
            ))
        else:
            self.non_games.append({"exe": item["exe"], "displayName": item["exe"]})
        return [
            _ack(mid),
            self._event("app.resolved", {"id": pending_id, "isGame": is_game}),
            self._event("games", {"games": self.games, "nonGames": self.non_games}),
        ]

    def _reclassify(self, mid, data):
        exe = data.get("exe")
        is_game = data.get("isGame")
        if not isinstance(exe, str) or not isinstance(is_game, bool):
            return [_error(mid, "invalid", "exe and isGame are required.")]
        self.games = [row for row in self.games if row["name"] != exe and row["id"] != exe]
        self.non_games = [row for row in self.non_games if row["exe"] != exe]
        if is_game:
            self.games.insert(0, _game(exe, exe, "user", "default", 0, 0, self.clock))
        else:
            self.non_games.append({"exe": exe, "displayName": exe})
        return [
            _ack(mid),
            self._event("app.resolved", {"id": exe, "isGame": is_game}),
            self._event("games", {"games": self.games, "nonGames": self.non_games}),
        ]

    def _set_capture(self, mid, data):
        capture = data.get("capture")
        if capture not in _CAPTURES:
            return [_error(mid, "invalid", "Unknown capture mode.")]
        game = next((row for row in self.games if row["id"] == data.get("gameId")), None)
        if game is None:
            return [_error(mid, "notFound", "No game with that id.")]
        game["capture"] = capture
        return [_ack(mid), self._event("games", {"games": self.games, "nonGames": self.non_games})]

    def _set_setting(self, mid, data):
        key = data.get("key")
        if key not in ALLOWED_SETTINGS:
            return [_error(mid, "readOnly", "That setting is not writable from the phone.")]
        value = data.get("value")
        problem = _check_setting(key, value)
        if problem:
            return [_error(mid, "invalid", problem)]
        _write_setting(self.settings, key, value)
        return [_ack(mid), self._event("settings", self.settings)]

    def _list_clips(self, mid, data):
        rows = self._matching(data.get("gameId"), data.get("query"))
        start = _cursor(data.get("cursor"))
        page = rows[start:start + _PAGE]
        nxt = start + _PAGE
        return [_ack(mid, {
            "clips": page,
            "nextCursor": str(nxt) if nxt < len(rows) else None,
        })]

    def _delete_clip(self, mid, data):
        # In-memory mock only. A real build must not remove a recording from
        # disk or from the NAS; that decision is not this module's to make.
        clip_id = data.get("id")
        clip = next((row for row in self.clips if row["id"] == clip_id), None)
        if clip is None:
            return [_error(mid, "notFound", "No clip with that id.")]
        self.clips = [row for row in self.clips if row["id"] != clip_id]
        return [_ack(mid), self._event("clip.removed", {"id": clip_id})]

    def _trim_clip(self, mid, data):
        clip = next((row for row in self.clips if row["id"] == data.get("id")), None)
        if clip is None:
            return [_error(mid, "notFound", "No clip with that id.")]
        if clip["writing"] or isinstance(clip["offload"], dict):
            return [_error(mid, "busy", "That clip is still being written or copied.")]
        start, end = data.get("in"), data.get("out")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
            return [_error(mid, "invalid", "Trim needs an in point before an out point.")]
        born = dict(clip)
        born["id"] = clip["id"] + "-trim"
        born["duration"] = float(end - start)
        born["file"] = clip["file"].replace(".mkv", "-trim.mkv")
        born["offload"] = "none"
        born["locations"] = ["pc"]
        self.clips.insert(0, born)
        return [_ack(mid), self._event("clip.added", born)]

    def _stream(self, mid, _data):
        if not self.settings["remote"]["moonlightInstalled"]:
            return [_error(mid, "noMoonlight", "Moonlight is not installed on the phone.")]
        self.streaming = True
        return [_ack(mid)]

    def _begin(self, capture):
        state = "bufferOnly" if capture == "buffer" else "recording"
        self.session = {
            "state": state,
            "game": dict(self.foreground),
            "startedAt": _iso(self.clock),
            "pausedTotal": 0.0,
            "pausedAt": None,
            "scene": "Gameplay",
            "output": {"resolution": "1920x1080", "fps": 60, "encoder": "NVENC"},
            "bytesWritten": 0,
            "highlights": [],
            "storageFreeBytes": 212_000_000_000,
            "estimatedRemaining": 4 * 24 * 3600.0,
            "lastSession": self.session.get("lastSession"),
        }

    def _elapsed(self):
        started = _parse(self.session["startedAt"])
        end = self.clock
        if self.session["state"] == "paused" and self.session["pausedAt"]:
            end = _parse(self.session["pausedAt"])
        return max(0.0, (end - started).total_seconds() - self.session["pausedTotal"])

    def _finalise(self, duration):
        game = self.session["game"] or self.foreground or {"id": "unknown", "name": "Unknown"}
        stamp = self.clock.strftime("%Y%m%d-%H%M%S")
        return {
            "id": "clip-%s" % stamp,
            "game": {"id": game["id"], "name": game["name"]},
            "file": "%s.mkv" % stamp,
            "folder": game["name"],
            "kind": "recording",
            "createdAt": _iso(self.clock),
            "duration": duration,
            "bytes": self.session["bytesWritten"],
            "resolution": self.session["output"]["resolution"],
            "fps": self.session["output"]["fps"],
            "encoder": self.session["output"]["encoder"],
            "highlights": list(self.session["highlights"]),
            "locations": ["pc"],
            "offload": "queued" if self.settings["offload"]["auto"] else "none",
            "thumbnailURL": "/files/thumb/clip-%s.jpg" % stamp,
            "writing": False,
        }

    def _last_view(self, duration):
        game = self.session.get("game")
        if not game:
            return self.session.get("lastSession")
        return {
            "game": game,
            "endedAt": _iso(self.clock),
            "duration": duration,
            "bytes": self.session["bytesWritten"],
            "highlightCount": len(self.session["highlights"]),
            "offload": "queued" if self.settings["offload"]["auto"] else "none",
        }

    def _matching(self, game_id, query):
        rows = list(self.clips)
        if isinstance(game_id, str) and game_id:
            rows = [row for row in rows if row["game"]["id"] == game_id]
        if isinstance(query, str) and query.strip():
            needle = query.strip().lower()
            rows = [row for row in rows if _haystack(row).find(needle) >= 0]
        return rows

    def snapshot(self):
        return {
            "serverNow": _iso(self.clock),
            "session": self.session_view(),
            "games": self.games,
            "nonGames": self.non_games,
            "pending": self.pending,
            "clips": self.clips[:50],
            "settings": self.settings,
            "peers": self.peers,
            "obs": {"connected": self.obs_connected},
        }

    def session_view(self):
        view = dict(self.session)
        view["highlights"] = list(self.session["highlights"])
        return view

    def _event(self, kind, data):
        return {"type": kind, "id": None, "data": data}

    def advance(self, seconds):
        """Move the mock clock. Tests use this so a pause has a real duration."""
        with self._lock:
            self.clock = self.clock + timedelta(seconds=seconds)


def serve_mock(agent, host="127.0.0.1", port=0):
    """One-client WebSocket around `handle`. Returns (stop_event, bound_port).

    An agent that defines `poll_events()` gets it called every few seconds
    while a client is connected; whatever it returns is pushed unsolicited.
    The seeded mock has no such method, so the tests see no change.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, port))
    listener.listen(1)
    listener.settimeout(0.2)
    bound = listener.getsockname()[1]
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                conn, _addr = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                _speak(conn, agent)
            finally:
                conn.close()
        listener.close()

    threading.Thread(target=loop, name="mobile-mock", daemon=True).start()
    return stop, bound


_PUSH_EVERY_S = 3.0


def _speak(conn, agent):
    _handshake(conn)
    lock = threading.Lock()
    done = threading.Event()
    poll = getattr(agent, "poll_events", None)
    if callable(poll):
        threading.Thread(
            target=_push_loop, args=(conn, lock, done, agent, poll),
            name="mobile-push", daemon=True,
        ).start()
    try:
        while True:
            text = _read_text(conn, lock)
            if text is None:
                return
            try:
                message = json.loads(text)
            except ValueError:
                message = None
            for outbound in agent.handle(message):
                _send_text(conn, json.dumps(outbound), lock)
    finally:
        done.set()


def _push_loop(conn, lock, done, agent, poll):
    while not done.wait(_PUSH_EVERY_S):
        if not agent.paired:
            continue
        try:
            for outbound in poll() or ():
                _send_text(conn, json.dumps(outbound), lock)
        except OSError:
            return
        except Exception:
            continue


def _handshake(conn):
    blob = b""
    while b"\r\n\r\n" not in blob:
        chunk = conn.recv(4096)
        if not chunk:
            raise ConnectionError("client left during the handshake")
        blob += chunk
    header = blob.split(b"\r\n\r\n", 1)[0].decode("latin1")
    key = ""
    for line in header.split("\r\n"):
        if line.lower().startswith("sec-websocket-key:"):
            key = line.split(":", 1)[1].strip()
    digest = hashlib.sha1((key + _WS_GUID).encode("ascii")).digest()
    accept = base64.b64encode(digest).decode("ascii")
    conn.sendall((
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Accept: %s\r\n"
        "\r\n" % accept
    ).encode("ascii"))


def _read_exact(conn, count):
    blob = b""
    while len(blob) < count:
        chunk = conn.recv(count - len(blob))
        if not chunk:
            raise ConnectionError("socket closed")
        blob += chunk
    return blob


def _read_text(conn, lock=None):
    parts = []
    while True:
        head = _read_exact(conn, 2)
        opcode = head[0] & 0x0F
        masked = head[1] & 0x80
        length = head[1] & 0x7F
        if length == 126:
            length = int.from_bytes(_read_exact(conn, 2), "big")
        elif length == 127:
            length = int.from_bytes(_read_exact(conn, 8), "big")
        mask = _read_exact(conn, 4) if masked else b""
        payload = _read_exact(conn, length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        if opcode == 0x8:
            return None
        if opcode == 0x9:
            _send_raw(conn, 0xA, payload, lock)
            continue
        if opcode == 0xA:
            continue
        parts.append(payload)
        if head[0] & 0x80:
            return b"".join(parts).decode("utf-8")


def _send_text(conn, text, lock=None):
    _send_raw(conn, 0x1, text.encode("utf-8"), lock)


def _send_raw(conn, opcode, payload, lock=None):
    length = len(payload)
    if length < 126:
        head = bytes([0x80 | opcode, length])
    elif length < 65536:
        head = bytes([0x80 | opcode, 126]) + length.to_bytes(2, "big")
    else:
        head = bytes([0x80 | opcode, 127]) + length.to_bytes(8, "big")
    if lock is None:
        conn.sendall(head + payload)
        return
    with lock:
        conn.sendall(head + payload)


def _idle_session():
    return {
        "state": "idle",
        "game": None,
        "startedAt": None,
        "pausedTotal": 0.0,
        "pausedAt": None,
        "scene": "Gameplay",
        "output": {"resolution": "1920x1080", "fps": 60, "encoder": "NVENC"},
        "bytesWritten": 0,
        "highlights": [],
        "storageFreeBytes": 212_000_000_000,
        "estimatedRemaining": None,
        "lastSession": None,
    }


def _ack(mid, data=None):
    return {"type": "ack", "id": mid, "data": data or {}}


def _error(mid, code, message):
    return {"type": "error", "id": mid, "data": {"code": code, "message": message}}


def _parse(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _haystack(clip):
    labels = " ".join(
        item.get("label") or "" for item in clip.get("highlights") or []
    )
    return " ".join((clip["game"]["name"], clip["file"], labels)).lower()


def _cursor(value):
    if value in (None, ""):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _check_setting(key, value):
    if key == "launchCapture":
        return None if value in _LAUNCH else "launchCapture must be record, buffer, or both."
    if key == "replaySeconds":
        return None if value in _REPLAY else "replaySeconds must be 15, 30, 60, or 120."
    if key == "idleTimeout":
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 60:
            return None
        return "idleTimeout must be a whole number from 1 to 60."
    if key == "discardUnder":
        if (
            isinstance(value, int) and not isinstance(value, bool)
            and 0 <= value <= 120 and value % 5 == 0
        ):
            return None
        return "discardUnder must be a multiple of 5 from 0 to 120."
    if key == "keepAliveApps":
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return None
        return "keepAliveApps must be a list of exe names."
    if key == "offload.auto":
        return None if isinstance(value, bool) else "offload.auto must be true or false."
    if key == "gameListSync.provider":
        return None if value in _PROVIDERS else "provider must be onedrive or none."
    return "Unknown setting."


def _write_setting(settings, key, value):
    if key == "offload.auto":
        settings["offload"]["auto"] = value
    elif key == "gameListSync.provider":
        settings["gameListSync"]["provider"] = value
    else:
        settings[key] = value


_DISPATCH = {
    "hello": MobileAgent._hello,
    "session.start": MobileAgent._start,
    "session.pause": MobileAgent._pause,
    "session.resume": MobileAgent._resume,
    "session.stop": MobileAgent._stop,
    "session.mark": MobileAgent._mark,
    "replay.save": MobileAgent._replay_save,
    "stats.subscribe": MobileAgent._stats_on,
    "stats.unsubscribe": MobileAgent._stats_off,
    "app.classify": MobileAgent._classify,
    "app.reclassify": MobileAgent._reclassify,
    "game.setCapture": MobileAgent._set_capture,
    "settings.set": MobileAgent._set_setting,
    "clips.list": MobileAgent._list_clips,
    "clip.delete": MobileAgent._delete_clip,
    "clip.trim": MobileAgent._trim_clip,
    "remote.stream": MobileAgent._stream,
}


def main(argv=None):
    """Serve a studio on the Tailscale address only.

    By default the studio is the machine's real state (`obsauto.mobile_real`):
    games from games.json, clips that exist under recording_root, live
    tailnet peers. `--mock` (or NEBULA_MOBILE_MOCK=1) serves `seed_mock()`
    instead, for demos. A failure to build real state exits non-zero; it
    never falls back to the mock behind the user's back.

    The phone types this address itself, and the listener is never opened on
    the home LAN.
    """
    import argparse
    import os
    import time

    from obsauto import tailscale as ts

    parser = argparse.ArgumentParser(prog="python -m obsauto.mobile_agent")
    parser.add_argument("--mock", action="store_true",
                        help="serve the seeded in-memory demo studio")
    parser.add_argument("--root", default=None,
                        help="checkout holding config.json / games.json")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    use_mock = args.mock or os.environ.get("NEBULA_MOBILE_MOCK") == "1"

    try:
        status = ts.status()
    except Exception:
        status = None
    ips = ((status or {}).get("self") or {}).get("ips") or []
    host = ips[0] if ips else None
    if not host:
        print("No Tailscale address. The studio will not listen on the LAN.")
        return 1
    if use_mock:
        agent = seed_mock()
    else:
        try:
            from obsauto.mobile_real import build_real_agent
            agent = build_real_agent(root=args.root)
        except Exception as exc:
            print("Could not read this machine's state: %s" % exc)
            return 1
    _stop, port = serve_mock(agent, host, args.port)
    print("%s studio at ws://%s:%d/nebula" % (
        "Mock" if use_mock else "Real", host, port))
    print("Token for the phone: %s" % agent.token)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        _stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

