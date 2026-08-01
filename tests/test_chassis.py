"""Fixes 6 through 9 of the 6.7 list, plus the session log they read from.

6.5  the titlebar is exactly eight elements
6.3  stat tiles are read-only, and the four are fixed
6.4  the activity log has a header, newest-first order and three columns
6.6  the scene preview is a dark placeholder with no invented audio bars

Each of these was a case of the build adding something the spec doesn't have -
a third window control, a slider inside a display tile, an eleven-bar equaliser
metering nothing - so most of the assertions are about absence.

    python tests/test_chassis.py
"""
import os
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

import customtkinter as ctk

from obsauto import config as config_module
from obsauto import design_v3 as dv
from obsauto import session_log
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI_SRC = open(os.path.join(ROOT, "obsauto", "gui.py"), encoding="utf-8").read()

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


# ---------------------------------------------------------------------------
# The session log, which the stat tiles read
# ---------------------------------------------------------------------------
tmp = tempfile.mkdtemp(prefix="nebula-session-")
session_log.log_path = lambda: os.path.join(tmp, "sessions.jsonl")

check("an unwritten log reads as empty, not as an error", session_log.read() == [])
zero = session_log.today()
check("a fresh install counts zero, honestly",
      zero == {"clips": 0, "recorded_seconds": 0.0, "bytes": 0,
               "culled": 0, "idle_pauses": 0}, zero)

session_log.append("rec_start", game="Helldivers 2")
session_log.append("rec_stop", game="Helldivers 2", path="a.mkv", duration=3600, size=4_000_000)
session_log.append("idle_in", game="Helldivers 2", reason="idle")
session_log.append("idle_out", game="Helldivers 2")
session_log.append("rec_stop", game="Helldivers 2", path="b.mkv", duration=6, culled=True)
session_log.append("idle_in", game="Helldivers 2", reason="idle")
session_log.append("mark", game="Helldivers 2", path="a.mkv", offset=120)

stats = session_log.today()
check("kept clips are counted", stats["clips"] == 1, stats)
check("culled clips are counted separately", stats["culled"] == 1, stats)
check("idle pauses are counted", stats["idle_pauses"] == 2, stats)
check("recorded time adds up across clips", stats["recorded_seconds"] == 3606, stats)
check("a culled clip's bytes aren't counted as kept", stats["bytes"] == 4_000_000, stats)

try:
    session_log.append("nonsense")
    bad = False
except ValueError:
    bad = True
check("an unknown event type is refused", bad)

with open(session_log.log_path(), "a", encoding="utf-8") as f:
    f.write("{ this is not json\n")
check("a torn last line is skipped, not fatal", len(session_log.read()) == 7,
      len(session_log.read()))

# A telemetry file must never be able to stop a recording.
session_log.log_path = lambda: os.path.join(tmp, "no", "such", "dir", "x.jsonl")
check("an unwritable log fails soft", session_log.append("rec_start") is None)
session_log.log_path = lambda: os.path.join(tmp, "sessions.jsonl")

# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------
app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=250):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


settle(400)


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


# --- 6.5: the titlebar, exactly eight elements ------------------------------
# The circle buttons are canvas items, so count them by their hit ovals in the
# titlebar band rather than by widget type.
circles = 0
for item in app.bg._c.find_all():
    if app.bg._c.type(item) != "oval":
        continue
    x0, y0, x1, y1 = app.bg._c.coords(item)
    if y1 <= app._S(gui.TITLEBAR_HEIGHT) and (x1 - x0) >= app._S(24):
        circles += 1
check("the titlebar has two window controls, not three", circles == 2,
      f"{circles} circle buttons in the titlebar band")
check("collapse-to-mini left the titlebar",
      "collapse_mini" not in GUI_SRC.split("def _build_topbar")[0].split(
          "def _build_titlebar")[-1],
      "the mini button is still built in _build_titlebar")
check("it reappears as a pane action", "self.mini_btn" in GUI_SRC)

# "Not in the titlebar: Customise, globes, settings gears, maximise, help."
# Comments are stripped first - the code says which of these it is *not*
# building, and that note would otherwise fail the check it documents.
titlebar_src = GUI_SRC.split("def _build_titlebar")[1].split("def _build_topbar")[0]
titlebar_code = "\n".join(
    ln for ln in titlebar_src.split("\n") if not ln.lstrip().startswith("#"))
for banned in ("Customise", "globe", "maximise", "Help"):
    check(f"no {banned} in the titlebar", banned not in titlebar_code)

# "OBS + endpoint: dot 7px, one line."
check("the OBS status dot is a 7px fill glyph",
      'ICON_GLYPHS["record"]' in titlebar_code and "-7)" in titlebar_code,
      "status dot is not a 7px fill glyph")

# --- 6.3: stat tiles are read-only ------------------------------------------
tile_src = GUI_SRC.split("def _build_stats")[1].split("def _refresh_stat_tiles")[0]
check("no control lives inside a stat tile",
      "CTkSlider" not in tile_src and "CTkButton" not in tile_src, "a widget is in the row")
check("the slider left the dashboard entirely", "CTkSlider" not in GUI_SRC)
for label in ("Clips today", "Recorded", "Auto-culled", "Idle pauses"):
    check(f"the row has the {label!r} tile", f'"{label}"' in tile_src)
for gone in ("Idle timeout", "Disk free", "Sync"):
    check(f"{gone!r} is no longer a tile", f'"{gone}"' not in tile_src)
check("idle timeout is still reachable, in Settings",
      any(f.key == "idle_timeout_seconds"
          for f in __import__("obsauto.settings_spec", fromlist=["x"]).FIELDS),
      "idle_timeout_seconds is not a declared setting")

# --- 6.4: activity anatomy --------------------------------------------------
check("the log panel has a header bar", "ACTIVITY_HEADER_H" in GUI_SRC)
labels = {b.cget("text") for b in walk(app.root) if isinstance(b, ctk.CTkButton)}
check("the header carries All tags and Copy log",
      {"All tags", "Copy log"} <= labels, sorted(t for t in labels if t))
check("the columns are the spec's 58 / 74 / flex",
      (app.ACTIVITY_COL_TIME, app.ACTIVITY_COL_TAG) == (58, 74),
      (app.ACTIVITY_COL_TIME, app.ACTIVITY_COL_TAG))
check("rows past the fifth are dimmed", app.ACTIVITY_FULL_ROWS == 5)

app._log("[OBS] first line")
app._log("[Monitor] second line")
settle(300)
text = app.console.get("1.0", "end")
lines = [ln for ln in text.split("\n") if ln.strip()]
check("newest entry is at the top",
      lines and "second line" in lines[0], lines[:2])
check("every row starts with a time column",
      all(len(ln.split("\t")[0]) == 8 and ln[2] == ":" for ln in lines[:2]), lines[:2])
check("the tag is its own column",
      lines and lines[0].split("\t")[1] in ("[Monitor]", "[OBS]"),
      lines[0].split("\t") if lines else [])

# --- 6.6: the preview is dark, with no invented meters ----------------------
check("the equaliser bars are gone", not app._eq_bars, app._eq_bars)
check("nothing still draws them", "_eq_bars.append" not in GUI_SRC)
tile = app._make_preview_tile(320, 180)
mid = tile.getpixel((tile.width // 2, tile.height // 2))[:3]
accent = tuple(int(dv.ACCENT[i:i + 2], 16) for i in (1, 3, 5))
# What 6.6 rejects is a *bright flat* fill: the build's old
# `linear-gradient(150deg,#8B7CF6,#B9AEF9)` at accent brightness and above,
# which "blow[s] out the only ember cue". It is measured against the accent
# rather than against the ground range, because the frame's own accepted half
# (mockup line 1116) is `linear-gradient(140deg,#241E44,#2E2358,#5340A8)` - a
# ramp that ends on a raised surface tone and therefore leaves the ground range
# by design. Pinning this to PANEL+4 was stricter than the mockup it came from,
# and what it actually enforced was an empty black box.
check("the preview is a placeholder, not a lit violet fill",
      sum(mid) < sum(accent) * 0.55, f"centre {mid} vs accent {accent}")
check("it never approaches accent brightness",
      max(mid) < max(accent) * 0.75, f"centre {mid} vs accent {accent}")
# "Bright FLAT fills" - the other half of the complaint. A ramp has corners
# that differ; a flat fill does not.
near = tile.getpixel((6, 6))[:3]
far = tile.getpixel((tile.width - 7, tile.height - 7))[:3]
check("and it is a ramp, not a flat fill", sum(far) - sum(near) > 30,
      f"{near} -> {far}")

# "Path field: rail footer only, not in the hero."
check("the hero carries no path field", "folder_label_id" not in GUI_SRC)

app._set_hero_state("watching")
app._foreground_exe = ("chrome.exe", "non_game")
app._set_hero_state("watching")
settle(150)
check("the watching hero names the foreground it rejected",
      "chrome.exe" in app.bg._c.itemcget(app._hero_source_id, "text"),
      app.bg._c.itemcget(app._hero_source_id, "text"))
app._foreground_exe = None
app._set_hero_state("recording")
settle(120)
check("and says nothing while recording",
      not app.bg._c.itemcget(app._hero_source_id, "text"),
      app.bg._c.itemcget(app._hero_source_id, "text"))

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<54} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
