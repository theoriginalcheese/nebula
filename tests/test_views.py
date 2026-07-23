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

from obsauto import config as config_module
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

# Layout changes persist through save_config(); tests must not rewrite the real
# config.json sitting next to the app. gui.py imports it inside the function, so
# patching the module attribute is enough.
config_module.save_config = lambda *a, **k: None

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

# ---- modular dashboard ----
app._show_view("dashboard")
settle()
check("customise off by default", app._customising is False)
check("grips hidden when not customising",
      app.bg.itemcget(app._grips["hero"]["tile"], "state") == "hidden",
      app.bg.itemcget(app._grips["hero"]["tile"], "state"))

app._toggle_customise()
settle(120)
check("grips shown in customise mode",
      app.bg.itemcget(app._grips["hero"]["tile"], "state") == "normal",
      app.bg.itemcget(app._grips["hero"]["tile"], "state"))

default_order = list(app._layout_order)
hero_y_before = app._blocks["hero"]["y"]

# Reorder and confirm blocks actually move and stack without overlapping.
app._apply_dashboard_layout(["activity", "stats", "hero"])
settle(120)
check("reorder applied", app._layout_order == ["activity", "stats", "hero"],
      app._layout_order)
check("hero physically moved", app._blocks["hero"]["y"] != hero_y_before,
      f"{hero_y_before} -> {app._blocks['hero']['y']}")
ys = [(app._blocks[b]["y"], app._blocks[b]["y"] + app._blocks[b]["h"])
      for b in app._layout_order]
check("blocks stack without overlap",
      all(ys[i][1] <= ys[i + 1][0] for i in range(len(ys) - 1)), ys)
check("layout stays inside the window",
      ys[0][0] >= 56 and ys[-1][1] <= 760, (ys[0][0], ys[-1][1]))
check("layout persisted to config",
      app.config.get("dashboard_layout") == ["activity", "stats", "hero"],
      app.config.get("dashboard_layout"))

# A corrupt/partial saved layout must never lose a panel.
app.config["dashboard_layout"] = ["stats", "nonsense"]
recovered = app._saved_layout()
check("bad saved layout recovers all blocks",
      sorted(recovered) == sorted(gui.DEFAULT_BLOCKS) and recovered[0] == "stats",
      recovered)

# Leaving the dashboard must drop customise mode rather than strand the grips.
app._toggle_customise() if not app._customising else None
app._set_customise(True)
app._show_view("games")
settle(120)
check("customise cleared when leaving dashboard", app._customising is False)

app._show_view("dashboard")
app._apply_dashboard_layout(list(default_order))
settle(120)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<38} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
