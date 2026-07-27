"""Bugs found by hunting rather than by a failing test.

Every check here corresponds to a defect that existed in shipped code and that
the suite did not catch, because each one is about a *resource* or a *rebind*
rather than a visible behaviour - the kind that only shows up after hours of
use. They are grouped by what went wrong, with the symptom recorded.

    python tests/test_regressions.py
"""
import os
import random
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import hotkey

# Count hook add/remove before gui imports anything.
_calls = {"add": 0, "remove": 0}


class _FakeKeyboard:
    def add_hotkey(self, *a, **k):
        _calls["add"] += 1
        return f"handle{_calls['add']}"

    def remove_hotkey(self, handle):
        _calls["remove"] += 1


hotkey.keyboard = _FakeKeyboard()
hotkey._AVAILABLE = True

from obsauto import gui

gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto import design_v3 as dv
from obsauto import session_log
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow
from obsauto.obs_client import OBSError
from obsauto.replay import ReplayBuffer

config_module.save_config = lambda *a, **k: None

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


AppWindow._poll_manual_review = lambda self: None
app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=150):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


settle(250)

# ---------------------------------------------------------------------------
# Global hotkeys were never unregistered
# ---------------------------------------------------------------------------
# Symptom: editing the toggle key four times left fifteen live hooks. The stale
# suppress=True ones keep swallowing the old key system-wide, and the toggle
# fires once per surviving hook. hotkey.unregister() exists for this and was
# never called - every handle was discarded.
at_start = _calls["add"] - _calls["remove"]
check("startup binds the three global keys", at_start == 3, at_start)

for _ in range(5):
    app._register_hotkey()
live = _calls["add"] - _calls["remove"]
check("rebinding replaces hooks instead of stacking them", live == 3,
      f"{live} live hooks after 5 rebinds (add={_calls['add']} "
      f"remove={_calls['remove']})")
check("the handles are actually kept", len(app._hotkey_handles) == 3,
      app._hotkey_handles)

# ...and every key that needs a rebind must trigger one.
for key in ("toggle_hotkey", "toggle_hotkey_scancode", "replay_hotkey",
            "replay_hotkey_scancode", "replay_enabled", "palette_hotkey"):
    before = _calls["add"]
    app._settings_apply_live(key, app.config.get(key))
    check(f"changing {key} rebinds the hotkeys", _calls["add"] > before,
          "no rebind happened")

# A field claiming restart=False must genuinely apply live.
from obsauto import settings_spec

live_keys = {f.key for f in settings_spec.FIELDS if not f.restart}
for key in ("replay_hotkey", "palette_hotkey"):
    check(f"{key} claims to apply live", key in live_keys)

# ---------------------------------------------------------------------------
# PhotoImages were pinned for the life of the process
# ---------------------------------------------------------------------------
# Symptom: "Fail to allocate bitmap" part way through the stress test - Windows
# out of GDI handles. self._images was append-only while the dashboard is
# rebuilt on every relayout and the ribbon on every refresh.
random.seed(11)
names = list(gui.DEFAULT_BLOCKS)
before_global = len(app._images)
for _ in range(60):
    picked = random.sample(names, random.randint(1, len(names)))
    layout = [{"id": n, "span": dv.GRID_COLS if n == "hero" else random.choice(dv.SPANS)}
              for n in picked]
    app._relayout_grid(layout)
check("60 relayouts pin no images in the global pool",
      len(app._images) == before_global,
      f"{before_global} -> {len(app._images)}")
check("the dashboard scope holds one generation, not sixty",
      len(app._images_dashboard) < 40, len(app._images_dashboard))
app._relayout_grid([dict(it) for it in gui.DEFAULT_GRID])

# The glass cache is keyed by position now, so check it converges rather than
# growing per relayout.
size_a = len(app._glass_cache)
for _ in range(40):
    app._set_hero_state(random.choice(["watching", "recording", "paused", "disconnected"]))
check("the glass cache converges instead of growing per call",
      len(app._glass_cache) - size_a < 20,
      f"{size_a} -> {len(app._glass_cache)}")

# Clip thumbnails are four images each against a 400-clip list.
check("the clip thumbnail cache is bounded", app.CLIP_THUMB_CACHE <= 100,
      app.CLIP_THUMB_CACHE)
for i in range(app.CLIP_THUMB_CACHE + 25):
    app._clip_thumb_cache[f"clip{i}.mkv"] = ["x"] * 4
    while len(app._clip_thumb_cache) > app.CLIP_THUMB_CACHE:
        app._clip_thumb_cache.pop(next(iter(app._clip_thumb_cache)))
check("...and it stays bounded as clips are browsed",
      len(app._clip_thumb_cache) <= app.CLIP_THUMB_CACHE,
      len(app._clip_thumb_cache))
app._clip_thumb_cache.clear()

# ---------------------------------------------------------------------------
# Removing the hero module crashed the app
# ---------------------------------------------------------------------------
# Symptom: TclError "invalid command name" once a second, into a stderr that
# doesn't exist under pythonw. _poll_obs_status calls _set_hero_state forever,
# and 6.8's catalogue lets the hero be removed.
callback_errors.clear()
app._relayout_grid([{"id": "activity", "span": dv.GRID_COLS}])
check("the hero can be removed", not app._hero_present())
for state in ("watching", "recording", "paused", "disconnected"):
    app._set_hero_state(state)
app._poll_obs_status()
settle(120)
check("a removed hero doesn't crash the status poll", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")
app._relayout_grid([dict(it) for it in gui.DEFAULT_GRID])
settle(120)
check("putting it back restores the card", app._hero_present())

# ---------------------------------------------------------------------------
# The session log grew without bound and was re-read in full
# ---------------------------------------------------------------------------
work = tempfile.mkdtemp(prefix="nebula-regress-")
big = os.path.join(work, "sessions.jsonl")
session_log.log_path = lambda: big
row = '{"ts": %d, "type": "rec_stop", "game": "G", "duration": 60, "size": 1000}\n'
with open(big, "w", encoding="utf-8") as f:
    for i in range(120_000):
        f.write(row % (time.time() - i))
size_mb = os.path.getsize(big) / 1024 / 1024
t0 = time.perf_counter()
rows = session_log.read()
elapsed = (time.perf_counter() - t0) * 1000
check("a huge log is read from the tail, not in full",
      len(rows) < 120_000, f"{len(rows)} of 120000 rows from {size_mb:.0f}MB")
check("...and reading it stays fast", elapsed < 1500, f"{elapsed:.0f}ms")
check("the cap is declared", session_log.MAX_READ_BYTES <= 8 * 1024 * 1024,
      session_log.MAX_READ_BYTES)
check("tail reading still yields parseable rows",
      rows and all("ts" in r for r in rows[:5]), len(rows))
# 50k parsed dicts plus a 9MB file is real memory; holding it through the rest
# of the file starved Tk of bitmaps ("Fail to allocate bitmap") in a later
# section. The assertions above are done with it.
del rows
os.remove(big)
import gc

gc.collect()

# ---------------------------------------------------------------------------
# The spec'd periodic refreshes were declared but never scheduled
# ---------------------------------------------------------------------------
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "obsauto", "gui.py"), encoding="utf-8").read()
check("7b's 10s live ribbon update is scheduled",
      "dv.RIBBON_LIVE_UPDATE_MS" in src, "constant declared but never used")
check("7c's 15min forecast refresh is scheduled",
      "dv.FORECAST_REFRESH_MS" in src, "constant declared but never used")
check("the ribbon tick only redraws while recording",
      "_is_recording and self._current_view" in src)

# ---------------------------------------------------------------------------
# "Replay buffer is not available" had no recovery path
# ---------------------------------------------------------------------------
class FakeOBS:
    """Models what OBS actually did on this machine.

    Setting SimpleOutput/RecRB does NOT create the replay-buffer output - the
    live log proved it: arm() set RecRB=true via push_length_to_obs and the
    very next GetReplayBufferStatus still answered "not available". OBS only
    instantiates the output when the profile is loaded. `needs_reload=False`
    models the friendlier OBS that picks it up immediately.
    """

    def __init__(self, available=False, needs_reload=True):
        self.connected = True
        self.available = available
        self.needs_reload = needs_reload
        self.params = {}
        self.started = False

    def get_replay_buffer_status(self):
        if not self.available:
            raise OBSError("GetReplayBufferStatus failed: Replay buffer is not available.")
        return self.started

    def start_replay_buffer(self):
        self.started = True

    def stop_replay_buffer(self):
        self.started = False

    def set_profile_parameter(self, category, name, value):
        self.params[(category, name)] = value
        if name == "RecRB" and not self.needs_reload:
            self.available = True

    def __getattr__(self, name):
        return lambda *a, **k: None


obs = FakeOBS(available=False)
logs = []
rb = ReplayBuffer(obs, dict(app.config), on_log=logs.append)
check("arming a missing buffer fails rather than claiming success",
      rb.arm("G") is False)
check("the unavailable case is distinguished from a generic failure",
      rb.unavailable is True, rb._last_error)
check("the log says how to fix it, not just that it broke",
      any("Enable Replay Buffer" in m for m in logs), logs[-1] if logs else "")

# The pessimistic OBS: the setting lands, the output still doesn't exist.
# enable_in_obs must report that honestly rather than claiming success.
check("enabling writes the profile parameter",
      rb.enable_in_obs() is False and obs.params.get(("SimpleOutput", "RecRB")) == "true",
      obs.params)
check("...and both output modes are covered",
      ("AdvOut", "RecRB") in obs.params, sorted(obs.params))
check("...and it says OBS needs a restart rather than silently failing",
      any("restart" in m.lower() for m in logs), logs[-1] if logs else "")

# The OBS that does pick it up straight away: it must arm, not ask for a restart.
obs3 = FakeOBS(available=False, needs_reload=False)
logs3 = []
rb3 = ReplayBuffer(obs3, dict(app.config), on_log=logs3.append)
rb3.arm("G")
check("where OBS applies it live, Enable actually arms",
      rb3.enable_in_obs() is True and rb3.armed is True, logs3[-1] if logs3 else "")
check("the unavailable flag clears once it works", rb3.unavailable is False)

# A transient failure must NOT offer the button - no button fixes that.
obs2 = FakeOBS(available=True)
rb2 = ReplayBuffer(obs2, dict(app.config), on_log=lambda m: None)
obs2.get_replay_buffer_status = lambda: (_ for _ in ()).throw(OBSError("timed out"))
rb2.arm("G")
check("a transient failure is not offered the Enable fix", rb2.unavailable is False,
      rb2._last_error)

# ---------------------------------------------------------------------------
# Timers wrote to widgets the layout had destroyed
# ---------------------------------------------------------------------------
# Symptom: removing the Activity module left _flush_log writing to a destroyed
# textbox every ~80ms - a TclError per log line, invisible under pythonw, and
# the pending buffer never drained.
callback_errors.clear()
app._relayout_grid([{"id": "hero", "span": dv.GRID_COLS}])
settle(150)
for i in range(200):
    app._log(f"[Monitor] activity module is gone {i}")
settle(700)
check("logging with the Activity module removed doesn't throw",
      not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")
app._relayout_grid([dict(it) for it in gui.DEFAULT_GRID])
settle(400)
check("the history replays when the module comes back",
      "activity module is gone" in app.console.get("1.0", "end"))
check("...and nothing was dropped from it", len(app._log_lines) >= 200,
      len(app._log_lines))

# Canvas items tolerate being deleted; only widgets raise. Run every periodic
# writer against a dashboard stripped to one module.
callback_errors.clear()
app._relayout_grid([{"id": "hero", "span": dv.GRID_COLS}])
settle(150)
for fn in (app._refresh_stat_tiles, app._refresh_replay_module,
           app._refresh_forecast, app._poll_obs_status):
    fn()
app._apply_disk_stats(3, 10 ** 9, "1 GB", "D:", (10 ** 11, 10 ** 12))
settle(200)
check("every periodic writer survives its module being removed",
      not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")
app._relayout_grid([dict(it) for it in gui.DEFAULT_GRID])
settle(200)

# ---------------------------------------------------------------------------
# Rearranging the dashboard destroyed the Clips pane's search box
# ---------------------------------------------------------------------------
# Symptom: _build_clips put its search entry in _dashboard_widgets, which
# _relayout_grid destroys wholesale. One rearrange and typing in Clips raised
# TclError until restart; entering Customise mode disabled it too.
for _ in range(4):
    app._relayout_grid([dict(it) for it in gui.DEFAULT_GRID])
settle(200)
check("the Clips search box survives a dashboard rearrange",
      bool(app._clip_search.winfo_exists()))
app._set_customise(True)
settle(120)
check("...and stays usable in Customise mode",
      str(app._clip_search.cget("state")) == "normal",
      app._clip_search.cget("state"))
app._set_customise(False)
settle(150)
callback_errors.clear()
app._show_view("clips")
app._clip_search.insert(0, "hd")
app._render_clips_rows()
settle(150)
check("...and still filters", app._clip_search.get() == "hd" and not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")
check("only dashboard modules are in the dashboard widget list",
      all(w is not app._clip_search for w in app._dashboard_widgets))
app._show_view("dashboard")
settle(120)

# ---------------------------------------------------------------------------
# Every visit to Clips spawned another ffprobe storm
# ---------------------------------------------------------------------------
# Symptom: _queue_thumb_work started a raw thread per render, each launching an
# ffprobe per clip. Flicking between panes stacked 25 threads and dozens of
# concurrent subprocesses. One in flight is enough - the next render picks up
# whatever it didn't reach.
import threading

from obsauto import thumbs as thumbs_mod

_real_duration = thumbs_mod.duration_of
thumbs_mod.duration_of = lambda p: (time.sleep(0.02), 60.0)[1]
app._ui = lambda fn: None          # the marshal isn't what's under test here
app._clip_durations.clear()
clips = [{"path": f"C:/probe/c{i}.mkv", "name": f"c{i}.mkv", "game": "G",
          "rel": f"G/c{i}.mkv", "size": 10 ** 6, "mtime": time.time()}
         for i in range(30)]
base_threads = threading.active_count()
peak = base_threads
for _ in range(20):
    app._queue_thumb_work(clips, "C:/probe")
    peak = max(peak, threading.active_count())
check("repeated Clips renders don't stack scan threads",
      peak - base_threads <= 2, f"+{peak - base_threads} threads over 20 renders")
deadline = time.time() + 8
while time.time() < deadline and app._thumb_scan_busy:
    time.sleep(0.05)
check("the single-flight guard always releases", not app._thumb_scan_busy,
      "still busy after 8s")
thumbs_mod.duration_of = _real_duration

# ---------------------------------------------------------------------------
# A view's items drawn while another pane is showing appeared on top of it
# ---------------------------------------------------------------------------
# Symptom, from a screenshot: the Clips pane's session ribbon - track, axis
# ticks and the ember live block - painted straight across the Dashboard's hero
# card. _show_view hides a view by setting state on the items that exist at
# that moment; anything drawn afterwards is born visible. _refresh_ribbon runs
# on rec_stop and on mark, and _refresh_replay_module runs on every bitrate
# poll while recording, so both could fire from the wrong pane.
app._show_view("clips")
settle(150)
app._show_view("dashboard")
settle(150)
app._refresh_ribbon()
leaked = [i for i in app.bg._c.find_withtag("view_clips")
          if app.bg._c.itemcget(i, "state") != "hidden"]
check("a ribbon refresh can't paint over the Dashboard", not leaked, len(leaked))

app._refresh_replay_module()
app._show_view("clips")
settle(150)
app._refresh_replay_module()
leaked = [i for i in app.bg._c.find_withtag("blk_replay")
          if app.bg._c.itemcget(i, "state") != "hidden"]
check("a replay-module refresh can't paint over Clips", not leaked, len(leaked))

shown = [i for i in app.bg._c.find_withtag("view_clips")
         if app.bg._c.itemcget(i, "state") != "hidden"]
check("...and the ribbon is still visible on its own pane", shown, len(shown))
app._show_view("dashboard")
settle(150)

# ---------------------------------------------------------------------------
# "Recorded 0m today" beside "2 clips · 7.3 GB"
# ---------------------------------------------------------------------------
# Symptom: the duration only lands on rec_stop, so an hour into a session the
# tile read zero - which looks broken rather than honest.
work2 = tempfile.mkdtemp(prefix="nebula-today-")
today_log = os.path.join(work2, "sessions.jsonl")
session_log.log_path = lambda: today_log
now = time.time()
import json as _json

with open(today_log, "w", encoding="utf-8") as f:
    for r in ({"ts": now - 7200, "type": "rec_start", "game": "A"},
              {"ts": now - 5400, "type": "rec_stop", "game": "A",
               "duration": 1800, "size": 10 ** 9},
              {"ts": now - 3600, "type": "rec_start", "game": "B"}):
        f.write(_json.dumps(r) + "\n")
stats = session_log.today()
check("Recorded counts the recording still in progress",
      5000 < stats["recorded_seconds"] < 5600,
      f"{stats['recorded_seconds']:.0f}s, expected ~5400 (30m done + 60m live)")
check("...without inventing a finished clip", stats["clips"] == 1, stats)

# ---------------------------------------------------------------------------
# The hero named Nebula's own window as the foreground it rejected
# ---------------------------------------------------------------------------
from obsauto.monitor import Monitor

for name in ("Nebula.exe", "obs64.exe", "pythonw.exe"):
    check(f"{name} is never reported as the foreground",
          name.lower() in Monitor.SELF_PROCESSES, sorted(Monitor.SELF_PROCESSES))
check("a real app still is", "chrome.exe" not in Monitor.SELF_PROCESSES)

check("no callback exceptions overall", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<56} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
