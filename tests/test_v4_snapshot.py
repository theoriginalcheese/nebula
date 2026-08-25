"""v4 snapshot must not isdir() NAS/SMB on the JS-bridge thread.

    python tests/test_v4_snapshot.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.clip_catalog import ClipCatalog
from spike.app import Api

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


def _stub_api(app_dir, recording_root):
    api = Api.__new__(Api)
    api.cfg = {
        "min_clip_seconds": 10,
        "recording_root": recording_root,
        "nas_offload_root": "Z:/OBS",
        "nas_offload_root_lan": r"\\192.168.68.59\50tb\OBS",
        "nas_offload_root_remote": r"\\100.84.207.58\50tb\OBS",
    }
    api._host = None
    api._clips_error = None
    api._clips_root = recording_root
    api._clips_backfill_busy = False
    api._clip_durations = {}
    api._thumb_data_cache = {}
    api._clips_cache = [{
        "game": "G", "name": "a.mkv", "path": "", "rel": "G/a.mkv",
        "size": 1, "mtime": 1.0, "location": "remote",
        "availability": "online", "nas_path": r"\\nas\share\G\a.mkv",
    }]
    api._clip_catalog = ClipCatalog(api.cfg, app_dir=app_dir)
    api._seed_clips_from_index = lambda: None
    api._ensure_clips_scan = lambda force=False: None
    api._offloader = lambda: None
    api._api_log = lambda m: None
    return api


def test_clips_panel_skips_nas_isdir():
    work = tempfile.mkdtemp(prefix="nebula-snap-")
    api = _stub_api(work, os.path.join(work, "rec"))

    api._clip_catalog.upsert(
        game="G", name="a.mkv", size=1, mtime=1.0,
        nas_path=r"\\nas\share\G\a.mkv",
    )

    def boom(*_a, **_k):
        raise AssertionError("NAS probe on snapshot thread")

    api._clip_catalog.resolve_active_root = boom
    api._clip_catalog.nas_reachable = boom
    api._clip_catalog.nas_online = boom

    t0 = time.time()
    panel = api._clips_panel()
    dt = time.time() - t0
    check("clips panel returns", isinstance(panel.get("clips"), list))
    check("clips panel is fast", dt < 1.0, "%.3fs" % dt)
    check("remote row restamped offline from cache",
          panel["clips"] and panel["clips"][0]["availability"] == "offline",
          panel["clips"][:1] if panel.get("clips") else None)


def test_snapshot_isolates_section_faults():
    work = tempfile.mkdtemp(prefix="nebula-snap-")
    api = _stub_api(work, os.path.join(work, "rec"))
    api.seed = 1
    api._classifier = type("C", (), {
        "snapshot": lambda self: {"games": {}, "non_games": {}},
        "_lock": __import__("threading").Lock(),
        "_pending_manual": {},
    })()
    api._log_filter = "All"
    api._settings_saved_at = None
    api._moonlight_proc = None

    def boom():
        raise RuntimeError("clips hung")

    logs = []
    api._api_log = logs.append
    api._clips_panel = boom
    api._hero = lambda: {
        "state": "disconnected", "eyebrow": "OBS disconnected",
        "tint": "", "title": "Can't reach OBS", "source": "", "hint": "",
        "show_readouts": False, "elapsed": "", "size": "", "bitrate": "",
        "scene": "", "video": "", "preview_seq": 0, "actions": [],
        "actions_enabled": []}
    api._obs = lambda: {"connected": False, "live": False,
                        "label": "Not connected · no sessions logged",
                        "state": "disconnected"}
    api._tiles = lambda: []
    api._activity = lambda: {"rows": [], "tags": ["All"], "filter": "All"}
    api._ribbon = lambda: {
        "spans": [], "total_s": 0,
        "axis": ["00:00", "06:00", "12:00", "18:00", "24:00"],
        "by_game": [], "now_pct": 0, "hour_marks": []}
    api._forecast = lambda: {"label": "Not enough history",
                             "rate": "10.0 GB free · 3 more days",
                             "used_pct": 0.1}
    api._games = lambda: {"pending": [], "games": [], "non_games": [],
                          "foot_games": "", "foot_non": ""}
    api._settings_payload = lambda: {
        "groups": [], "fields": [], "saved_at": None,
        "config_path": "", "appearance": {}}
    api.appearance = lambda: {}
    api._macropad = lambda: {"empty": True, "title": "", "body": "", "foot": ""}
    api._remote = lambda: {"moonlight": {}, "tailscale": {}, "blurb": ""}

    snap = api.snapshot()
    check("forecast survives clips fault",
          snap["forecast"]["label"] == "Not enough history")
    check("conn label survives clips fault",
          "Not connected" in snap["obs"]["label"])
    check("clips fallback is empty not missing",
          snap["clips_panel"]["clips"] == [])
    check("snapshot faults stay out of Activity", logs == [], logs)


def test_hero_survives_host_without_preview():
    work = tempfile.mkdtemp(prefix="nebula-hero-")
    api = _stub_api(work, os.path.join(work, "rec"))
    api.cfg["idle_timeout_seconds"] = 4
    api.cfg["reconnect_interval_seconds"] = 10

    class Host:
        def hero_state(self):
            return "idle"

        def tray_status(self):
            return {"state": "idle", "heading": "Watching for a game",
                    "detail": "No game in focus"}

        def hero_readouts(self):
            return {"elapsed": "", "size": "", "bitrate": ""}

        def obs_meta(self):
            return {"scene": "", "video_label": ""}

        def pause_reason(self):
            return None

    api._host = Host()
    hero = api._hero()
    check("hero does not raise without preview", hero["state"] == "idle")
    check("hero is not disconnected fallback",
          hero["title"] != "Can't reach OBS", hero.get("title"))
    check("preview seq is zero", hero["preview_seq"] == 0)

    class Connecting:
        def hero_state(self):
            return "disconnected"

        def tray_status(self):
            return {"state": "disconnected", "heading": "Looking for OBS",
                    "detail": "localhost:4455"}

        def hero_readouts(self):
            return {"elapsed": "", "size": "", "bitrate": ""}

        def obs_meta(self):
            return {"scene": "", "video_label": ""}

        def pause_reason(self):
            return None

        def is_connecting(self):
            return True

    api._host = Connecting()
    looking = api._hero()
    check("connecting hero is looking", looking["title"] == "Looking for OBS",
          looking.get("title"))
    check("connecting flag is set", looking.get("connecting") is True)
    check("connecting is not the ember failure copy",
          "Can't reach OBS" not in (looking.get("title") or ""))


def test_start_menu_shortcut_is_not_dev():
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    from install_nebula_shortcut import shortcut_args
    args = shortcut_args(r"C:\nebula\spike\app.py", show=True)
    check("everyday shortcut has --show", "--show" in args)
    check("everyday shortcut has no --dev", "--dev" not in args)
    dev = shortcut_args(r"C:\nebula\spike\app.py", show=True, dev=True)
    check("explicit dev still available", "--dev" in dev and "--show" in dev)


if __name__ == "__main__":
    test_clips_panel_skips_nas_isdir()
    test_snapshot_isolates_section_faults()
    test_hero_survives_host_without_preview()
    test_start_menu_shortcut_is_not_dev()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
    print("ALL PASS")
