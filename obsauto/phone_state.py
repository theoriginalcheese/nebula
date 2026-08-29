"""Build an `Api.snapshot()`-shaped payload from files, with no GUI.

    from obsauto.phone_state import DiskSnapshot
    DiskSnapshot().snapshot()          # same shape spike/app.py's Api emits

Why this exists: the phone agent's normal source is the live `Api` inside
desktop Nebula, which only runs in a logged-in desktop session. After a reboot
with nobody logged in there is no Api, so the phone would show nothing. This
reads the same underlying files Nebula does and emits the same shape, which
means `phone_agent.project()` consumes it unchanged.

Running a second `Api()` instead was the obvious idea and is the wrong one: two
instances would both write `clip_index.json` and the icon caches, and under the
SYSTEM account the per-user config paths resolve somewhere else entirely.
Reading files avoids both problems.

**Strictly read-only, and never opens a recording.** Clip discovery is
`os.scandir` plus `stat` - directory metadata only. Nothing here opens, moves,
hashes or deletes a video, and no absolute path leaves the process (the agent
scrubs those on the way out as a second line of defence).

What is honestly knowable headless: clips, session history, the games list,
tailnet peers, the disk forecast, Moonlight's last known state, and whether a
recording is running (a `session_log` span with no rec_stop is live). What is
not: live bitrate and scene name, which only OBS knows - those stay null and
render as an em-dash rather than being guessed at.
"""
import json
import os
import shutil
import time

from obsauto.app_log import log_to_file

#: Rescan interval for the clip sweep. A 5s phone poll must not re-walk the
#: recordings tree every time; the tree changes on the order of minutes.
SCAN_TTL_S = 30.0

#: Newest-first cut applied before the agent's own cap, so a huge library never
#: turns into a huge walk result held in memory.
CLIP_SCAN_LIMIT = 400

VIDEO_SUFFIXES = (".mkv", ".mp4", ".mov", ".flv", ".ts", ".m4v")


def _format_bytes(n):
    """Match the desktop's readouts: 62.5 KB, 4.2 GB."""
    try:
        value = float(n)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return ("%.0f %s" if unit == "B" else "%.1f %s") % (value, unit)
        value /= 1024.0
    return ""


def _clock(seconds):
    """Elapsed seconds -> "HH:MM:SS", the form `project()` parses back."""
    seconds = int(max(0, seconds))
    return "%02d:%02d:%02d" % (seconds // 3600, (seconds % 3600) // 60, seconds % 60)


class DiskSnapshot:
    """`Api.snapshot()`-shaped payload assembled from files. Read-only."""

    def __init__(self, root=None, config=None, clock=time.time):
        self._root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._config = config
        self._clock = clock
        self._scan = (0.0, [])

    # ---------------------------------------------------------------- config

    def config(self):
        if self._config is None:
            self._config = self._read_json("config.json", {})
        return self._config

    def _path(self, name):
        return os.path.join(self._root, name)

    def _read_json(self, name, fallback):
        try:
            with open(self._path(name), encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return fallback

    # -------------------------------------------------------------- snapshot

    def snapshot(self):
        """Every section is independently guarded, matching `Api.snapshot()`:
        one unreadable file must not blank the rest of the phone."""
        def part(name, fn, fallback):
            try:
                return fn()
            except Exception as exc:
                log_to_file("[PHONE] disk snapshot %s failed: %s" % (name, exc))
                return fallback

        spans = part("spans", self._spans, [])
        return {
            "hero": part("hero", lambda: self._hero(spans),
                         {"state": "disconnected"}),
            "forecast": part("forecast", lambda: self._forecast(spans),
                             {"label": "", "rate": "", "used_pct": 0}),
            "clips_panel": part("clips", lambda: {"clips": self._clips()},
                                {"clips": []}),
            "games": part("games", self._games,
                          {"games": [], "non_games": [], "pending": []}),
            "remote": part("remote", self._remote, {}),
        }

    # ------------------------------------------------------------------ hero

    def _spans(self):
        from obsauto import session_log
        return session_log.spans(now=self._clock()) or []

    def _hero(self, spans):
        """A span with no rec_stop is the live recording - that is the whole
        test, and it needs no OBS connection."""
        live = next((s for s in reversed(spans) if s.get("live")), None)
        if not live:
            return {"state": "saved" if spans else "disconnected"}
        started = live.get("start") or self._clock()
        return {
            "state": "recording",
            "title": live.get("game") or "",
            "elapsed": _clock(self._clock() - started),
            "size": _format_bytes(live.get("size")) if live.get("size") else "",
            # Scene and encoder are OBS-only facts; headless they are unknown,
            # and unknown must read as unknown.
            "scene": "",
            "video": "",
            "bitrate": "",
        }

    # -------------------------------------------------------------- forecast

    def _forecast(self, spans):
        from obsauto import forecast as forecast_mod
        root = self.config().get("recording_root") or ""
        if not root or not os.path.isdir(root):
            return {"label": "drive unavailable", "rate": "", "used_pct": 0}
        usage = shutil.disk_usage(root)
        f = forecast_mod.forecast(usage.free, usage.total, spans, now=self._clock())
        if not f.get("ready"):
            return {"label": "", "rate": "", "used_pct": usage.used / float(usage.total or 1)}
        return {
            "label": forecast_mod.days_left_label(f["days_left"]) + " left",
            "rate": "",
            "used_pct": usage.used / float(usage.total or 1),
        }

    # ----------------------------------------------------------------- clips

    def _clips(self):
        now = self._clock()
        cached_at, cached = self._scan
        if cached and (now - cached_at) < SCAN_TTL_S:
            return cached
        rows = self._scan_local() + self._nas_index()
        rows.sort(key=lambda c: c.get("mtime") or 0, reverse=True)
        rows = rows[:CLIP_SCAN_LIMIT]
        self._scan = (now, rows)
        return rows

    def _scan_local(self):
        """Recordings under `recording_root`, one level of game folders deep.

        Metadata only - `scandir`/`stat`. Nothing here opens a video.
        """
        root = self.config().get("recording_root") or ""
        if not root or not os.path.isdir(root):
            return []
        out = []
        for entry in self._safe_scandir(root):
            if entry.is_dir():
                game = entry.name
                for f in self._safe_scandir(entry.path):
                    self._collect(out, f, game, root)
            else:
                self._collect(out, entry, "", root)
        return out

    @staticmethod
    def _safe_scandir(path):
        try:
            with os.scandir(path) as it:
                return list(it)
        except OSError:
            return []

    def _collect(self, out, entry, game, root):
        if not entry.name.lower().endswith(VIDEO_SUFFIXES):
            return
        try:
            if not entry.is_file():
                return
            st = entry.stat()
        except OSError:
            return
        rel = os.path.relpath(entry.path, root).replace("\\", "/")
        out.append({
            "rel": rel,
            "game": game,
            "name": entry.name,
            "title": os.path.splitext(entry.name)[0],
            "size_label": _format_bytes(st.st_size),
            "mtime": st.st_mtime,
            "location": "local",
            # Duration needs a probe of the file itself, which is exactly what
            # this module does not do. Null renders as an em-dash.
            "length": "",
        })

    def _nas_index(self):
        """Already-offloaded clips, from the index Nebula maintains.

        Read from the index rather than the NAS so a sleeping or unreachable
        NAS costs nothing and blocks nothing.
        """
        data = self._read_json("clip_index.json", {})
        out = []
        for entry in (data.get("entries") or []):
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or ""
            if not name:
                continue
            out.append({
                "rel": entry.get("rel") or name,
                "game": entry.get("game") or "",
                "name": name,
                "title": os.path.splitext(name)[0],
                "size_label": _format_bytes(entry.get("size")),
                "mtime": entry.get("mtime") or entry.get("offloaded_at") or 0,
                "location": "remote",
                "length": "",
            })
        return out

    # ----------------------------------------------------------------- games

    def games_sources(self):
        """Where a populated games.json might be, best first.

        The repo copy is often empty: the classifier keeps the real list in the
        sync folder and on the NAS, and only writes back locally on change. The
        NAS path is a mapped drive, so it resolves for the logged-in user and
        not for a service account - it is tried last and its absence is normal.
        """
        cfg = self.config()
        out = [self._path("games.json")]
        sync = (cfg.get("sync_folder") or "").strip()
        if sync:
            out.append(os.path.join(os.path.expanduser("~"), sync, "games.json"))
        nas = (cfg.get("nas_offload_root") or "").strip()
        if nas:
            out.append(os.path.join(nas, ".nebula", "games.json"))
        return out

    def _games(self):
        """Group exes by display name, the same fold `Api._games` performs."""
        # Take the richest source, not the first readable one: the repo copy
        # usually has a couple of non_games and no games at all, which would
        # otherwise win and report an empty library.
        data = {}
        best = -1
        for candidate in self.games_sources():
            try:
                with open(candidate, encoding="utf-8") as fh:
                    found = json.load(fh)
            except Exception:
                continue
            if not isinstance(found, dict):
                continue
            count = len(found.get("games") or {})
            if count > best:
                data, best = found, count
        raw = data.get("games") or {}
        by_name = {}
        for key, value in raw.items():
            name = (value.get("display_name") or key) if isinstance(value, dict) else key
            by_name.setdefault(name, []).append(key)
        games = [{"name": name, "exes": sorted(by_name[name])}
                 for name in sorted(by_name, key=str.lower)]
        non = [{"name": k} for k in sorted(data.get("non_games") or {}, key=str.lower)]
        # No classifier is running headless, so nothing is awaiting a verdict.
        return {"games": games, "non_games": non, "pending": []}

    # ---------------------------------------------------------------- remote

    def _remote(self):
        return {
            "tailscale": {"peers": self._peers()},
            "moonlight": self._moonlight(),
            "offload": self._offload(),
        }

    def _peers(self):
        from obsauto import tailscale as ts
        status = ts.status() or {}
        out = []
        for peer in (status.get("peer_list") or []):
            # peer_list entries are keyed `hostname`, not `name`.
            name = (peer.get("hostname") or peer.get("name") or "").strip()
            if not name:
                continue
            out.append({"name": name, "online": bool(peer.get("online")),
                        "status": "Online" if peer.get("online") else "Offline"})
        return out

    def _moonlight(self):
        from obsauto import moonlight as moon
        try:
            details = moon.log_details() or {}
        except Exception:
            details = {}
        # Headless there is no window to inspect, so "live" is never claimed -
        # only what the log last recorded.
        return {"state": "idle" if details else "unknown"}

    def _offload(self):
        state = self._read_json("offload_state.json", {})
        queue = self._read_json("offload_queue.json", [])
        pending = len(queue) if isinstance(queue, list) else 0
        if not pending:
            return {"enabled": False, "text": ""}
        return {
            "enabled": True,
            "text": "%d clip%s queued%s" % (
                pending, "" if pending == 1 else "s",
                (" · %s" % state.get("last_message")) if state.get("last_message") else "",
            ),
        }
