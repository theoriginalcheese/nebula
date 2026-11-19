"""The phone's studio, projected from this machine's real state.

`mobile_agent.seed_mock()` stays the test fixture. `python -m obsauto.mobile_agent`
serves what `build_real_agent()` returns instead:

- games / non-games: the classification files Nebula itself keeps
  (`games.json`, the sync-folder copy, the NAS hub copy), merged newest-wins.
- clips: video files that actually exist under `recording_root`, from
  `DiskSnapshot._scan_local()`. An absent or empty root is an empty list.
  Never a sample. A background probe may read a file with ffmpeg to learn
  its length and to write a jpeg into the app cache. That cache is the only
  thing served to the phone. Nothing is written into the footage folder.
- pending: only an unknown exe that is really in the foreground right now.
- peers: every tailnet peer by hostname, online or not, never an address.

Read-only with respect to footage. The one thing this module writes into
Nebula's data is the classification file, through `merge_classifications` +
an atomic replace, so a verdict survives a restart without clobbering
another machine's additions. Thumbnails and measured lengths live in the
app cache, never beside the recording. `clip.delete` and `clip.trim` are
refused, and the recording controls are refused too,
because this agent is not wired to OBS and a pretend recording would put a
pretend clip in the library.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone

from . import classifier as classifier_mod
from .app_log import log_to_file
from .atomic_json import write_json_atomic
from .fsprobe import isdir_within, isfile_within
from .mobile_agent import MOCK_TOKEN, MobileAgent, _ack, _error, _iso
from .phone_state import DiskSnapshot, peer_rows

#: Nebula's own windows and the OBS it drives are never "an unknown app".
SELF_PROCESSES = frozenset((
    "nebula.exe", "python.exe", "pythonw.exe", "python3",
    "obs64.exe", "obs32.exe", "obs.exe", "obs",
))

_REFRESH_EVERY_S = 2.0
_WRITING_WINDOW_S = 20.0
# A stub file in a test is a couple of kilobytes. A real recording is not.
# Skipping the small ones keeps a probe from ever touching a fixture.
_PROBE_MIN_BYTES = 100_000
_THUMB_NAME = re.compile(r"^clip-[0-9a-f]{12}\.jpg$")
_PENDING_CONFIRMATIONS = 2
_PENDING_CAP = 5
_CLIP_CAP = 400


class StoreError(Exception):
    """The classification file could not be updated safely."""


def default_foreground():
    """The foreground window as `{exe, name, title, width, height, fullscreen}`.

    None when nothing usable is in front or this platform has no probe.
    """
    try:
        import win32api
        import win32gui

        from .monitor import get_foreground_window_info
    except Exception:
        return None
    try:
        info = get_foreground_window_info()
        if not info:
            return None
        _pid, exe_path, proc_name, title, _cls = info
        hwnd = win32gui.GetForegroundWindow()
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        screen = win32api.GetMonitorInfo(win32api.MonitorFromWindow(hwnd, 2))["Monitor"]
        return {
            "exe": os.path.basename(exe_path or proc_name or ""),
            "path": exe_path or "",
            "name": proc_name or "",
            "title": title or "",
            "width": max(0, right - left),
            "height": max(0, bottom - top),
            "fullscreen": (left, top, right, bottom) == tuple(screen),
        }
    except Exception:
        return None


class ClassStore:
    """games.json, read from every place Nebula keeps it, written in one."""

    def __init__(self, disk):
        self._disk = disk
        self._lock = threading.Lock()

    def sources(self):
        return list(self._disk.games_sources())

    def target(self):
        """Where Nebula's own classifier writes: the sync folder when one is
        configured and present, else the local copy. Never the NAS hub."""
        cfg = self._disk.config()
        sync = (cfg.get("sync_folder") or "").strip()
        if sync:
            folder = sync if os.path.isabs(sync) else os.path.join(
                os.path.expanduser("~"), sync)
            if isdir_within(folder):
                return os.path.join(folder, "games.json")
        return self.sources()[0]

    def read(self):
        """Every readable copy, oldest first, folded with the real merge so
        the newest file's verdict wins and other copies' additions survive."""
        found = []
        for path in self.sources():
            if isfile_within(path) is not True:
                continue
            try:
                stamp = os.path.getmtime(path)
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                found.append((stamp, data))
        found.sort(key=lambda row: row[0])
        merged = {"games": {}, "non_games": {}}
        for _stamp, data in found:
            merged = classifier_mod.merge_classifications(merged, {
                "games": data.get("games") or {},
                "non_games": data.get("non_games") or {},
            })
        return merged

    def write(self, games=None, non_games=None):
        """Merge a verdict into the target file and replace it atomically.

        The merge treats the verdict as the newer view: an exe lives in
        exactly one bucket afterwards, and whatever else is already on disk
        (another machine's additions) is kept. An unreadable target is
        refused, never overwritten.
        """
        path = self.target()
        with self._lock:
            base_file = {}
            if isfile_within(path) is True:
                try:
                    with open(path, encoding="utf-8") as fh:
                        base_file = json.load(fh)
                except (OSError, ValueError):
                    raise StoreError("games.json could not be read; not overwriting it.")
                if not isinstance(base_file, dict):
                    raise StoreError("games.json is not an object; not overwriting it.")
                base = {"games": base_file.get("games") or {},
                        "non_games": base_file.get("non_games") or {}}
            else:
                base = self.read()
            merged = classifier_mod.merge_classifications(base, {
                "games": dict(games or {}),
                "non_games": dict(non_games or {}),
            })
            payload = dict(base_file)
            payload.update(merged)
            write_json_atomic(path, payload, indent=2, sort_keys=True)
        return path


class RealStudio(MobileAgent):
    """A MobileAgent whose state is read from this machine, not seeded."""

    def __init__(self, token, disk=None, foreground=None, tailscale_status=None,
                 clock=time.time):
        super().__init__(token, [], [], [], [], None)
        self.disk = disk or DiskSnapshot()
        self.store = ClassStore(self.disk)
        self._probe = foreground or default_foreground
        self._status = tailscale_status or _tailscale_status
        self._time = clock
        self._refreshed = 0.0
        self._seen = {}            # exe -> (first_seen_epoch, probes)
        self._pending_names = {}   # pending id -> name to file it under
        self._fresh = set()        # exes the phone classified this run
        self._clip_cache = (0.0, [])
        self._classes = {"games": {}, "non_games": {}}
        self._announced = {"pending": {}, "peers": None, "clips": None, "games": None,
                           "clip_meta": None, "session": None}
        self._media = {}
        self.obs_connected = False
        self.settings = self._settings()
        self.refresh(force=True)
        threading.Thread(target=self._media_loop, name="nebula-clip-media",
                         daemon=True).start()

    # ------------------------------------------------------------- building

    def refresh(self, force=False):
        now = self._time()
        if not force and now - self._refreshed < _REFRESH_EVERY_S:
            return
        self._refreshed = now
        self.clock = datetime.fromtimestamp(now, timezone.utc)
        try:
            self._classes = self.store.read()
        except Exception as exc:
            log_to_file("[PHONE] real games read failed: %s" % exc)
        self.clips = self._clips(now)
        self._build_games()
        self.pending = self._pending(now)
        self.peers = [{"name": row["name"], "online": row["online"], "isHost": False}
                      for row in peer_rows(self._safe_status())]
        self.settings = self._settings()
        self.session = self._real_session()

    def _safe_status(self):
        try:
            return self._status() or {}
        except Exception as exc:
            log_to_file("[PHONE] tailscale status failed: %s" % exc)
            return {}

    def _settings(self):
        cfg = self.disk.config()
        root = (cfg.get("recording_root") or "").replace("\\", "/").rstrip("/")
        offload_root = (cfg.get("nas_offload_root") or "").replace("\\", "/").rstrip("/")
        offload_name = offload_root.rsplit("/", 1)[-1] if offload_root else None
        try:
            from obsauto import moonlight
            moonlight_present = bool(moonlight.available(cfg.get("moonlight_path", "")))
        except Exception:
            moonlight_present = False
        try:
            from obsauto.version import display_version
            version = display_version()
        except Exception:
            version = ""
        return {
            "launchCapture": cfg.get("default_capture_mode") or "record",
            "replaySeconds": cfg.get("replay_seconds") or 30,
            "idleTimeout": cfg.get("idle_timeout_seconds") or 0,
            "discardUnder": cfg.get("min_clip_seconds") or 0,
            "keepAliveApps": list(cfg.get("keep_alive_audio_processes") or []),
            # Last path component only: an absolute path is not for the phone.
            "recordingRoot": root.rsplit("/", 1)[-1] if root else "",
            "gameListSync": {"provider": "onedrive" if cfg.get("sync_folder") else "none",
                             "path": ""},
            "offload": {"target": offload_name, "auto": bool(offload_root)},
            "remote": {"tailscale": bool(self._safe_status().get("self_online")),
                       "moonlightInstalled": moonlight_present},
            "hotkey": cfg.get("toggle_hotkey") or "",
            "appVersion": version,
            "updateAvailable": None,
        }

    def _real_session(self):
        free = None
        root = (self.disk.config().get("recording_root") or "").strip()
        if root and isdir_within(root):
            try:
                free = shutil.disk_usage(root).free
            except OSError:
                free = None
        session = dict(self.session)
        session.update(output={"resolution": "", "fps": 0, "encoder": ""},
                       scene="", storageFreeBytes=free, estimatedRemaining=None)
        clips = getattr(self, "clips", None) or []
        if clips:
            newest = clips[0]
            session["lastSession"] = {
                "game": newest["game"],
                "endedAt": newest["createdAt"],
                "duration": newest.get("duration") or 0,
                "bytes": newest.get("bytes") or 0,
                "highlightCount": len(newest.get("highlights") or []),
                "offload": newest.get("offload") or "none",
            }
        else:
            session["lastSession"] = None
        return session

    def _clips(self, now):
        """Files under recording_root, newest first. The directory walk is
        cached for 30s; the `writing` flag is recomputed on every call."""
        stamp, rows = self._clip_cache
        if not stamp or now - stamp >= 30.0:
            root = (self.disk.config().get("recording_root") or "").strip()
            # Bounded probe first: a dead mapped drive must not hold the socket.
            rows = self.disk._scan_local() if root and isdir_within(root) else []
            rows.sort(key=lambda row: row.get("mtime") or 0, reverse=True)
            rows = rows[:_CLIP_CAP]
            self._clip_cache = (now, rows)
        return [self._clip_row(row, now) for row in rows]

    def _clip_row(self, row, now):
        folder = row.get("game") or ""
        name = folder or "Unsorted"
        mtime = row.get("mtime") or 0
        clip_id = "clip-" + hashlib.sha1(row["rel"].encode("utf-8")).hexdigest()[:12]
        meta = self._media.get(clip_id) or {}
        thumb = ("/thumbs/%s.jpg" % clip_id) if meta.get("thumb") else None
        return {
            "id": clip_id,
            "game": {"id": _slug(name), "name": name},
            "file": row["name"],
            "folder": folder,
            "kind": "recording",
            "createdAt": _iso(datetime.fromtimestamp(mtime, timezone.utc)),
            "duration": meta.get("duration"),
            "bytes": row.get("size"),
            "resolution": "",
            "fps": 0,
            "encoder": "",
            "highlights": [],
            "locations": ["pc"],
            "offload": "none",
            "thumbnailURL": thumb,
            "writing": (now - mtime) < _WRITING_WINDOW_S,
        }

    def _build_games(self):
        raw = self._classes.get("games") or {}
        groups = {}
        for exe, value in raw.items():
            info = value if isinstance(value, dict) else {}
            name = (info.get("display_name") or exe).strip() or exe
            groups.setdefault(name, []).append((exe, info))
        stats = {}
        for clip in self.clips:
            slot = stats.setdefault(clip["game"]["id"], {"n": 0, "bytes": 0, "last": 0})
            slot["n"] += 1
            slot["bytes"] += clip["bytes"] or 0
            slot["last"] = max(slot["last"], _epoch(clip["createdAt"]))
        weeks = self._weeks()
        rows = []
        for name in sorted(groups, key=str.lower):
            members = sorted(groups[name], key=lambda pair: pair[0])
            first = members[0][1]
            gid = _slug(name)
            slot = stats.get(gid) or {"n": 0, "bytes": 0, "last": 0}
            capture = first.get("capture")
            source = first.get("source") or "manual"
            if any(exe in self._fresh for exe, _ in members):
                source = "prompt"
            rows.append({
                "id": gid,
                "name": name,
                "source": "steam" if source == "steam" else (
                    "prompt" if source == "prompt" else "user"),
                "capture": capture if capture in classifier_mod.CAPTURE_MODES else "default",
                "clipCount": slot["n"],
                "bytes": slot["bytes"],
                "coverURL": None,
                "lastPlayed": _iso(datetime.fromtimestamp(slot["last"], timezone.utc))
                if slot["last"] else None,
                "weekPlaytime": weeks.get(name.lower(), []),
                "exes": [exe for exe, _ in members],
            })
        self._group_exes = {row["id"]: row.pop("exes") for row in rows}
        self.games = rows
        self.non_games = [{"exe": exe, "displayName": exe}
                          for exe in sorted(self._classes.get("non_games") or {},
                                            key=str.lower)]

    def _weeks(self):
        """Recorded seconds per game for the last seven days, from sessions.jsonl."""
        try:
            from . import session_log
            spans = session_log.spans(now=self._time()) or []
            today = session_log.day_start(self._time())
        except Exception:
            return {}
        out = {}
        for span in spans:
            key = str(span.get("game") or "").lower()
            if not key:
                continue
            days = out.setdefault(key, [0.0] * 7)
            for index in range(7):
                begin = today - (6 - index) * 86400
                days[index] += session_log.span_recorded_seconds(
                    span, now=self._time(), window=(begin, begin + 86400))
        return {key: [round(value, 1) for value in days] for key, days in out.items()}

    # -------------------------------------------------------------- pending

    def _pending(self, now):
        try:
            fg = self._probe()
        except Exception:
            fg = None
        exe = str((fg or {}).get("exe") or "").lower()
        if not exe or not self._is_unknown(exe, (fg or {}).get("path") or "",
                                           (fg or {}).get("name") or ""):
            self._seen = {}
            return []
        first, probes = self._seen.get(exe, (now, 0))
        self._seen = {exe: (first, probes + 1)}
        if probes + 1 < _PENDING_CONFIRMATIONS:
            return []
        pid = "pending-" + _slug(os.path.splitext(exe)[0])
        stem = os.path.splitext(fg.get("exe") or exe)[0]
        self._pending_names[pid] = stem
        return [{
            "id": pid,
            "exe": fg.get("exe") or exe,
            "window": {"fullscreen": bool(fg.get("fullscreen")),
                       "width": int(fg.get("width") or 0),
                       "height": int(fg.get("height") or 0)},
            "inSteam": False,
            "seenAt": _iso(datetime.fromtimestamp(first, timezone.utc)),
        }][:_PENDING_CAP]

    def _is_unknown(self, exe, path, proc_name):
        """True only when nothing already has a verdict on this exe.

        Games and non-games from the files, the built-in denylist and
        known-games table, installer helpers, Nebula/OBS themselves, and
        anything installed under steamapps (desktop Nebula files those
        from the Steam library itself) are never pending.
        """
        if exe in SELF_PROCESSES or (proc_name or "").lower() in SELF_PROCESSES:
            return False
        if exe in (self._classes.get("games") or {}):
            return False
        if exe in (self._classes.get("non_games") or {}):
            return False
        if exe in classifier_mod.DENYLIST or exe in classifier_mod.KNOWN_GAMES:
            return False
        if classifier_mod._looks_like_installer_helper(exe):
            return False
        if "steamapps" in (path or "").replace("\\", "/").lower():
            return False
        return True

    # ------------------------------------------------------------- the wire

    def _hello(self, mid, data):
        self.refresh(force=True)
        return super()._hello(mid, data)

    def snapshot(self):
        self.refresh()
        view = super().snapshot()
        view["games"] = self.games
        return view

    def _list_clips(self, mid, data):
        self.refresh()
        return super()._list_clips(mid, data)

    def _classify(self, mid, data):
        self.refresh(force=True)
        pending_id = data.get("pendingId")
        item = next((row for row in self.pending if row["id"] == pending_id), None)
        if item is None:
            return [_error(mid, "notFound", "That app is no longer waiting.")]
        is_game = data.get("isGame")
        if not isinstance(is_game, bool):
            return [_error(mid, "invalid", "isGame must be true or false.")]
        capture = data.get("capture") or "default"
        if is_game and capture not in ("default",) + tuple(classifier_mod.CAPTURE_MODES):
            return [_error(mid, "invalid", "Unknown capture mode.")]
        exe = item["exe"].lower()
        try:
            if is_game:
                entry = {"display_name": self._pending_names.get(pending_id)
                         or os.path.splitext(item["exe"])[0],
                         "source": "manual"}
                if capture != "default":
                    entry["capture"] = capture
                self.store.write(games={exe: entry})
                self._fresh.add(exe)
            else:
                self.store.write(non_games={exe: True})
        except (StoreError, OSError) as exc:
            log_to_file("[PHONE] classify not saved: %s" % exc)
            return [_error(mid, "unsaved", "Studio PC couldn't save that. Try again.")]
        self._seen = {}
        self.refresh(force=True)
        return [
            _ack(mid),
            self._event("app.resolved", {"id": pending_id, "isGame": is_game}),
            self._event("games", {"games": self.games, "nonGames": self.non_games}),
        ]

    def _reclassify(self, mid, data):
        exe = data.get("exe")
        is_game = data.get("isGame")
        if not isinstance(exe, str) or not isinstance(is_game, bool) or not exe.strip():
            return [_error(mid, "invalid", "exe and isGame are required.")]
        self.refresh(force=True)
        targets = self._resolve_exes(exe.strip())
        try:
            if is_game:
                games = {}
                for key in targets:
                    prior = (self._classes.get("games") or {}).get(key)
                    entry = dict(prior) if isinstance(prior, dict) else {}
                    entry.setdefault("display_name", os.path.splitext(key)[0])
                    entry.setdefault("source", "manual")
                    games[key] = entry
                self.store.write(games=games)
            else:
                self.store.write(non_games={key: True for key in targets})
        except (StoreError, OSError) as exc:
            log_to_file("[PHONE] reclassify not saved: %s" % exc)
            return [_error(mid, "unsaved", "Studio PC couldn't save that. Try again.")]
        self.refresh(force=True)
        return [
            _ack(mid),
            self._event("app.resolved", {"id": exe, "isGame": is_game}),
            self._event("games", {"games": self.games, "nonGames": self.non_games}),
        ]

    def _resolve_exes(self, token):
        """A typed exe, or a game's display name meaning all of its exes."""
        lowered = token.lower()
        games = self._classes.get("games") or {}
        if lowered in games or lowered in (self._classes.get("non_games") or {}):
            return [lowered]
        by_name = [key for key, value in games.items()
                   if str((value or {}).get("display_name") or "").lower() == lowered]
        if by_name:
            return sorted(by_name)
        return [lowered]

    def _set_capture(self, mid, data):
        capture = data.get("capture")
        if capture not in ("default",) + tuple(classifier_mod.CAPTURE_MODES):
            return [_error(mid, "invalid", "Unknown capture mode.")]
        self.refresh(force=True)
        exes = self._group_exes.get(data.get("gameId"))
        if not exes:
            return [_error(mid, "notFound", "No game with that id.")]
        games = {}
        for key in exes:
            prior = (self._classes.get("games") or {}).get(key)
            entry = dict(prior) if isinstance(prior, dict) else {}
            if capture == "default":
                entry.pop("capture", None)
            else:
                entry["capture"] = capture
            games[key] = entry
        try:
            self.store.write(games=games)
        except (StoreError, OSError) as exc:
            log_to_file("[PHONE] capture not saved: %s" % exc)
            return [_error(mid, "unsaved", "Studio PC couldn't save that. Try again.")]
        self.refresh(force=True)
        return [_ack(mid), self._event("games", {"games": self.games,
                                                 "nonGames": self.non_games})]

    # Nothing below may touch a recording, and nothing may pretend to.

    def _delete_clip(self, mid, _data):
        return [_error(mid, "readOnly", "Clips are never deleted from the phone.")]

    def _trim_clip(self, mid, _data):
        return [_error(mid, "readOnly", "Trimming isn't available from the phone yet.")]

    def _set_setting(self, mid, _data):
        return [_error(mid, "readOnly", "That setting is not writable from the phone.")]

    def _no_obs(self, mid, _data):
        return [_error(mid, "obsUnavailable",
                       "Recording control isn't connected to OBS from this agent.")]

    _start = _pause = _resume = _stop = _mark = _replay_save = _no_obs

    def _stream(self, mid, _data):
        return [_ack(mid)]

    # ---------------------------------------------------------------- push

    def poll_events(self):
        """Unsolicited events since the last poll: a new pending app, one that
        went away, peers that changed, clips that appeared or vanished."""
        with self._lock:
            self.refresh(force=True)
            events = []
            last = self._announced
            now_pending = {row["id"]: row for row in self.pending}
            for pid, row in now_pending.items():
                if pid not in last["pending"]:
                    events.append(self._event("app.pending", row))
            for pid in last["pending"]:
                if pid not in now_pending:
                    events.append(self._event("app.resolved", {"id": pid}))
            last["pending"] = now_pending
            if last["peers"] is not None and last["peers"] != self.peers:
                events.append(self._event("peers", {"peers": self.peers}))
            last["peers"] = list(self.peers)
            ids = [row["id"] for row in self.clips]
            if last["clips"] is not None:
                before = set(last["clips"])
                for row in self.clips:
                    if row["id"] not in before:
                        events.append(self._event("clip.added", row))
                after = set(ids)
                for cid in last["clips"]:
                    if cid not in after:
                        events.append(self._event("clip.removed", {"id": cid}))
            last["clips"] = ids
            marker = json.dumps([self.games, self.non_games], sort_keys=True)
            if last["games"] is not None and last["games"] != marker:
                events.append(self._event("games", {"games": self.games,
                                                    "nonGames": self.non_games}))
            last["games"] = marker
            meta = {row["id"]: (row.get("duration"), row.get("thumbnailURL"))
                    for row in self.clips}
            if last.get("clip_meta") is not None:
                prev = last["clip_meta"]
                for row in self.clips:
                    if row["id"] in prev and prev[row["id"]] != meta.get(row["id"]):
                        events.append(self._event("clip.updated", row))
            last["clip_meta"] = meta
            session_sig = json.dumps(self.session.get("lastSession"), sort_keys=True)
            if last.get("session") is not None and last["session"] != session_sig:
                events.append(self._event("session", self.session))
            last["session"] = session_sig
            return events

    # --------------------------------------------------------------- media

    def _cache_dir(self):
        from .paths import APP_DIR
        path = os.path.join(APP_DIR, "phone_clip_cache")
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
        return path

    def thumb_bytes(self, name):
        """A cached jpeg, or None. The name is a fixed pattern, so a request
        cannot point at a recording."""
        if not isinstance(name, str) or not _THUMB_NAME.match(name):
            return None
        path = os.path.join(self._cache_dir(), name)
        try:
            with open(path, "rb") as fh:
                data = fh.read(2_000_000)
        except OSError:
            return None
        if not data.startswith(b"\xff\xd8"):
            return None
        return data

    def _media_loop(self):
        while True:
            with self._lock:
                job = self._next_media_job()
            if job is None:
                time.sleep(2.0)
                continue
            measured = _measure_clip(job["path"], job["dest"])
            with self._lock:
                self._media[job["id"]] = measured

    def _next_media_job(self):
        root = (self.disk.config().get("recording_root") or "").strip()
        if not root:
            return None
        root_abs = os.path.abspath(root)
        _, rows = self._clip_cache
        for row in rows:
            clip_id = "clip-" + hashlib.sha1(row["rel"].encode("utf-8")).hexdigest()[:12]
            if clip_id in self._media:
                continue
            rel = (row.get("rel") or "").replace("/", os.sep).replace("\\", os.sep)
            full = os.path.abspath(os.path.join(root, rel))
            try:
                inside = os.path.commonpath([root_abs, full]) == root_abs
            except ValueError:
                inside = False
            size = row.get("size") or 0
            if not inside or size < _PROBE_MIN_BYTES:
                self._media[clip_id] = {"duration": None, "thumb": False}
                continue
            return {"id": clip_id, "path": full,
                    "dest": os.path.join(self._cache_dir(), clip_id + ".jpg")}
        return None


def _tailscale_status():
    from obsauto import tailscale
    return tailscale.status()


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "unknown"


def _epoch(stamp):
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc).timestamp()


def _measure_clip(path, dest):
    """Read-only. The jpeg is written to `dest` in the app cache, never next
    to the recording. A failure leaves the length unknown and no thumbnail."""
    return {"duration": _ffprobe_duration(path), "thumb": _ffmpeg_thumb(path, dest)}


def _ffprobe_duration(path):
    tool = shutil.which("ffprobe")
    if not tool:
        return None
    from .silent_proc import run_kwargs
    try:
        done = subprocess.run(
            [tool, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            timeout=12, capture_output=True, **run_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    try:
        value = float((done.stdout or b"").decode("ascii", "replace").strip())
    except ValueError:
        return None
    if value <= 0 or value > 60 * 60 * 48:
        return None
    return value


def _ffmpeg_thumb(path, dest):
    tool = shutil.which("ffmpeg")
    if not tool:
        return False
    from .silent_proc import run_kwargs
    part = dest + ".part"
    for seek in ("3", "0"):
        try:
            subprocess.run(
                [tool, "-y", "-ss", seek, "-i", path, "-frames:v", "1",
                 "-vf", "scale=640:-2", "-q:v", "5", part],
                timeout=20, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **run_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if _jpeg_file(part):
            try:
                os.replace(part, dest)
                return True
            except OSError:
                return False
        # A failed attempt is not a recording. Leave the part file; the next
        # seek overwrites it. Nothing in the footage tree is removed.
    return False


def _jpeg_file(path):
    try:
        with open(path, "rb") as fh:
            return fh.read(3).startswith(b"\xff\xd8") and os.path.getsize(path) > 32
    except OSError:
        return False


def build_real_agent(root=None, token=None, **kwargs):
    """The studio `python -m obsauto.mobile_agent` serves by default."""
    token = token or os.environ.get("NEBULA_MOBILE_TOKEN") or MOCK_TOKEN
    return RealStudio(token, disk=DiskSnapshot(root=root), **kwargs)
