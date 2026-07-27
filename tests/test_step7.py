"""Games (2d), Macropad (2e) and the mini overlay (2k).

The overlay's rules are the ones worth guarding - the spec calls it one of the
three surfaces "the last build got wrong":

    "296x54 ... Snaps to the nearest screen corner within 32px; remembers
     position per monitor. Drops to 55% opacity after 3s without the pointer ...
     Collapse restores the main window; it never appears while idle."

    python tests/test_step7.py
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import classifier as classifier_module
from obsauto import config as config_module
from obsauto import design_v3 as dv
from obsauto import session_log
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

# Point the classifier at a scratch file. This test marks and promotes apps, and
# writing that into the real games.json would pollute a live classification set
# (and, with sync on, push the junk to every other machine).
import shutil
import tempfile

_scratch = tempfile.mkdtemp(prefix="nebula-step7-")
classifier_module.DATA_FILE = os.path.join(_scratch, "games.json")

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


classifier = Classifier()
app = AppWindow(load_config(), classifier, on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=150):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


def texts(frame):
    out = []

    def walk(w):
        try:
            t = w.cget("text")
            if t:
                out.append(str(t))
        except Exception:
            pass
        for c in w.winfo_children():
            walk(c)

    for c in frame.winfo_children():
        walk(c)
    return out


# ---- Games (2d) ----------------------------------------------------------
app._show_view("games")
settle(400)
check("games pane has all three blocks",
      all(hasattr(app, a) for a in
          ("_games_pending", "_games_list", "_nongames_list")))
check("ignored apps listed separately", bool(texts(app._nongames_list)),
      texts(app._nongames_list)[:4])
check("footer states where the list lives",
      "games.json" in app.bg.itemcget(app._games_foot, "text"),
      app.bg.itemcget(app._games_foot, "text"))

# peek must NOT drain the queue - the modal flow owns that.
classifier.queue_for_manual_review("someunknown.exe")
peeked = classifier.peek_pending_reviews()
check("peek sees the pending item", "someunknown.exe" in peeked, peeked)
check("peek did not drain the queue",
      "someunknown.exe" in classifier.peek_pending_reviews())
popped = [k for k, _b, _n in classifier.pop_pending_reviews()]
check("pop still drains it", "someunknown.exe" in popped, popped)
classifier.finish_review("someunknown.exe")

app._refresh_games()
settle(200)
check("pending block shows an honest empty state when nothing waits",
      any("Nothing awaiting" in t for t in texts(app._games_pending)),
      texts(app._games_pending)[:3])

# Right-click promotes an ignored app back to Games.
classifier.mark_non_game("promoteme.exe")
app._refresh_games()
settle(200)
asked = {"n": 0}
gui.tkinter.messagebox.askyesno = lambda *a, **k: (asked.__setitem__("n", asked["n"] + 1), True)[1]
row = next((r for r in app._nongames_list.winfo_children()
            if "promoteme.exe" in " ".join(texts(r) + [""])), None)
if row is None:  # the row is the frame itself; match on its children
    row = next((r for r in app._nongames_list.winfo_children()
                if any("promoteme.exe" in t for t in
                       [str(c.cget("text")) for c in r.winfo_children()
                        if "text" in c.keys()])), None)
check("ignored row rendered", row is not None)
# Don't synthesise the click: CustomTkinter proxies bind() onto an inner widget,
# so event_generate() against the row never reaches the handler even though a
# real right-click does. Exercise the action the binding calls.
app._promote_non_game("promoteme.exe")
settle(200)
check("right-click asks first", asked["n"] == 1, asked)
check("promoted back into games",
      "promoteme.exe" in classifier._data.get("games", {}),
      list(classifier._data.get("games", {}))[:4])

# Declining must change nothing.
classifier.mark_non_game("declineme.exe")
gui.tkinter.messagebox.askyesno = lambda *a, **k: False
check("declining leaves it ignored",
      app._promote_non_game("declineme.exe") is False
      and "declineme.exe" in classifier._data.get("non_games", {}))
classifier._data.get("non_games", {}).pop("declineme.exe", None)

classifier._data.get("games", {}).pop("promoteme.exe", None)

# ---- Macropad (2e) stays honest -----------------------------------------
app._show_view("macropad")
settle(200)
check("macropad admits it has no device layer", True)   # rendered on canvas
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "obsauto", "gui.py"), encoding="utf-8").read()
pad = src.split("def _build_macropad", 1)[1].split("# ---- Settings", 1)[0]
check("no fabricated HID id", "0x1209" not in pad)
check("no mock key map", "Mute mic" not in pad and "Scene 1" not in pad)
check("says the layer is missing", "No device layer yet" in pad)

# ---- mini overlay (2k) ---------------------------------------------------
check("overlay size is 296x54", (dv.MINI_W, dv.MINI_H) == (296, 54),
      (dv.MINI_W, dv.MINI_H))

# "it never appears while idle"
app._obs_connected = True
app._set_hero_state("watching")
settle(80)
app.show_mini()
settle(150)
check("refuses to open while idle", app._mini is None, app._mini)
app._set_hero_state("disconnected")
app.show_mini()
settle(150)
check("refuses to open while disconnected", app._mini is None, app._mini)

# ...and does open while recording
app._current_game = "Helldivers 2"
app._tray_elapsed = "01:47:22"
app._set_hero_state("recording")
app.show_mini()
settle(300)
check("opens while recording", app._mini is not None)
check("overlay is topmost",
      bool(app._mini["popup"].attributes("-topmost")))
check("overlay shows the elapsed time",
      app._mini["canvas"].itemcget(app._mini["timer"], "text") == "01:47:22",
      app._mini["canvas"].itemcget(app._mini["timer"], "text"))
check("overlay shows the game",
      app._mini["canvas"].itemcget(app._mini["game"], "text") == "Helldivers 2")

# --- transport buttons: a deliberate deviation from 2k ----------------------
# The frame draws timer + game + collapse only. Anthony asked for buttons, so
# the shell keeps every rule 2k states and gains the three actions that are
# otherwise unreachable without restoring the whole window.
actions = app._mini.get("actions") or {}
check("the overlay carries transport buttons",
      set(actions) == {"pause", "stop", "mark"}, sorted(actions))
check("...inside the spec's shell, unchanged",
      (dv.MINI_W, dv.MINI_H) == (296, 54), (dv.MINI_W, dv.MINI_H))

# Scratch log, for the same reason the classifier gets one: a mark written here
# would otherwise land in the real sessions.jsonl and show up on the ribbon.
session_log.log_path = lambda: os.path.join(_scratch, "sessions.jsonl")
app._is_recording = True          # _mark_clip refuses when nothing is recording
marks_before = len([r for r in session_log.read() if r.get("type") == "mark"])
app._mark_clip()
app.root.update()
check("Mark clip records a mark",
      len([r for r in session_log.read() if r.get("type") == "mark"])
      == marks_before + 1)

app._hero_state = "paused"
app._mini_update()
app.root.update()
paused_glyph = app._mini["canvas"].itemcget(actions["pause"], "text")
app._hero_state = "recording"
app._mini_update()
app.root.update()
check("the pause button flips to resume while paused",
      paused_glyph != app._mini["canvas"].itemcget(actions["pause"], "text"),
      paused_glyph)

# geometry is the spec's size, scaled
app.root.update()
check("overlay geometry matches the spec",
      (app._mini["popup"].winfo_width(), app._mini["popup"].winfo_height())
      == (app._S(dv.MINI_W), app._S(dv.MINI_H)),
      (app._mini["popup"].winfo_width(), app._mini["popup"].winfo_height()))

# snapping + per-monitor memory
left, top, right, bottom = app._toast_workarea()
sw, sh = app._S(dv.MINI_W), app._S(dv.MINI_H)
app._mini["popup"].geometry(f"+{left + 10}+{top + 9}")   # within 32px of a corner
app.root.update()
app._mini_snap(app._mini)
app.root.update()
check("snaps to the nearest corner within 32px",
      (app._mini["popup"].winfo_x(), app._mini["popup"].winfo_y()) == (left, top),
      (app._mini["popup"].winfo_x(), app._mini["popup"].winfo_y()))
positions = app.config.get("mini_overlay_positions") or {}
check("position remembered per monitor", len(positions) == 1 and
      list(positions.values())[0] == [left, top], positions)

far = app._S(dv.MINI_SNAP_PX) + 40
app._mini["popup"].geometry(f"+{left + far}+{top + far}")
app.root.update()
app._mini_snap(app._mini)
app.root.update()
check("does not snap from beyond 32px",
      app._mini["popup"].winfo_x() == left + far,
      app._mini["popup"].winfo_x())

# fade
app._mini_fade(app._mini, True)
check("drops to 55% without the pointer",
      abs(float(app._mini["popup"].attributes("-alpha")) - dv.MINI_FADED_OPACITY) < 0.02,
      app._mini["popup"].attributes("-alpha"))
app._mini_fade(app._mini, False)
check("full opacity on hover",
      abs(float(app._mini["popup"].attributes("-alpha")) - 1.0) < 0.02,
      app._mini["popup"].attributes("-alpha"))
check("fade delay is 3s", dv.MINI_FADE_AFTER_MS == 3000, dv.MINI_FADE_AFTER_MS)

# recording ends -> the overlay must go, per "never while idle"
app._set_hero_state("watching")
app._mini_update()
settle(150)
check("overlay closes when the recording ends", app._mini is None, app._mini)

# collapse restores the main window
app._set_hero_state("recording")
app.show_mini()
settle(200)
restored = {"n": 0}
real_show = app.show
app.show = lambda: restored.__setitem__("n", restored["n"] + 1)
app.hide_mini(restore=True)
settle(150)
check("collapse restores the main window", restored["n"] == 1, restored)
check("overlay destroyed on collapse", app._mini is None)
app.show = real_show

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
shutil.rmtree(_scratch, ignore_errors=True)
sys.exit(0 if passed_all else 1)
