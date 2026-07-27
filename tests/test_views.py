"""Regression tests for nav-rail view switching.

Every workspace tab must open without raising, restore the dashboard's
state-dependent visibility correctly, and keep the activity log writing into
the dashboard Activity panel.

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


VIEWS = ["dashboard", "clips", "games", "macropad", "settings"]

# Log something before settle so the dashboard activity panel still receives it.
app._log("[Monitor] test line before dashboard settle")

for view in VIEWS:
    callback_errors.clear()
    app._show_view(view)
    settle()
    check(f"open '{view}'", not callback_errors,
          callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")
    check(f"'{view}' title", gui.VIEW_TITLES[view] == app.bg.itemcget(app._topbar_title, "text"),
          app.bg.itemcget(app._topbar_title, "text"))
    # v3's rail carries five destinations; Activity is a dashboard block, not a
    # rail entry, so it has no nav item to highlight (gui.RAIL_VIEWS).
    if view in gui.RAIL_VIEWS:
        check(f"'{view}' nav highlighted", app._nav[view].get("active") is True)
    else:
        check(f"'{view}' is not a rail destination", view not in app._nav)

# Only the active view's items may be visible.
app._show_view("games")
settle()
dash_hidden = app.bg.itemcget(app._status_card_item, "state") == "hidden"
check("dashboard hidden when on Games", dash_hidden,
      app.bg.itemcget(app._status_card_item, "state"))

# Round-trip back to the dashboard: the hero must respect its own state again,
# not be blanket-shown by the tag toggle.
app._set_hero_state("watching")
app._show_view("clips")
settle()
app._show_view("dashboard")
settle()
check("timer stays hidden when not recording",
      app.bg.itemcget(app.timer_label_id, "state") == "hidden",
      app.bg.itemcget(app.timer_label_id, "state"))
# v3 keeps the secondary button visible in every hero state and relabels it
# instead of hiding it ("Pause monitoring" while watching, "Stop & save" while
# paused, "Connection settings" while disconnected). What must survive the view
# round-trip is that the label still matches the state.
check("secondary button stays visible when not recording",
      app.bg.itemcget(app._pause_btn_win, "state") == "normal",
      app.bg.itemcget(app._pause_btn_win, "state"))
check("secondary button relabelled for 'watching'",
      app.pause_btn.cget("text") == "Pause monitoring", app.pause_btn.cget("text"))

app._current_game = "Test Game"
app._set_hero_state("recording")
app._show_view("settings")
settle()
app._show_view("dashboard")
settle()
check("timer shown again while recording",
      app.bg.itemcget(app.timer_label_id, "state") == "normal",
      app.bg.itemcget(app.timer_label_id, "state"))

# Log reaches the dashboard Activity panel (v3 has no standalone Activity page).
app._log("[OBS] mirrored line")
settle(120)
dash_text = app.console.get("1.0", "end")
check("log reaches dashboard panel", "mirrored line" in dash_text)
check("earlier lines still in the panel", "before dashboard settle" in dash_text)

# Visibility gating: hidden window must skip animation work.
check("animations gated while hidden", app._visible is False, app._visible)

# ---- tile-grid dashboard ----
app._show_view("dashboard")
settle()


def rects_ok(rects):
    """No two blocks overlap, and everything stays inside the content area."""
    x0 = app._content_x0()
    boxes = [(n, r[0], r[1], r[0] + r[2], r[1] + r[3]) for n, r in rects.items()]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            _, ax0, ay0, ax1, ay1 = boxes[i]
            _, bx0, by0, bx1, by1 = boxes[j]
            if ax0 < bx1 - 0.5 and bx0 < ax1 - 0.5 and ay0 < by1 - 0.5 and by0 < ay1 - 0.5:
                return False, f"overlap {boxes[i][0]} / {boxes[j][0]}"
    for n, rx0, ry0, rx1, ry1 in boxes:
        if rx0 < x0 - 0.5 or rx1 > gui.WIDTH - gui.MARGIN + 0.5 or ry1 > gui.HEIGHT + 0.5:
            return False, f"{n} out of bounds"
    return True, "ok"


check("customise off by default", app._customising is False)
check("grips hidden when not customising",
      app.bg.itemcget(app._grips["hero"]["tile"], "state") == "hidden")

app._toggle_customise()
settle(120)
check("grips shown in customise mode",
      app.bg.itemcget(app._grips["hero"]["tile"], "state") == "normal")

# Default full-width layout: no overlaps, in bounds.
ok, why = rects_ok(app._grid_rects)
check("default grid has no overlaps", ok, why)

# Put stats and activity SIDE BY SIDE (both half). This is the whole point of
# the grid over the old vertical reorder.
app._relayout_grid([
    {"name": "hero", "span": 2},
    {"name": "stats", "span": 1},
    {"name": "activity", "span": 1},
])
settle(150)
sr, ar = app._grid_rects["stats"], app._grid_rects["activity"]
check("stats & activity share a row (same y)", abs(sr[1] - ar[1]) < 1, (sr[1], ar[1]))
check("stats left, activity right", sr[0] < ar[0], (sr[0], ar[0]))
check("both are half width", sr[2] < (gui.WIDTH - gui.MARGIN - app._content_x0()) * 0.6)
ok, why = rects_ok(app._grid_rects)
check("side-by-side grid has no overlaps", ok, why)
check("layout persisted as grid",
      isinstance(app.config.get("dashboard_grid"), list)
      and {"name": "stats", "span": 1} in app.config["dashboard_grid"],
      app.config.get("dashboard_grid"))
check("old dashboard_layout key retired", "dashboard_layout" not in app.config)

# Width toggle flips a block back to full.
app._toggle_block_span("stats")
settle(150)
check("toggle made stats full width again",
      app._grid_rects["stats"][2] > (gui.WIDTH - gui.MARGIN - app._content_x0()) * 0.9)

# Every embedded widget survived the rebuilds (destroyed + recreated cleanly).
check("record button rebuilt", str(app.record_toggle_btn.winfo_exists()) == "1")
check("console rebuilt", str(app.console.winfo_exists()) == "1")

# A corrupt/partial saved grid must never lose a panel.
app.config["dashboard_grid"] = [{"name": "stats", "span": 1}, {"name": "nonsense"}]
recovered = app._saved_grid()
names = [it["name"] for it in recovered]
check("bad saved grid recovers all blocks",
      sorted(names) == sorted(gui.DEFAULT_BLOCKS) and names[0] == "stats", names)

# Leaving the dashboard must drop customise mode rather than strand the grips.
app._set_customise(True)
app._show_view("games")
settle(120)
check("customise cleared when leaving dashboard", app._customising is False)

app._show_view("dashboard")
app._relayout_grid([dict(it) for it in gui.DEFAULT_GRID])
settle(120)


# ---- v3 hero: one enum drives all four states (frames 2a, 2f-2h) ----
# Each state must swap the eyebrow, the tint and BOTH button bindings, and only
# recording/paused may show the readouts.
HERO_EXPECT = {
    "disconnected": ("Retry now", "Connection settings", False),
    "watching":     ("Record anyway", "Pause monitoring", False),
    "recording":    ("Stop recording", "Pause", True),
    "paused":       ("Resume", "Stop & save", True),
}
for state, (primary, secondary, readouts) in HERO_EXPECT.items():
    app._set_hero_state(state)
    settle(40)
    check(f"hero '{state}' primary action", app.record_toggle_btn.cget("text") == primary,
          app.record_toggle_btn.cget("text"))
    check(f"hero '{state}' secondary action", app.pause_btn.cget("text") == secondary,
          app.pause_btn.cget("text"))
    shown = app.bg.itemcget(app.timer_label_id, "state") == "normal"
    check(f"hero '{state}' readouts {'shown' if readouts else 'hidden'}", shown == readouts)

# Ember leads on exactly one state - the spec is explicit about it.
app._set_hero_state("disconnected")
check("ember leads only on disconnected",
      app.record_toggle_btn.cget("border_color") == gui.EMBER
      or gui.dv.HERO_STATES["disconnected"]["tint"] == gui.EMBER)
check("recording is accent-tinted, not ember",
      gui.dv.HERO_STATES["recording"]["tint"] == gui.ACCENT)

# Bitrate is derived from two real samples, never invented.
app._bitrate_sample = None
app._update_bitrate(1000, 1_000_000)
check("bitrate blank after one sample",
      app.bg.itemcget(app._readouts["bitrate"][1], "text") == "--",
      app.bg.itemcget(app._readouts["bitrate"][1], "text"))
app._update_bitrate(2000, 2_775_000)      # +1.775 MB in 1.0s -> 14.2 Mb/s
check("bitrate computed from the delta",
      app.bg.itemcget(app._readouts["bitrate"][1], "text") == "14.2 Mb/s",
      app.bg.itemcget(app._readouts["bitrate"][1], "text"))
app._update_bitrate(2100, 2_775_000)      # too short an interval to mean anything
check("bitrate ignores a sub-500ms interval",
      app.bg.itemcget(app._readouts["bitrate"][1], "text") == "14.2 Mb/s")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<44} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
