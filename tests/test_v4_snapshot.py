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


def test_nas_backfill_resolves_root_off_the_bridge():
    """_ensure_clips_scan runs inside snapshot(); scheduling the NAS walk used
    to resolve the root there - tailscale CLI plus up to seven timed isdirs."""
    import threading
    work = tempfile.mkdtemp(prefix="nebula-backfill-")
    api = _stub_api(work, os.path.join(work, "rec"))
    api._clips_backfill_at = 0.0
    bridge = threading.current_thread()
    resolved_on, walked = [], threading.Event()

    def resolve():
        resolved_on.append(threading.current_thread())
        time.sleep(0.5)
        return "Z:/OBS"

    api._resolved_nas_root = resolve
    api._clip_catalog.backfill_from_nas = (
        lambda root: walked.set() or {"ok": True, "added": 0})

    t0 = time.perf_counter()
    api._schedule_nas_backfill(force=False)
    dt = time.perf_counter() - t0
    check("backfill scheduling does not wait on the NAS", dt < 0.1, "%.3fs" % dt)
    check("backfill marked busy at once", api._clips_backfill_busy is True)
    walked.wait(3)
    check("backfill walk still runs", walked.is_set())
    check("root resolved on the worker",
          resolved_on and resolved_on[0] is not bridge, resolved_on)
    deadline = time.time() + 2
    while time.time() < deadline and api._clips_backfill_busy:
        time.sleep(0.01)
    check("backfill clears busy and stamps", not api._clips_backfill_busy
          and api._clips_backfill_at > 0)

    api._clips_backfill_at = 0.0
    for key in ("nas_offload_root", "nas_offload_root_lan",
                "nas_offload_root_remote"):
        api.cfg[key] = ""
    resolved_on.clear()
    api._schedule_nas_backfill(force=True)
    check("no NAS configured spawns nothing",
          not api._clips_backfill_busy and not resolved_on)


def test_clip_clicks_never_resolve_the_nas_root():
    """Reveal / Open / Delete run on the JS bridge. Resolving the root there
    shelled out to tailscale and timed-isdir'd every share - a click froze
    the window for seconds whenever the NAS or the tailnet was down."""
    from spike import app as app_mod

    work = tempfile.mkdtemp(prefix="nebula-click-")
    rec = os.path.join(work, "rec")
    clip_path = os.path.join(rec, "G", "b.mkv")
    os.makedirs(os.path.dirname(clip_path))
    with open(clip_path, "wb") as f:
        f.write(b"x" * 64)
    api = _stub_api(work, rec)
    api._open_clip_busy = set()
    api._clips_cache = [{
        "game": "G", "name": "b.mkv", "path": os.path.normpath(clip_path),
        "rel": "G/b.mkv", "size": 64, "mtime": 1.0, "location": "local",
        "availability": "online", "nas_path": "",
    }]

    class Offloader:
        enabled = True

        @property
        def root(self):
            raise AssertionError("live NAS root resolved on the bridge")

        def cached_root(self):
            return "Z:/OBS"

        def pending_paths(self):
            return set()

    api._offloader = lambda: Offloader()

    def boom(*_a, **_k):
        raise AssertionError("NAS probe on the bridge")

    api._clip_catalog.resolve_active_root = boom
    asked = []
    api._clip_catalog.resolve_nas_path = (
        lambda rel, root=None: asked.append(root) or None)
    opened = []
    real_reveal, real_open = app_mod.subprocess_reveal, app_mod.subprocess_open
    app_mod.subprocess_reveal = opened.append
    app_mod.subprocess_open = opened.append
    try:
        res = api.reveal_clip(clip_path)
        check("reveal local: no live lookup", res.get("ok") is True
              and res.get("where") == "local", res)
        res = api.open_clip("G/b.mkv")
        check("open local: no live lookup", res.get("ok") is True
              and res.get("started") is False, res)
        check("  ...still opens the local file",
              opened == [os.path.normpath(clip_path)] * 2, opened)
        res = api.delete_clip(clip_path, confirm=True)
        check("delete: no live lookup, same refusal",
              res.get("refused") is True
              and "no NAS copy is recorded" in res.get("message", ""), res)
        check("  ...NAS path asked against the cached root",
              asked == ["Z:/OBS"], asked)
        check("  ...local file untouched", os.path.exists(clip_path))

        api._clips_cache[0].update(location="remote", path="")
        os.remove(clip_path)
        asked.clear()
        api._nas_root_seen = r"\\192.168.68.59\50tb\OBS"
        api._clip_catalog.nas_online = lambda root=None, **_k: False
        res = api.reveal_clip("G/b.mkv")
        check("reveal remote, NAS down: same message",
              res.get("ok") is False and "isn't reachable" in res.get("error", ""),
              res)
        check("  ...uses the root a worker last resolved",
              asked == [r"\\192.168.68.59\50tb\OBS"], asked)
    finally:
        app_mod.subprocess_reveal, app_mod.subprocess_open = real_reveal, real_open


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


def test_set_setting_never_logs_secrets():
    """The activity log is nebula.log on disk; a password or token must not
    land in it when the user edits the field in Settings."""
    import spike.app as app_module
    work = tempfile.mkdtemp(prefix="nebula-snap-")
    api = _stub_api(work, os.path.join(work, "rec"))
    api._gamesync = None
    api._settings_saved_at = None
    logs = []
    api._api_log = logs.append
    saved = []
    real_save = app_module.save_config
    app_module.save_config = lambda cfg, *a, **k: saved.append(dict(cfg))
    try:
        secret = "hunter2-very-secret-9f8e7d"
        out = api.set_setting("obs_password", secret)
        check("secret set_setting ok", out.get("ok") is True, out)
        check("secret written to config", api.cfg.get("obs_password") == secret and saved)
        check("secret commit logged", any("obs_password" in m for m in logs), logs)
        check("secret plaintext not logged", not any(secret in m for m in logs), logs)
        tok = "ghp_0123456789abcdef"
        api.set_setting("github_token", tok)
        check("token plaintext not logged", not any(tok in m for m in logs), logs)
        api.set_setting("obs_port", "4460")
        check("non-secret still logs its value",
              any("obs_port = 4460" in m for m in logs), logs)
    finally:
        app_module.save_config = real_save


def test_swr_serves_last_real_value_while_refreshing():
    """A slow probe (NAS path, tailscale, git) runs off the bridge thread
    once there is a real answer to serve."""
    import threading
    work = tempfile.mkdtemp(prefix="nebula-swr-")
    api = _stub_api(work, os.path.join(work, "rec"))
    calls = []
    release = threading.Event()

    def slow():
        calls.append(time.monotonic())
        if len(calls) > 1:
            release.wait(5)
        return {"pending": len(calls) - 1}

    first = api._swr_get("probe", slow, ttl=0.0)
    check("swr first call is computed inline", first == {"pending": 0}, first)
    t0 = time.perf_counter()
    second = api._swr_get("probe", slow, ttl=0.0)
    dt = time.perf_counter() - t0
    check("swr stale read does not wait for the refresh", dt < 0.1, "%.3fs" % dt)
    check("swr stale read is the last real value", second == {"pending": 0}, second)
    api._swr_get("probe", slow, ttl=0.0)
    time.sleep(0.05)
    check("swr runs one refresh at a time", len(calls) == 2, len(calls))
    release.set()
    deadline = time.time() + 2
    while time.time() < deadline and api._swr_get("probe", slow, ttl=60) != {"pending": 1}:
        time.sleep(0.01)
    check("swr refresh lands", api._swr_get("probe", slow, ttl=60) == {"pending": 1})

    zero = api._swr_get("zero", lambda: 0, ttl=60)
    again = api._swr_get("zero", lambda: 99, ttl=60)
    check("a real zero stays a zero", zero == 0 and again == 0, (zero, again))


def test_swr_mutation_beats_stale_refresh():
    import threading
    work = tempfile.mkdtemp(prefix="nebula-swr-")
    api = _stub_api(work, os.path.join(work, "rec"))
    api._swr_get("games", lambda: "old", ttl=60)
    started, release = threading.Event(), threading.Event()

    def stale_refresh():
        started.set()
        release.wait(5)
        return "stale"

    api._swr_get("games", stale_refresh, ttl=0.0)
    started.wait(2)
    api._swr_put("games", "renamed")
    release.set()
    time.sleep(0.1)
    got = api._swr_get("games", lambda: "never", ttl=60)
    check("refresh that started before a rename can't undo it",
          got == "renamed", got)


def test_settings_and_remote_use_cached_offload_status():
    """host.offload_status() re-probes SMB roots; snapshot asks it once per TTL,
    not once per section per poll."""
    work = tempfile.mkdtemp(prefix="nebula-off-")
    api = _stub_api(work, os.path.join(work, "rec"))
    seen = []

    class Host:
        def offload_status(self):
            seen.append(1)
            return {"pending": 2, "reachability": "nas_up", "enabled": True,
                    "can_sync": True, "root": "Z:/OBS"}

    api._host = Host()
    a = api._settings_sync_footer()
    b = api._settings_sync_footer()
    check("offload status fetched once across reads", len(seen) == 1, len(seen))
    check("sync footer shows the real pending count",
          a["pending"] == 2 and b["pending"] == 2, (a["pending"], b["pending"]))
    api._swr_drop("offload_status")
    api._settings_sync_footer()
    check("a user action re-reads offload status", len(seen) == 2, len(seen))


def test_icon_urls_survive_a_long_games_list():
    """app_icons memoises 128; a games.json with more rows than that used to
    evict and re-read every icon on every poll."""
    import spike.app as app_module
    work = tempfile.mkdtemp(prefix="nebula-icons-")
    api = _stub_api(work, os.path.join(work, "rec"))
    games = {"g%03d.exe" % i: {"display_name": "Game %d" % i} for i in range(200)}
    non = {"n%03d.exe" % i: True for i in range(100)}
    api._classifier = type("C", (), {
        "snapshot": lambda self: {"games": games, "non_games": non},
        "_lock": __import__("threading").Lock(),
        "_pending_manual": {},
    })()
    api._gamesync = None
    fetched = []
    real = app_module.app_icons.data_url
    app_module.app_icons.data_url = lambda b, n: fetched.append(b) or "data:x"
    try:
        api._build_games()
        api._build_games()
    finally:
        app_module.app_icons.data_url = real
    check("each icon is encoded once", len(fetched) == 300, len(fetched))


def test_slow_snapshot_names_the_section_once():
    import spike.app as app_module
    work = tempfile.mkdtemp(prefix="nebula-slow-")
    api = _stub_api(work, os.path.join(work, "rec"))
    lines = []
    real = app_module.log_to_file
    app_module.log_to_file = lines.append
    for name in ("_obs", "_hero", "_tiles", "_activity", "_snapshot_ribbon",
                 "_snapshot_clips_panel", "_snapshot_forecast",
                 "_snapshot_games", "_settings_payload", "_macropad", "_remote"):
        setattr(api, name, lambda: {})
    api._update_offer = None
    try:
        api.snapshot()
        check("fast snapshot logs nothing", lines == [], lines)

        def slow_games():
            time.sleep(0.8)
            return {}
        api._snapshot_games = slow_games
        api.snapshot()
    finally:
        app_module.log_to_file = real
    slow = [ln for ln in lines if ln.startswith("[UI] snapshot slow:")]
    sections = [ln for ln in lines if ln.startswith("[UI] snapshot slow sections:")]
    check("slow line kept", len(slow) == 1, lines)
    check("one section line per slow call", len(sections) == 1, lines)
    check("section line names the culprit first",
          sections and sections[0].split(": ", 1)[1].startswith("games "), sections)


if __name__ == "__main__":
    test_clips_panel_skips_nas_isdir()
    test_nas_backfill_resolves_root_off_the_bridge()
    test_clip_clicks_never_resolve_the_nas_root()
    test_snapshot_isolates_section_faults()
    test_hero_survives_host_without_preview()
    test_start_menu_shortcut_is_not_dev()
    test_set_setting_never_logs_secrets()
    test_swr_serves_last_real_value_while_refreshing()
    test_swr_mutation_beats_stale_refresh()
    test_settings_and_remote_use_cached_offload_status()
    test_icon_urls_survive_a_long_games_list()
    test_slow_snapshot_names_the_section_once()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
    print("ALL PASS")
