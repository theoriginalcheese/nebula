"""Nebula v4 spike - the same chassis, rendered by WebView2 instead of tk.Canvas.

    python spike/app.py

What this is testing, in order of how much it matters:

 1. Does the backdrop the spec asks for - drifting aurora, parallax star
    layers, pointer spotlight, pointer lean, pulsing live block - run at 60fps
    for ~0% CPU? On tk.Canvas it measured p50 110ms at 95% CPU and had to be
    baked static. Every one of those is live here.
 2. Does it cost less than gui.py at idle, in RAM and CPU, *while a game is in
    the foreground*? That is the constraint that actually governs Nebula: it is
    a tray app that runs the whole time you are playing.
 3. Do the existing modules drop straight in? Nothing in obsauto/ is modified
    by this file. It imports session_log, forecast, config and thumbs exactly
    as they are and renders what they return.

The HUD in the bottom right is the answer to 1 and 2. Watch `frame p50`.
"""
import ctypes
import base64
import os
import random
import re
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psutil
import webview

from obsauto import app_icons
from obsauto import design_v3 as dv
from obsauto import forecast as forecast_mod
from obsauto import palette as palette_mod
from obsauto import profiles as profiles_mod
from obsauto import session_log
from obsauto import settings_spec
from obsauto.app_log import LOG_FILE, log_to_file, setup_logging
from obsauto.classifier import Classifier
from obsauto.obs_client import OBSClient
from obsauto.config import CONFIG_FILE, load_config, save_config
from obsauto.paths import RESOURCE_DIR
from obsauto import thumbs
from spike import host as host_mod

# Main script is flattened to _MEIPASS/app.py under PyInstaller onefile, so
# dirname(__file__) is _MEIPASS — not spike/. Web assets live at spike/web/.
INDEX = os.path.join(RESOURCE_DIR, "spike", "web", "index.html")

VIDEO_EXT = (".mkv", ".mp4", ".mov", ".flv")

# Same map as gui.py. BUILD-SPEC: "log tag colours stay as LOG_TAG_COLORS in
# gui.py" — the one place non-accent hues are allowed. Duplicated here so the
# webview can paint tags without importing gui.py (and its Tk deps).
LOG_TAG_COLORS = {
    "OBS": "#8B7CF6",
    "Monitor": "#7FB7F0",
    "Steam": "#4FD1C5",
    "Manual": "#F5A623",
    "Classifier": "#F0A6CA",
    "Audio": "#3DDC84",
}

# 6.8 dashboard blocks the spike actually renders (no replay pane yet).
SPIKE_DASH_BLOCKS = ("hero", "stats", "activity")
SPIKE_DASH_LABELS = {
    "hero": "Live session",
    "stats": "Session stats",
    "activity": "Activity",
}
SPIKE_DEFAULT_GRID = [
    {"id": "hero", "span": 12},
    {"id": "stats", "span": 6},
    {"id": "activity", "span": 12},
]
_LEGACY_SPAN = {1: 6, 2: 12}


def normalise_dashboard_layout(saved):
    """Defend a hand-edited config — same rules as gui.py ``_saved_grid``."""
    if not isinstance(saved, list) or not saved:
        return [dict(it) for it in SPIKE_DEFAULT_GRID]
    cleaned, seen = [], set()
    for it in saved:
        if isinstance(it, str):
            key, span = it, dv.GRID_COLS
        else:
            it = it or {}
            key = it.get("id") or it.get("name")
            span = it.get("span", dv.GRID_COLS)
            span = _LEGACY_SPAN.get(span, span)
        if key not in SPIKE_DASH_BLOCKS or key in seen:
            continue
        if span not in dv.SPANS:
            span = dv.GRID_COLS
        cleaned.append({"id": key, "span": dv.GRID_COLS if key == "hero" else span})
        seen.add(key)
    for block in SPIKE_DASH_BLOCKS:
        if block not in seen:
            cleaned.append({"id": block, "span": dv.GRID_COLS})
    return cleaned


def _proc_tree():
    """This process plus every child.

    WebView2 is multi-process - the browser, GPU and renderer are separate
    msedgewebview2.exe children. Measuring only os.getpid() would report the
    Python host alone and flatter the spike by a wide margin, which would make
    the whole exercise pointless.
    """
    me = psutil.Process(os.getpid())
    out = [me]
    try:
        out += me.children(recursive=True)
    except psutil.Error:
        pass
    return out


def _sample(procs):
    rss = 0
    cpu = 0.0
    for p in procs:
        try:
            rss += p.memory_info().rss
            cpu += p.cpu_percent(None)
        except psutil.Error:
            continue
    return rss, cpu


def _short_obs_version(raw):
    """'30.1.2' out of whatever GetVersion returned."""
    return str((raw or "")).strip()


def _friendly_obs_error(exc):
    """Say which of the three things went wrong, not just that one did.

    Onboarding is the one place where the person reading this has never seen
    OBS's WebSocket settings page, so 'ConnectionRefusedError(10061)' is worse
    than useless - it reads as "the app is broken" rather than "tick a box".
    """
    text = str(exc) or exc.__class__.__name__
    low = text.lower()
    if "refused" in low or "10061" in low:
        return ("OBS isn't accepting connections. In OBS: Tools -> WebSocket "
                "Server Settings -> tick 'Enable WebSocket server'.")
    if "auth" in low or "password" in low or "401" in low:
        return "OBS rejected the password. Copy it from that same OBS panel."
    if "timed out" in low or "timeout" in low:
        return "No answer from that host and port. Is OBS running there?"
    return text


class Api:
    def __init__(self):
        # Read before load_config(), which writes the file when it is missing -
        # so "has this machine ever run Nebula" has to be asked first. A
        # missing config.json is the only honest first-run signal: a flag
        # inside the file cannot be false on a machine that has no file, and
        # adding one would have re-run setup for every existing install.
        self._fresh_install = not os.path.exists(CONFIG_FILE)
        self.cfg = load_config()
        # Underscore-prefixed on purpose. pywebview walks the api object's
        # public attributes to expose them to JS; a pywebview Window has a
        # .native.browser.webview whose COM properties throw when touched off
        # the UI thread, and that exception aborts the whole bridge - every
        # api call then fails with no message on the JS side.
        self._window = None
        self._host = None
        self._procs = _proc_tree()
        _sample(self._procs)                 # prime cpu_percent's baseline
        self.seed = random.randrange(1, 2 ** 31)
        self._classifier = Classifier(on_log=self._api_log)
        self._settings_saved_at = None
        self._update_pending = None
        self._update_last_message = ""
        self._update_busy = False
        self._log_filter = "All"
        self._goto_pane = None
        self._clips_cache = None
        self._clips_error = None
        self._clips_root = ""
        self._clip_durations = {}
        self._thumb_data_cache = {}
        self._thumb_scan_busy = False
        self._clips_scan_busy = False
        self._clips_scanned_at = 0.0
        self._ensure_clips_scan()
        self._backfill_icon_paths()

    def _backfill_icon_paths(self):
        """Learn exe paths for anything already running, off the UI thread.

        The Monitor records a path each time it sees a process, so the Games
        pane fills in over time on its own. This is the head start: whatever is
        running at launch gets its real icon on the first visit rather than
        after its next restart.
        """
        def worker():
            try:
                snap = self._classifier.snapshot()
                names = list(snap.get("games", {})) + list(snap.get("non_games", {}))
                found = app_icons.backfill_from_running(names)
                if found:
                    self._api_log("[Icons] Resolved %d app icon%s from running processes."
                                  % (found, "" if found == 1 else "s"))
            except Exception as exc:
                log_to_file("[Icons] Backfill failed: %s" % exc)

        threading.Thread(target=worker, daemon=True).start()

    # --- chassis -------------------------------------------------------

    def config(self):
        """Hand the BACKGROUND spec to the front end rather than re-typing it.

        design_v3.py stays the one place a v3 number lives. The stylesheet gets
        the static tokens via gen_tokens.py; the layout maths (blob counts,
        size fractions, alphas, motion cycles) comes through here as JSON.
        """
        bg = dict(dv.BACKGROUND)
        bg["motion"] = dict(dv.BACKGROUND_MOTION_UNUSED)
        return {
            "seed": self.seed,
            "background": bg,
            "hero_states": {k: dict(v) for k, v in dv.HERO_STATES.items()},
            "paused_timer_opacity": dv.PAUSED_TIMER_OPACITY,
            "log_tags": dict(LOG_TAG_COLORS),
            "idle_timeout_seconds": int(self.cfg.get("idle_timeout_seconds") or 4),
            "reconnect_interval_seconds": int(
                self.cfg.get("reconnect_interval_seconds") or 10),
            "min_clip_seconds": int(self.cfg.get("min_clip_seconds") or 10),
            "toggle_hotkey": self.cfg.get("toggle_hotkey") or "",
            # At boot too, not only in the snapshot: the chrome should already
            # be the user's accent and density on the first paint.
            "appearance": self.appearance(),
            "setup": {
                "needed": self.setup_needed(),
                "values": {k: _settings_display(settings_spec.BY_KEY[k], self.cfg.get(k))
                           for k in ("obs_host", "obs_port", "obs_password",
                                     "recording_root", "toggle_hotkey")
                           if k in settings_spec.BY_KEY},
            },
            "dashboard": {
                "blocks": list(SPIKE_DASH_BLOCKS),
                "labels": dict(SPIKE_DASH_LABELS),
                "default_grid": [dict(it) for it in SPIKE_DEFAULT_GRID],
                "cols": dv.GRID_COLS,
                "gap": dv.GRID_GAP,
                "spans": list(dv.SPANS),
                "span_labels": dict(dv.SPAN_LABELS),
                "layout": self._saved_dashboard_layout(),
            },
            "version": self._version_payload(),
        }

    def _version_payload(self):
        from obsauto.version import version_info
        return version_info()

    # --- first run (mockup 1l) -----------------------------------------

    def setup_needed(self):
        """Show onboarding only on a machine that has never run Nebula."""
        return bool(self._fresh_install) and not self.cfg.get("setup_complete")

    def setup_test_obs(self, host, port, password):
        """Probe obs-websocket with the details typed in step 2.

        Its own short-lived client, deliberately: the host's OBSClient may be
        mid-reconnect against the *old* settings, and the point of this button
        is to answer a question about what was just typed. Blocking is fine -
        pywebview runs api calls off the GUI thread.
        """
        try:
            port = int(str(port).strip() or 4455)
        except ValueError:
            return {"ok": False, "error": "Port needs to be a whole number."}
        probe = OBSClient(str(host or "localhost").strip(), port,
                          str(password or ""), on_log=lambda m: None)
        try:
            probe.connect(timeout=4)
        except Exception as exc:
            return {"ok": False, "error": _friendly_obs_error(exc)}
        try:
            version = _short_obs_version(probe.get_version())
        except Exception:
            version = ""
        ms = probe.last_handshake_ms
        try:
            probe.disconnect()
        except Exception:
            pass
        detail = []
        if version:
            detail.append("OBS %s" % version)
        if ms is not None:
            detail.append("responds in %d ms" % ms)
        return {"ok": True, "text": "Connected", "detail": " · ".join(detail)}

    def setup_choose_folder(self, current=""):
        """Native folder picker for step 3."""
        if not self._window:
            return {"ok": False, "error": "no window"}
        try:
            picked = self._window.create_file_dialog(
                webview.FOLDER_DIALOG, directory=current or "")
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if not picked:
            return {"ok": False, "cancelled": True}
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        return {"ok": True, "path": str(path)}

    def setup_scan_steam(self):
        """Step 4's scan, synchronous so the step can report what it found."""
        try:
            self._classifier.refresh_steam_index()
            self._classifier.register_all_steam_games()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        snap = self._classifier.snapshot()
        return {"ok": True, "games": len(snap.get("games", {}))}

    def setup_finish(self, values=None, skipped=False):
        """Write what setup collected, then behave like a normal launch.

        Every field goes through settings_spec.parse, so onboarding cannot
        write a value the Settings pane would refuse - one validator, not two.
        """
        errors = []
        for key, raw in (values or {}).items():
            field = settings_spec.BY_KEY.get(key)
            if field is None:
                continue
            value, error = settings_spec.parse(field, raw)
            if error:
                errors.append("%s: %s" % (field.label, error))
            else:
                self.cfg[key] = value
        if errors:
            return {"ok": False, "errors": errors}
        self.cfg["setup_complete"] = True
        save_config(self.cfg)
        self._fresh_install = False
        self._api_log("[Setup] First-run setup %s."
                      % ("skipped" if skipped else "complete"))
        if self._host:
            # Rebind against whatever was just written, then start watching.
            try:
                self._host.config.update(self.cfg)
                self._host.call_soon(self._host.start_hotkeys)
                self._host.call_soon(self._host.autostart)
            except Exception as exc:
                self._api_log("[Setup] Couldn't start monitoring: %s" % exc)
        return {"ok": True}

    def _saved_dashboard_layout(self):
        for key in ("dashboard_layout", "dashboard_grid"):
            saved = self.cfg.get(key)
            if isinstance(saved, list) and saved:
                return normalise_dashboard_layout(saved)
        return [dict(it) for it in SPIKE_DEFAULT_GRID]

    def set_dashboard_layout(self, layout):
        """Persist customise-mode edits to config.json."""
        if not isinstance(layout, list):
            return {"ok": False, "error": "layout must be a list"}
        cleaned = normalise_dashboard_layout(layout)
        self.cfg["dashboard_layout"] = cleaned
        self.cfg.pop("dashboard_grid", None)
        save_config(self.cfg)
        self._settings_saved_at = time.time()
        order = " · ".join(
            "%s:%s" % (it["id"], dv.SPAN_LABELS.get(it["span"], it["span"]))
            for it in cleaned)
        self._api_log("[Manual] Dashboard layout saved: %s" % order)
        return {"ok": True, "layout": cleaned,
                "saved_at": time.strftime("%H:%M:%S",
                                           time.localtime(self._settings_saved_at))}

    def _api_log(self, message):
        if self._host:
            self._host._log(message)
        else:
            log_to_file(message)

    # Frame 2j: "Both - and x hide to tray. Quit exists only in this menu."
    # So neither button destroys anything - both land on the same call.
    def close(self):
        if self._host:
            self._host.hide()

    def minimise(self):
        if self._host:
            self._host.hide()

    def tray(self):
        """Let the window show what the tray thinks the state is."""
        if not self._host:
            return {"state": "disconnected", "heading": "", "detail": "",
                    "monitoring": False, "bound": [], "pending": {}}
        s = self._host.tray_status()
        s["bound"] = self._host.hotkeys.bound()
        s["pending"] = self._host.hotkeys.pending()
        return s

    # --- measurement ---------------------------------------------------

    def proc(self):
        self._procs = _proc_tree()
        rss, cpu = _sample(self._procs)
        return {"rss_mb": rss / 1048576.0,
                "cpu_pct": cpu / (psutil.cpu_count() or 1),
                "procs": len(self._procs)}

    def page_awake(self):
        """Sleep flag for JS to poll — evaluate_js from the watcher is best-effort."""
        return {"awake": self._host.awake() if self._host else True}

    def bench(self, seconds=10):
        """Average over a window, which is the only honest way to read CPU."""
        procs = _proc_tree()
        _sample(procs)
        time.sleep(seconds)
        rss, cpu = _sample(procs)
        return {"rss_mb": rss / 1048576.0,
                "cpu_pct": cpu / (psutil.cpu_count() or 1),
                "procs": len(procs), "seconds": seconds}

    # --- real data, straight out of the existing modules ----------------

    def snapshot(self):
        return {"obs": self._obs(),
                "hero": self._hero(),
                "tiles": self._tiles(),
                "activity": self._activity(),
                "ribbon": self._ribbon(),
                "clips_panel": self._clips_panel(),
                "forecast": self._forecast(),
                "games": self._games(),
                "settings": self._settings_payload(),
                "macropad": self._macropad()}

    def _obs(self):
        """One source of truth for connection state: the host.

        An earlier version of this guessed the state from sessions.jsonl - if
        the last span was still open and spans() had just stamped its end with
        now, call it live. That is not a heuristic that can work, and a
        screenshot caught it claiming "Recording" while the tray, three inches
        away, correctly said "OBS disconnected".

        The reason it cannot work: spans() stamps `end = now` on *every* open
        span, so a genuine live recording and a log abandoned mid-recording are
        byte-for-byte identical. sessions.jsonl simply does not carry the
        answer. Only OBS's own GetRecordStatus does, and that arrives in step 2.

        So until then this reports the host's state, which is honestly
        "disconnected", and offers the last clip's age as the fact the log
        *can* support.
        """
        s = (self._host.tray_status() if self._host else
             {"state": "disconnected", "heading": "OBS disconnected"})
        state = s["state"]

        label = s["heading"]
        if state == "disconnected":
            spans = session_log.spans()
            if spans:
                ago = time.time() - max(sp["end"] or 0 for sp in spans)
                label = "Not connected · last clip %s ago" % _ago(ago)
            else:
                label = "Not connected · no sessions logged"

        return {"connected": state != "disconnected",
                "live": state in ("recording", "paused"),
                "label": label,
                "state": state}

    def _hero(self):
        """Frame 2a / 2f–2h. One state enum from the host; nothing fabricated."""
        if not self._host:
            state = "disconnected"
            s = {"heading": "OBS disconnected", "detail": ""}
            readouts = {"elapsed": "", "size": "", "bitrate": ""}
            meta = {"scene": "", "video_label": ""}
        else:
            state = self._host.hero_state()
            s = self._host.tray_status()
            readouts = self._host.hero_readouts()
            meta = self._host.obs_meta()

        hero_key = "watching" if state == "idle" else state
        spec = dv.HERO_STATES.get(hero_key, dv.HERO_STATES["disconnected"])
        idle = int(self.cfg.get("idle_timeout_seconds") or 4)
        reconnect = int(self.cfg.get("reconnect_interval_seconds") or 10)

        eyebrow = {
            "disconnected": "OBS disconnected",
            "idle": "Idle — watching",
            "recording": "Recording",
            "paused": "Paused — idle %d s" % idle,
        }.get(state, spec["eyebrow"])

        title = s.get("heading") or {
            "disconnected": "Can't reach OBS",
            "idle": "No game in focus",
            "recording": "Recording",
            "paused": "Paused",
        }.get(state, "Nebula")

        hint = ""
        source = ""
        if state == "disconnected":
            hint = ("Retrying every %ds — launching from obs_path if it's set."
                    % reconnect)
            title = "Can't reach OBS"
        elif state == "idle":
            hint = ("Standing by — recording starts by itself the moment a "
                    "game launches.")
            detail = (s.get("detail") or "").strip()
            if detail and detail != "No game in focus":
                source = detail

        show_readouts = state in ("recording", "paused")
        scene = meta.get("scene") or ""
        video = meta.get("video_label") or ""
        return {
            "state": state,
            "eyebrow": eyebrow,
            "tint": spec.get("tint") or "",
            "title": title,
            "source": source,
            "hint": hint,
            "show_readouts": show_readouts,
            "elapsed": readouts["elapsed"],
            "size": readouts["size"],
            "bitrate": readouts["bitrate"],
            "scene": scene,
            "video": video,
            "actions": list(spec.get("actions") or ()),
            "actions_enabled": [a for a in (spec.get("actions") or ())
                                if a != "Mark clip"],
        }

    def _tiles(self):
        """Dashboard stat tiles (FRAMES.md 2a / gui.py 6.3). Real zeros are fine."""
        t = session_log.today()
        min_clip = int(self.cfg.get("min_clip_seconds") or 10)
        idle = int(self.cfg.get("idle_timeout_seconds") or 4)
        return [
            {"k": "Clips today", "v": str(t["clips"]),
             "u": "", "sub": "finished today"},
            {"k": "Recorded", "v": _hm(t["recorded_seconds"]),
             "u": "", "sub": "today"},
            {"k": "Auto-culled", "v": str(t["culled"]),
             "u": "", "sub": "under %ds" % min_clip},
            {"k": "Idle pauses", "v": str(t["idle_pauses"]),
             "u": "", "sub": "after %ds idle" % idle},
        ]

    def _activity(self):
        """Newest-first rows from the host buffer (and the log file as fallback)."""
        lines = []
        if self._host:
            lines = self._host.log_lines()
        if not lines:
            lines = _tail_log_file(80)
        rows = []
        for ts, message in reversed(lines[-120:]):
            tag, body = _split_log_tag(message)
            rows.append({
                "ts": time.strftime("%H:%M:%S", time.localtime(ts)),
                "tag": tag,
                "text": body,
                "color": LOG_TAG_COLORS.get(tag, ""),
            })
        tags = ["All"] + sorted(LOG_TAG_COLORS.keys())
        return {"rows": rows, "tags": tags, "filter": self._log_filter}

    def set_log_filter(self, name):
        name = (name or "All").strip()
        if name != "All" and name not in LOG_TAG_COLORS:
            return {"ok": False, "filter": self._log_filter}
        self._log_filter = name
        return {"ok": True, "filter": self._log_filter}

    def copy_log(self):
        rows = self._activity()["rows"]
        text = "\n".join("%s  [%s]  %s" % (r["ts"], r["tag"] or "—", r["text"])
                         for r in rows)
        try:
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            r.clipboard_clear()
            r.clipboard_append(text)
            r.update()
            r.destroy()
            return {"ok": True, "n": len(rows)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _macropad(self):
        """Frame 2e — deliberately empty. No HID layer exists."""
        binding = self.cfg.get("toggle_hotkey") or "—"
        return {
            "empty": True,
            "title": "No device layer yet",
            "body": (
                "The design pairs Nebula with a 3×3 HID macropad: keys bound to "
                "start/stop, pause, mark clip and scene switches, with per-game "
                "profiles that follow whatever you launch.\n\n"
                "Nothing here talks to hardware, so rather than show a mock keypad "
                "that does nothing, this page stays empty until the binding layer "
                "exists."
            ),
            "foot": (
                "Meanwhile the global hotkey  %s  toggles monitoring from "
                "anywhere, bound by scan code so it can't swallow a neighbouring "
                "key." % binding
            ),
        }

    # --- Settings (frame 2c) -------------------------------------------

    def _settings_payload(self):
        groups = [{"key": k, "title": t, "blurb": b}
                  for k, t, b in settings_spec.GROUPS]
        fields = []
        for field in settings_spec.FIELDS:
            raw = self.cfg.get(field.key)
            fields.append({
                "key": field.key,
                "label": field.label,
                "kind": field.kind,
                "group": field.group,
                "hint": field.hint or "",
                "restart": field.restart or False,
                "choices": list(field.choices or ()),
                "value": _settings_display(field, raw),
                "unit": "seconds" if field.key.endswith("_seconds") else "",
            })
        saved = ""
        if self._settings_saved_at:
            saved = time.strftime("%H:%M:%S", time.localtime(self._settings_saved_at))
        return {
            "groups": groups,
            "fields": fields,
            "config_path": CONFIG_FILE,
            "saved_at": saved,
            "obs_footer": self._settings_obs_footer(),
            "updates_footer": self._settings_updates_footer(),
            "appearance": self.appearance(),
        }

    def appearance(self):
        """The four appearance keys, validated against design_v3's menus.

        Sent with every snapshot rather than only at boot so a change applies
        live - the whole point of putting these over tokens is that none of
        them needs a restart. An unknown value (hand-edited config, or a hue
        that was renamed) falls back to the default instead of leaving the
        front end to reason about it.
        """
        def pick(key, menu, fallback):
            value = self.cfg.get(key)
            return value if value in menu else fallback

        return {
            "accent": pick("appearance_accent", dv.ACCENTS, dv.ACCENT_DEFAULT),
            "density": pick("appearance_density", dv.DENSITIES, dv.DENSITY_DEFAULT),
            "radius": pick("appearance_radius", dv.RADII, dv.RADIUS_DEFAULT),
            "motion": pick("appearance_motion", dv.MOTION_MODES, dv.MOTION_DEFAULT),
            "densities": dict(dv.DENSITIES),
            "radii": dict(dv.RADII),
        }

    def _settings_obs_footer(self):
        """Real OBS version / handshake from the last connect."""
        if not self._host or self._host.hero_state() == "disconnected":
            return {"text": "OBS not connected", "can_test": True}
        meta = self._host.obs_meta()
        parts = []
        if meta.get("version"):
            parts.append("OBS %s" % meta["version"])
        ms = meta.get("handshake_ms")
        if ms is not None:
            parts.append("%d ms handshake" % ms)
        text = " · ".join(parts) if parts else "Connected"
        return {"text": text, "can_test": True}

    def _settings_updates_footer(self):
        """Version + what the Updates pane can do right now."""
        from obsauto import updater as updater_mod
        from obsauto.version import version_info

        info = version_info()
        frozen = info["frozen"]
        pending = getattr(self, "_update_pending", None) or {}
        last = getattr(self, "_update_last_message", "") or ""
        if frozen:
            blurb = ("Running Nebula %s (packaged). Check GitHub Releases and "
                     "install over this exe." % info["display"])
        else:
            blurb = ("Running Nebula %s. Pull the latest from GitHub, then "
                     "restart." % info["display"])
        if last:
            blurb = last
        can_install = bool(
            pending.get("status") == "update"
            and pending.get("release", {}).get("asset_url")
            and frozen)
        can_pull = (not frozen) and bool(updater_mod.source_checkout_root())
        return {
            "text": blurb,
            "kind": info["channel"],
            "version": info["release"],
            "display": info["display"],
            "detail": info["detail"],
            "status": pending.get("status") or "",
            "tag": (pending.get("release") or {}).get("tag") or "",
            "can_install": can_install,
            "can_pull": can_pull,
            "busy": bool(getattr(self, "_update_busy", False)),
        }

    def check_for_update(self):
        """Hit GitHub Releases. Safe to call from the UI thread — short timeout."""
        from obsauto import updater as updater_mod

        if self._update_busy:
            return {"ok": False, "error": "busy",
                    "updates_footer": self._settings_updates_footer()}
        self._update_busy = True
        try:
            result = updater_mod.check_for_update(
                token=self.cfg.get("github_token") or None)
            self._update_pending = result
            rel = result.get("release") or {}
            tag = rel.get("tag") or rel.get("version") or "?"
            if result["status"] == "current":
                msg = "You're on the latest (%s)." % result["local"]
            elif result["status"] == "no_asset":
                msg = ("%s is on GitHub but has no .exe asset yet." % tag)
            else:
                msg = "%s is available (you have %s)." % (tag, result["local"])
            self._update_last_message = msg
            self._api_log("[Update] %s" % msg)
            out = {"ok": True, "status": result["status"], "message": msg,
                   "tag": tag}
        except Exception as exc:
            msg = "Update check failed: %s" % exc
            self._update_last_message = msg
            self._api_log("[Update] %s" % msg)
            out = {"ok": False, "error": str(exc), "message": msg}
        finally:
            self._update_busy = False
        out["updates_footer"] = self._settings_updates_footer()
        return out

    def apply_update(self):
        """Download the pending release and replace this packaged build.

        Schedules a helper that waits for us to quit, then swaps the exe and
        relaunches. Source checkouts should call ``pull_source_update`` instead.
        """
        from obsauto import updater as updater_mod

        if self._update_busy:
            return {"ok": False, "error": "busy",
                    "updates_footer": self._settings_updates_footer()}
        if not updater_mod.is_frozen():
            return {"ok": False,
                    "error": "Packaged builds only — use Pull from GitHub.",
                    "updates_footer": self._settings_updates_footer()}
        pending = self._update_pending or {}
        release = pending.get("release") or {}
        if pending.get("status") != "update" or not release.get("asset_url"):
            return {"ok": False, "error": "Nothing to install — check first.",
                    "updates_footer": self._settings_updates_footer()}

        self._update_busy = True
        self._update_last_message = "Downloading %s…" % (
            release.get("asset_name") or "update")
        try:
            dest = updater_mod.default_download_path(release.get("asset_name"))
            path = updater_mod.download_update(
                release["asset_url"], dest,
                token=self.cfg.get("github_token") or None)
            updater_mod.install_and_relaunch(path)
            self._update_last_message = (
                "Installing %s — Nebula will restart." % (
                    release.get("tag") or "update"))
            self._api_log("[Update] %s" % self._update_last_message)
            if self._host:
                threading.Timer(0.4, self._host.quit).start()
            out = {"ok": True, "message": self._update_last_message,
                   "relaunching": True}
        except Exception as exc:
            msg = "Install failed: %s" % exc
            self._update_last_message = msg
            self._api_log("[Update] %s" % msg)
            out = {"ok": False, "error": str(exc), "message": msg}
        finally:
            self._update_busy = False
        out["updates_footer"] = self._settings_updates_footer()
        return out

    def pull_source_update(self):
        """git pull --ff-only for source checkouts."""
        from obsauto import updater as updater_mod

        if self._update_busy:
            return {"ok": False, "error": "busy",
                    "updates_footer": self._settings_updates_footer()}
        if updater_mod.is_frozen():
            return {"ok": False,
                    "error": "Source checkouts only — use Install & relaunch.",
                    "updates_footer": self._settings_updates_footer()}
        self._update_busy = True
        try:
            result = updater_mod.pull_source_update()
            self._update_last_message = result.get("message") or ""
            self._api_log("[Update] %s" % self._update_last_message)
            out = {"ok": bool(result.get("ok")),
                   "message": self._update_last_message,
                   "head": result.get("head") or ""}
        finally:
            self._update_busy = False
        out["updates_footer"] = self._settings_updates_footer()
        return out

    def open_releases_page(self):
        import webbrowser
        pending = self._update_pending or {}
        release = pending.get("release") or {}
        url = (release.get("html_url")
               or "https://github.com/theoriginalcheese/nebula/releases/latest")
        webbrowser.open(url)
        return {"ok": True}

    def hero_action(self, label):
        """Route a hero button press to the host transport layer."""
        if not self._host:
            return {"ok": False, "error": "no host"}
        label = (label or "").strip()
        routes = {
            "Retry now": self._host.autostart,
            "Record anyway": self._host._toggle_record,
            "Pause monitoring": self._host._toggle_monitoring,
            "Stop recording": self._host._toggle_record,
            "Pause": self._host._toggle_pause,
            "Resume": self._host._toggle_pause,
            "Stop & save": self._host._toggle_record,
        }
        fn = routes.get(label)
        if not fn:
            return {"ok": False, "error": "unknown action"}
        self._host.call_soon(fn)
        return {"ok": True}

    def set_setting(self, key, raw):
        """Write on blur. Merge over the live dict; never drop unknown keys."""
        field = settings_spec.BY_KEY.get(key)
        if field is None:
            return {"ok": False, "error": "unknown key"}
        old = self.cfg.get(key)
        if isinstance(raw, str) and field.key.endswith("_seconds"):
            # The field shows "10 s"; strip the unit before parse.
            raw = raw.strip()
            if raw.endswith(" s"):
                raw = raw[:-2].strip()
            elif len(raw) > 1 and raw[-1] in "sS" and raw[:-1].strip().isdigit():
                raw = raw[:-1].strip()
        if field.kind == "bool":
            text = str(raw).strip().lower()
            value = text in ("1", "true", "yes", "on")
            error = None
        else:
            value, error = settings_spec.parse(field, raw)
        if error:
            return {"ok": False, "error": error,
                    "value": _settings_display(field, old)}
        if value == old:
            return {"ok": True, "unchanged": True,
                    "value": _settings_display(field, old)}
        self.cfg[key] = value
        save_config(self.cfg)
        self._settings_saved_at = time.time()
        self._api_log("[Manual] %s = %r" % (key, value))
        # Hotkeys that claim live apply: rebind through the host when we can.
        if (self._host and key in (
                "toggle_hotkey", "toggle_hotkey_scancode",
                "replay_hotkey", "replay_hotkey_scancode",
                "palette_hotkey")):
            try:
                self._host.start_replay()
                self._host.start_hotkeys()
            except Exception as exc:
                self._api_log("[Manual] Couldn't rebind after %s: %s" % (key, exc))
        return {"ok": True, "value": _settings_display(field, value),
                "saved_at": time.strftime("%H:%M:%S",
                                          time.localtime(self._settings_saved_at)),
                "restart": bool(field.restart)}

    # --- 7e: command palette -------------------------------------------

    def _palette_rows(self):
        """Every action the palette can offer, built fresh each open.

        `palette.Row` has no destructive variant *by construction* - the module
        refuses to carry one, because "a delete that is two keystrokes after a
        typo is a trap". So nothing here can add one either; deletion stays in
        the Clips pane behind its own confirm.
        """
        rows = []
        add = rows.append

        for pane in dv.PANES:
            add(palette_mod.Row("Actions", "Go to %s" % dv.PANE_TITLES.get(pane, pane.title()),
                                ("goto", pane), hint="pane"))

        host = self._host
        state = host.tray_status()["state"] if host else "disconnected"
        if state in ("recording", "paused"):
            add(palette_mod.Row("Actions", "Stop recording", ("transport", "record")))
            add(palette_mod.Row("Actions",
                                "Resume recording" if state == "paused" else "Pause recording",
                                ("transport", "pause")))
        elif state == "idle":
            add(palette_mod.Row("Actions", "Record anyway", ("transport", "record")))

        if host and host.replay and host.replay.enabled:
            add(palette_mod.Row("Actions",
                                "Save the last %ds" % host.replay.seconds,
                                ("replay", "save")))
            add(palette_mod.Row("Actions",
                                "Disarm the buffer" if host.replay.armed
                                else "Arm the buffer",
                                ("replay", "arm")))

        # 2k. The overlay refuses to open while idle ("never while idle"), so
        # only offer it when it would actually appear - a palette row that
        # answers with a log line and nothing on screen reads as broken.
        # v3 had this row; v4 built the whole overlay layer and then wired
        # nothing to show_mini(), which left 2k unreachable in the shipped app.
        if state in ("recording", "paused"):
            add(palette_mod.Row("Actions", "Show the mini overlay",
                                ("overlay", "show"), hint="overlay"))

        add(palette_mod.Row("Actions", "Open recording folder", ("open", "recordings")))
        add(palette_mod.Row("Settings", "Open config.json", ("open", "config")))

        # Real games from the classifier - recency so recent ones rank first.
        try:
            snap = self._classifier.snapshot()
            for name in sorted(snap.get("games") or {}):
                add(palette_mod.Row("Games", name, ("game", name),
                                    hint="per-game profile"))
        except Exception:
            pass
        return rows

    def palette_search(self, query=""):
        """Filter/rank/group - all of it palette.py's, none of it ours."""
        rows = self._palette_rows()
        grouped = palette_mod.search(rows, query or "")
        out = []
        for group, items in grouped:
            out.append({
                "group": group,
                "rows": [{"label": r.label, "hint": r.hint,
                          "spans": list(r.spans or ()),
                          "action": list(r.action)} for r in items],
            })
        return {"groups": out, "total": palette_mod.count_all(rows, query or "")}

    def palette_run(self, action):
        """Execute one row. `action` is the [kind, arg] the row carried."""
        try:
            kind, arg = action[0], action[1]
        except (TypeError, IndexError):
            return {"ok": False, "error": "malformed action"}

        host = self._host
        if kind == "goto":
            self._goto_pane = arg
            return {"ok": True, "goto": arg}
        if kind == "transport" and host:
            (host._toggle_record if arg == "record" else host._toggle_pause)()
            return {"ok": True}
        if kind == "replay" and host:
            (host._save_replay if arg == "save" else host.toggle_replay_arm)()
            return {"ok": True}
        if kind == "open":
            (self.open_recording_root if arg == "recordings" else self.reveal_config)()
            return {"ok": True}
        if kind == "overlay" and host:
            (host.show_mini if arg == "show" else host.hide_mini)()
            return {"ok": True}
        if kind == "game":
            self._goto_pane = "games"
            return {"ok": True, "goto": "games", "select": arg}
        return {"ok": False, "error": "unknown action %r" % kind}

    # --- 7d: per-game profiles ------------------------------------------

    def profile_get(self, basename):
        """The saved profile for a game, plus what it would mean in practice."""
        try:
            prof = profiles_mod.for_game(self._classifier, basename) or {}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "basename": basename, "profile": prof,
                "summary": profiles_mod.summary(prof) if prof else "",
                "gb_per_hour": profiles_mod.estimated_gb_per_hour(
                    prof.get("bitrate_kbps")) if prof.get("bitrate_kbps") else None}

    def profile_save(self, basename, raw):
        """Sanitise then save. The scope guard in profiles.py runs on write."""
        try:
            clean = profiles_mod.sanitise(raw or {})
            profiles_mod.save(self._classifier, basename, clean)
        except Exception as exc:
            self._api_log("[Profiles] Save failed for %s: %s" % (basename, exc))
            return {"ok": False, "error": str(exc)}
        self._api_log("[Profiles] Saved profile for %s." % basename)
        return {"ok": True, "profile": clean,
                "summary": profiles_mod.summary(clean)}

    def reveal_config(self):
        path = CONFIG_FILE
        try:
            if os.path.isfile(path):
                subprocess_reveal(path)
            else:
                subprocess_reveal(os.path.dirname(path) or ".")
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def consume_goto_pane(self):
        """One-shot pane switch. Two sources, in-memory first.

        The palette sets `_goto_pane` when a "Go to" row runs; tools/shoot.py
        writes shots/goto_pane.txt. Both are one-shot: read once, then cleared,
        so a switch never repeats on the next poll.
        """
        pending, self._goto_pane = self._goto_pane, None
        if pending:
            return {"pane": pending}

        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "shots", "goto_pane.txt")
        if getattr(sys, "frozen", False):
            return {"pane": None}
        if not os.path.isfile(path):
            return {"pane": None}
        try:
            with open(path, "r", encoding="utf-8") as f:
                pane = f.read().strip().lower()
            os.remove(path)
        except OSError:
            return {"pane": None}
        if pane in ("dashboard", "clips", "games", "macropad", "settings"):
            return {"pane": pane}
        return {"pane": None}

    def open_recording_root(self):
        root = self.cfg.get("recording_root") or ""
        if not root or not os.path.isdir(root):
            return {"ok": False, "error": "recording root missing"}
        try:
            subprocess_reveal(root)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def refresh_clips(self):
        """Force a rescan of recording_root (frame 2b Refresh)."""
        self._clips_scanned_at = 0.0
        self._ensure_clips_scan(force=True)
        return {"ok": True}

    def reveal_clip(self, path):
        path = os.path.normpath(path or "")
        if not path or not os.path.isfile(path):
            return {"ok": False, "error": "clip not found"}
        try:
            subprocess_reveal(path)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def delete_clip(self, path, confirm=False):
        """Manual delete — same offload guard as gui.py / test_clips.py."""
        path = os.path.normpath(path or "")
        clip = None
        for c in self._clips_cache or []:
            if c["path"] == path:
                clip = c
                break
        if clip is None:
            return {"ok": False, "error": "clip not found"}

        pending = set()
        offloader = None
        if self._host and getattr(self._host, "monitor", None):
            offloader = self._host.monitor.offloader
        if offloader and offloader.enabled:
            try:
                pending = offloader.pending_paths()
            except Exception:
                pending = set()
        if path in pending:
            return {
                "ok": False,
                "refused": True,
                "message": (
                    "%s hasn't been copied to the NAS and verified yet.\n\n"
                    "Nebula won't delete a clip that has no second copy. It'll be "
                    "safe to remove once the offload queue has drained."
                ) % clip["name"],
            }
        if not confirm:
            return {
                "ok": False,
                "need_confirm": True,
                "rel": clip["rel"],
                "size_label": _format_bytes(clip["size"]),
            }
        try:
            os.remove(path)
        except OSError as exc:
            self._api_log("[Manual] Couldn't delete %s: %s" % (clip["name"], exc))
            return {"ok": False, "error": str(exc)}
        root = self.cfg.get("recording_root") or ""
        thumbs.purge(root, path)
        self._clip_durations.pop(path, None)
        self._thumb_data_cache.pop(path, None)
        if self._clips_cache is not None:
            self._clips_cache = [c for c in self._clips_cache if c["path"] != path]
        self._api_log("[Manual] Deleted %s" % clip["rel"])
        return {"ok": True}

    # --- Games (frame 2d) ----------------------------------------------

    def _games(self):
        snap = self._classifier.snapshot()
        games_raw, non_raw = snap.get("games", {}), snap.get("non_games", {})
        by_name = {}
        for key, value in games_raw.items():
            if isinstance(value, dict):
                name = value.get("display_name") or key
                source = value.get("source", "")
                appid = value.get("appid") or value.get("steam_appid") or ""
            else:
                name, source, appid = key, "", ""
            entry = by_name.setdefault(name, {"exes": [], "source": source,
                                              "appid": str(appid or "")})
            entry["exes"].append(key)
            if not entry["appid"] and appid:
                entry["appid"] = str(appid)

        games = []
        for name in sorted(by_name, key=str.lower):
            e = by_name[name]
            games.append({
                "name": name,
                "exes": e["exes"],
                "meta": e["appid"] or e["source"] or e["exes"][0],
                "icon": app_icons.data_url(e["exes"][0], name),
            })

        keep = {p.lower() for p in self.cfg.get("keep_alive_audio_processes", [])}
        non_games = []
        for basename in sorted(non_raw, key=str.lower):
            non_games.append({
                "name": basename,
                "meta": "keep-alive" if basename.lower() in keep else "",
                "icon": app_icons.data_url(basename, basename),
            })

        pending = []
        with self._classifier._lock:
            for key, (basenames, suggested) in self._classifier._pending_manual.items():
                pending.append({
                    "key": key,
                    "name": suggested or key,
                    "basenames": list(basenames),
                    "sub": "%s · awaiting classification" % (
                        ", ".join(basenames[:3]) + (
                            " +%d" % (len(basenames) - 3) if len(basenames) > 3 else "")
                    ),
                })

        synced = bool(self.cfg.get("github_gamedata_repo") and
                      self.cfg.get("github_token"))
        return {
            "pending": pending,
            "games": games,
            "non_games": non_games,
            "foot_games": (
                "Stored in games.json · shared via GitHub" if synced
                else "Stored in games.json · this machine only"),
            "foot_non": "Right-click a row to move it back to Games.",
        }

    def classify_pending(self, key, is_game):
        key = (key or "").strip()
        with self._classifier._lock:
            item = self._classifier._pending_manual.pop(key, None)
        if not item:
            return {"ok": False, "error": "nothing pending under that key"}
        basenames, suggested = item
        name = suggested or (basenames[0] if basenames else key)
        self._classifier.resolve_review(basenames, bool(is_game),
                                        display_name=name)
        self._classifier.finish_review(key)
        return {"ok": True, "games": self._games()}

    def promote_non_game(self, basename):
        basename = (basename or "").strip().lower()
        if not basename:
            return {"ok": False, "error": "empty"}
        display = os.path.splitext(basename)[0]
        self._classifier.mark_game(basename, display, source="manual")
        return {"ok": True, "games": self._games()}

    def demote_game(self, basename):
        basename = (basename or "").strip().lower()
        if not basename:
            return {"ok": False, "error": "empty"}
        self._classifier.mark_non_game(basename)
        return {"ok": True, "games": self._games()}

    def rescan_steam(self):
        """Kick a Steam rescan on a worker. Returns immediately."""
        def work():
            try:
                self._classifier.refresh_steam_index()
                self._classifier.register_all_steam_games()
            except Exception as exc:
                self._api_log("[Steam] Rescan failed: %s" % exc)
        threading.Thread(target=work, daemon=True).start()
        return {"ok": True, "started": True}

    def _ribbon(self):
        """7b, as a fraction of the day. The block geometry is the only thing
        computed here; the spans themselves are session_log's."""
        now = time.time()
        start = session_log.day_start()
        day = 86400.0
        spans = [s for s in session_log.spans() if (s["end"] or now) >= start]
        # Same trap as _obs(): a span's `live` flag means "no rec_stop was
        # seen", which an abandoned span satisfies forever. Painting the ember
        # pulse from it made the ribbon glow for a recording that had already
        # been killed. Nothing is live until step 2 can ask OBS.
        recording = self._host and self._host.tray_status()["state"] == "recording"
        blocks = []
        for s in spans:
            a = max(s["start"], start)
            b = min(s["end"] or now, start + day)
            if b <= a:
                continue
            blocks.append({"game": s["game"],
                           "live": bool(recording and s is spans[-1]),
                           "duration_s": b - a,
                           # Clock labels, so a span can say when it was
                           # without the reader converting a percentage of a
                           # day back into a time in their head.
                           "start_label": time.strftime("%H:%M", time.localtime(a)),
                           "end_label": time.strftime("%H:%M", time.localtime(b)),
                           "start_pct": (a - start) / day,
                           "width_pct": (b - a) / day})
        total = sum(b["duration_s"] for b in blocks)

        # What was actually recorded, biggest first. The bar shows *when*; this
        # is the part that answers *what*, which previously lived only in a
        # native tooltip one span at a time.
        per_game = {}
        for b in blocks:
            name = b["game"] or "unknown"
            row = per_game.setdefault(name, {"game": name, "seconds": 0.0, "count": 0})
            row["seconds"] += b["duration_s"]
            row["count"] += 1
        by_game = sorted(per_game.values(), key=lambda r: -r["seconds"])

        axis = ["00:00", "06:00", "12:00", "18:00", "24:00"]
        return {"spans": blocks, "total_s": total, "axis": axis,
                "by_game": by_game,
                # Where "now" is in the day, so the empty half of the track
                # reads as "not yet" rather than "nothing happened".
                "now_pct": max(0.0, min(1.0, (now - start) / day)),
                "hour_marks": [h / 24.0 for h in range(3, 24, 3)]}

    CLIP_LIST_CAP = 400

    def _ensure_clips_scan(self, force=False):
        """Background scan — never block snapshot()."""
        if self._clips_scan_busy:
            return
        age = time.time() - self._clips_scanned_at
        if not force and self._clips_cache is not None and age < 30:
            return
        self._clips_scan_busy = True

        def worker():
            try:
                self._scan_clips()
            finally:
                self._clips_scan_busy = False
                self._clips_scanned_at = time.time()

        threading.Thread(target=worker, daemon=True).start()

    def _scan_clips(self):
        root = self.cfg.get("recording_root") or ""
        clips, error = [], None
        try:
            if root and os.path.isdir(root):
                for game in sorted(os.listdir(root)):
                    folder = os.path.join(root, game)
                    if not os.path.isdir(folder):
                        continue
                    with os.scandir(folder) as inner:
                        for f in inner:
                            if not (f.is_file()
                                    and f.name.lower().endswith(VIDEO_EXT)):
                                continue
                            st = f.stat()
                            clips.append({
                                "game": game,
                                "name": f.name,
                                "path": f.path,
                                "rel": "%s/%s" % (game, f.name),
                                "size": st.st_size,
                                "mtime": st.st_mtime,
                            })
        except Exception as exc:
            error = exc
        self._clips_cache = clips
        self._clips_error = error
        self._clips_root = root
        self._queue_thumb_work(clips, root)

    def _queue_thumb_work(self, clips, root_dir):
        """Single-flight backfill for Length + thumbnails (7f)."""
        if not thumbs.available() or not clips:
            return
        if self._thumb_scan_busy:
            return
        self._thumb_scan_busy = True
        newest = sorted(clips, key=lambda c: -c["mtime"])[:40]

        def worker():
            try:
                for clip in newest:
                    path = clip["path"]
                    if path not in self._clip_durations:
                        seconds = thumbs.duration_of(path)
                        if seconds:
                            self._clip_durations[path] = seconds
                    if not thumbs.have_frames(root_dir, path):
                        dur = self._clip_durations.get(path)
                        thumbs.extract(root_dir, path, duration=dur)
            finally:
                self._thumb_scan_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _clips_panel(self):
        self._ensure_clips_scan()
        min_clip = int(self.cfg.get("min_clip_seconds") or 10)
        note = (
            "Clips under min_clip_seconds (%ds) are deleted automatically "
            "and never listed here." % min_clip)
        root = self._clips_root or self.cfg.get("recording_root") or ""
        if self._clips_cache is None:
            return {
                "scanning": True,
                "root": root,
                "error": None,
                "clips": [],
                "games": [],
                "summary": {"count": 0, "total_bytes": 0, "total_label": ""},
                "min_clip_note": note,
                "ffmpeg": thumbs.available(),
            }
        if self._clips_error is not None:
            return {
                "scanning": False,
                "root": root,
                "error": str(self._clips_error),
                "clips": [],
                "games": [],
                "summary": {"count": 0, "total_bytes": 0, "total_label": ""},
                "min_clip_note": note,
                "ffmpeg": thumbs.available(),
            }

        clips = []
        for raw in self._clips_cache:
            path = raw["path"]
            thumb = self._thumb_data_url(root, path)
            seconds = self._clip_durations.get(path)
            clips.append({
                "path": path,
                "rel": raw["rel"],
                "game": raw["game"],
                "name": raw["name"],
                "title": os.path.splitext(raw["name"])[0],
                "size_bytes": raw["size"],
                "size_label": _format_bytes(raw["size"]),
                "mtime": raw["mtime"],
                "recorded": _recorded_label(raw["mtime"]),
                "length": _length_label(seconds),
                "initials": _initials(raw["game"]),
                "thumb": thumb,
            })

        counts = {}
        for c in self._clips_cache:
            counts[c["game"]] = counts.get(c["game"], 0) + 1
        games = [{"key": "", "name": "All clips", "count": len(self._clips_cache)}]
        for game, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower())):
            games.append({"key": game, "name": game, "count": n})

        total = sum(c["size"] for c in self._clips_cache)
        return {
            "scanning": False,
            "root": root,
            "error": None,
            "clips": clips,
            "games": games,
            "summary": {
                "count": len(self._clips_cache),
                "total_bytes": total,
                "total_label": _format_bytes(total),
            },
            "min_clip_note": note,
            "ffmpeg": thumbs.available(),
            "capped": len(self._clips_cache) > self.CLIP_LIST_CAP,
            "cap": self.CLIP_LIST_CAP,
        }

    def _thumb_data_url(self, root, clip_path):
        """WebView2 blocks cross-path file:// loads — inline the frame instead."""
        clip_path = os.path.normpath(clip_path)
        cached = self._thumb_data_cache.get(clip_path)
        if cached is not None:
            return cached
        if not root or not thumbs.have_frames(root, clip_path):
            return ""
        frame = thumbs.frame_paths(root, clip_path)[thumbs.DEFAULT_FRAME]
        if not os.path.isfile(frame):
            return ""
        try:
            with open(frame, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
        except OSError:
            return ""
        url = "data:image/webp;base64," + data
        self._thumb_data_cache[clip_path] = url
        return url

    def _forecast(self):
        root = self.cfg.get("recording_root") or "C:/"
        drive = os.path.splitdrive(os.path.abspath(root))[0] + os.sep
        try:
            usage = psutil.disk_usage(drive)
        except OSError:
            return {"label": "drive unavailable", "rate": drive, "used_pct": 0}
        f = forecast_mod.forecast(usage.free, usage.total)
        # `ready` is False until three days of activity. The spec shows a
        # distinct state for that rather than a first-day guess, so honour it.
        if f["ready"]:
            label = forecast_mod.days_left_label(f["days_left"]) + " left"
            rate = "%.1f GB free · %.1f GB/h" % (usage.free / 1073741824.0, f["gb_per_hour"])
        else:
            label = "Not enough history"
            need = f["days_needed"]
            rate = "%.1f GB free · %d more day%s" % (
                usage.free / 1073741824.0, need, "" if need == 1 else "s")
        return {"label": label, "rate": rate,
                "used_pct": usage.used / float(usage.total or 1)}


def _settings_display(field, value):
    if field.kind == "bool":
        return "on" if value else "off"
    rendered = settings_spec.render(field, value)
    if field.key.endswith("_seconds") and rendered != "":
        return "%s s" % rendered
    return rendered


def _split_log_tag(message):
    """'[OBS] Recording started' -> ('OBS', 'Recording started')."""
    message = (message or "").strip()
    if message.startswith("[") and "]" in message:
        tag, _, rest = message[1:].partition("]")
        return tag.strip(), rest.strip()
    return "", message


def _tail_log_file(n=80):
    """Fallback when the host buffer is empty (fresh process, no tray events)."""
    path = LOG_FILE
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.rstrip("\n")
        # Formatter: "%Y-%m-%d %H:%M:%S message"
        ts = time.time()
        msg = line
        if len(line) >= 19 and line[4] == "-" and line[10] == " ":
            try:
                ts = time.mktime(time.strptime(line[:19], "%Y-%m-%d %H:%M:%S"))
                msg = line[20:]
            except ValueError:
                pass
        out.append((ts, msg))
    return out


def subprocess_reveal(path):
    """Explorer select-if-file / open-if-dir, without blocking the UI thread."""
    import subprocess
    path = os.path.normpath(path)
    if os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", path])
    else:
        subprocess.Popen(["explorer", path])


def _format_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.0f %s" % (n, unit) if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f GB" % n


def _initials(name):
    words = [w for w in re.split(r"[\s_\-]+", name or "") if w]
    return ("".join(w[0] for w in words[:2]) or (name or "")[:2]).upper()


def _recorded_label(mtime):
    now = time.time()
    delta = now - mtime
    if delta < 3600:
        return "%d min ago" % max(1, int(delta // 60))
    today = time.localtime(now)
    when = time.localtime(mtime)
    if (when.tm_year, when.tm_yday) == (today.tm_year, today.tm_yday):
        return time.strftime("Today %H:%M", when)
    if delta < 86400 * 2:
        return "Yesterday"
    if delta < 86400 * 7:
        return time.strftime("%a", when)
    return time.strftime("%d %b", when)


def _length_label(seconds):
    if not seconds:
        return ""
    hours, rem = divmod(int(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


def _hm(seconds):
    seconds = int(seconds)
    h, m = seconds // 3600, (seconds % 3600) // 60
    return "%dh %02dm" % (h, m) if h else "%dm" % m


def _ago(seconds):
    seconds = int(seconds)
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    if seconds < 86400:
        return "%dh" % (seconds // 3600)
    return "%dd" % (seconds // 86400)


def _set_dpi_awareness():
    """Per-monitor-v2 if the OS has it, else v1, else the ancient system flag.

    Returns the level that took, for the log - "which awareness am I actually
    running at" is the first question worth asking when a window misbehaves
    across monitors, and it is otherwise invisible.
    """
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2. Win10 1703+.
        # The context is a HANDLE, so -4 has to be pointer-sized: passing a
        # bare Python int marshals as 32-bit and the call just fails, silently
        # dropping us to v1.
        fn = ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_bool
        if fn(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor-v1"
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"
    except Exception:
        return "none"


def main():
    # Per-monitor DPI aware, so 1280x808 is 1280x808 of design units on a 150%
    # panel rather than a blurry upscale.
    #
    # v2 where it exists, not just shcore's v1. Under v1 Windows sends
    # WM_DPICHANGED when the window crosses onto a different-DPI monitor and
    # expects the *app* to resize itself; WinForms here does not, so dragging
    # from the 150% screen to a 100% one left a 1898px-wide window that is
    # 1898 logical px there - "it goes huge". v2 additionally scales the
    # non-client area and notifies child windows. The resize is still ours to
    # do; see NebulaHost.start_window_watch.
    #
    # Must run before any window exists: the first awareness call in a process
    # wins, and pywebview calls the old SetProcessDPIAware() when it builds the
    # master window.
    dpi_level = _set_dpi_awareness()

    # Before anything else: log_to_file() is a silent no-op until this runs,
    # and v4 inherits v3's real deployment - pythonw, no console, so a
    # traceback that does not reach the file reaches nobody.
    setup_logging()

    dev = "--dev" in sys.argv
    if not dev and not host_mod.claim_single_instance():
        # Same mutex name main.py uses, on purpose - see host.py. Two Nebulas
        # fight over OBS, over the global hotkey, and over APP_DIR's data.
        log_to_file("[App] Another Nebula is already running - exiting.")
        print("Another Nebula is already running. Use --dev to run anyway.")
        return 1

    api = Api()
    host = host_mod.NebulaHost(api.cfg)
    host.attach_backend(api._classifier)
    api._host = host

    # 2j: start hidden. Nebula is a tray app; the window is a thing you open,
    # not the thing that is running. `--show` is for development.
    start_hidden = "--show" not in sys.argv

    # ?nowind=1 / ?nosheet=1 / ?hud=1 - measurement switches, see app.css.
    url_args = next((x[6:] for x in sys.argv if x.startswith("--url=")), "")
    index = INDEX + ("?" + url_args if url_args else "")

    window = webview.create_window(
        "Nebula",
        index,
        js_api=api,
        width=dv.WIDTH,
        height=dv.HEIGHT,
        min_size=(dv.MIN_WIDTH, dv.MIN_HEIGHT),
        frameless=True,          # the v3 titlebar is ours, drawn in HTML
        easy_drag=False,         # .pywebview-drag-region handles it instead
        background_color="#0A0812",
        resizable=True,
        hidden=start_hidden,
    )
    api._window = window
    host.attach(window)
    host._visible = not start_hidden

    def _boot():
        host.start_tray()
        host.start_taskbar_icon()
        host.start_replay()
        host.start_hotkeys()
        host.start_window_watch()
        host.start_poll()
        host.autostart()
        # --toast-demo: fire real toast events through the real pipeline
        # (host._on_notify -> NebulaWindows.toast_replace), so 2i can be looked
        # at without OBS. Monitor is the only other thing that emits these, and
        # it cannot when obs-websocket is unreachable. Demo only: it changes
        # nothing and records nothing.
        if "--toast-demo" in sys.argv:
            def demo():
                for delay, event in ((3.0, "start"), (9.0, "pause"),
                                     (15.0, "stop"), (21.0, "error")):
                    threading.Timer(
                        delay, host._on_notify, (event, "Honkai Star rail")
                    ).start()
            demo()
        if start_hidden:
            # Page may not be ready on the first watcher tick; nudge asleep once
            # the bridge is likely up so we do not composite blur while hidden.
            threading.Timer(2.0, lambda: host._sleep(False)).start()
        host._log("[App] DPI awareness: %s" % dpi_level)
        host._log("[App] v4 spike up. Tray %s, %d hotkey(s) bound, %d deferred."
                  % ("running" if host._tray else "failed",
                     len(host.hotkeys.bound()), len(host.hotkeys.pending())))

    # gui=None lets pywebview pick; on Windows that is EdgeChromium (WebView2),
    # which is the runtime Tauri would also use. Measuring this measures both.
    webview.start(_boot, debug="--debug" in sys.argv)
    host.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
