"""Regression tests for nav-rail view switching.

Every workspace tab must open without raising, restore the dashboard's
state-dependent visibility correctly, and keep the activity log mirrored into
both the dashboard panel and the full Activity view.

    python tests/test_views.py
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()

callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb))
)

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def settle(ms=250):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


VIEWS = ["dashboard", "recordings", "games", "activity", "macropad", "settings"]

# Log something before the Activity view is ever shown, to prove replay works.
app._log("[Monitor] test line before activity view was opened")

for view in VIEWS:
    callback_errors.clear()
    app._show_view(view)
    settle()
    check(f"open '{view}'", not callback_errors,
          callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")
    check(f"'{view}' title", gui.VIEW_TITLES[view] == app.bg.itemcget(app._topbar_title, "text"),
          app.bg.itemcget(app._topbar_title, "text"))
    check(f"'{view}' nav highlighted", app._nav[view].get("active") is True)

# Only the active view's items may be visible.
app._show_view("games")
settle()
dash_hidden = app.bg.itemcget(app._status_card_item, "state") == "hidden"
check("dashboard hidden when on Games", dash_hidden,
      app.bg.itemcget(app._status_card_item, "state"))

# Round-trip back to the dashboard: the hero must respect its own state again,
# not be blanket-shown by the tag toggle.
app._set_hero_state("watching")
app._show_view("recordings")
settle()
app._show_view("dashboard")
settle()
check("timer stays hidden when not recording",
      app.bg.itemcget(app.timer_label_id, "state") == "hidden",
      app.bg.itemcget(app.timer_label_id, "state"))
check("pause stays hidden when not recording",
      app.bg.itemcget(app._pause_btn_win, "state") == "hidden",
      app.bg.itemcget(app._pause_btn_win, "state"))

app._current_game = "Test Game"
app._set_hero_state("recording")
app._show_view("settings")
settle()
app._show_view("dashboard")
settle()
check("timer shown again while recording",
      app.bg.itemcget(app.timer_label_id, "state") == "normal",
      app.bg.itemcget(app.timer_label_id, "state"))

# Log mirroring
app._log("[OBS] mirrored line")
settle(120)
dash_text = app.console.get("1.0", "end")
full_text = app.console_full.get("1.0", "end")
check("log reaches dashboard panel", "mirrored line" in dash_text)
check("log reaches Activity view", "mirrored line" in full_text)
check("Activity replayed earlier lines", "before activity view was opened" in full_text)

# Visibility gating: hidden window must skip animation work.
check("animations gated while hidden", app._visible is False, app._visible)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<38} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
