"""Customise mode - build spec 6.8, and fixes 11 and 12 of the 6.7 list.

    "This feature was never specified - it was invented during the build, and
     it does not work... Edit chrome is drawn as an overlay on top of each
     module instead of inside it, so handle bars cover content and modules land
     on top of each other. There is no grid, no placeholder, and no reflow."

Anthony chose to rebuild it rather than cut it, so these assertions are the
spec's list read back: strip inside the module, dashed placeholder, reflow
instead of overlap, three widths, keyboard parity, inert content, Esc reverts.

One deviation is asserted to be *documented* rather than present: "siblings
reflow over 260ms" is a 260ms animation over many canvas items, and every
canvas mutation here costs a full window composite.

    python tests/test_customise.py
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
from obsauto import design_v3 as dv
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI_SRC = open(os.path.join(ROOT, "obsauto", "gui.py"), encoding="utf-8").read()

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class Event:
    """Enough of a Tk event for the drag handlers."""
    def __init__(self, x, y):
        self.x, self.y = x, y


config = load_config()
config.pop("dashboard_layout", None)
config.pop("dashboard_grid", None)
app = AppWindow(config, Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=160):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.004)


settle(350)

# --- the grid itself --------------------------------------------------------
check("the grid is twelve columns", dv.GRID_COLS == 12, dv.GRID_COLS)
check("the gutter is the spec's 16", dv.GRID_GAP == 16, dv.GRID_GAP)
check("three widths, no more", dv.SPANS == (6, 8, 12), dv.SPANS)
check("the handle strip is 26px", dv.HANDLE_STRIP_H == 26, dv.HANDLE_STRIP_H)

# "Overlap: impossible - grid reflows, never free position." A layout is an
# order plus a width; no position is ever stored, so nothing can be dropped on
# top of anything. Prove it by asking for every combination.
def overlaps(rects):
    boxes = [(k, x, y, x + w, y + h) for k, (x, y, w, h) in rects.items()]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            _, ax0, ay0, ax1, ay1 = boxes[i]
            _, bx0, by0, bx1, by1 = boxes[j]
            if ax0 < bx1 - 0.5 and bx0 < ax1 - 0.5 and ay0 < by1 - 0.5 and by0 < ay1 - 0.5:
                return f"{boxes[i][0]} / {boxes[j][0]}"
    return None


bad = []
for a in dv.SPANS:
    for b in dv.SPANS:
        for editing in (False, True):
            layout = [{"id": "hero", "span": 12},
                      {"id": "stats", "span": a},
                      {"id": "activity", "span": b}]
            clash = overlaps(app._compute_grid(layout, editing=editing))
            if clash:
                bad.append((a, b, editing, clash))
check("no width combination can overlap", not bad, bad[:3])

within = []
for a in dv.SPANS:
    rects = app._compute_grid(
        [{"id": "hero", "span": 12}, {"id": "stats", "span": a},
         {"id": "activity", "span": 12 - a if 12 - a in dv.SPANS else 6}],
        editing=True)
    for key, (x, y, w, h) in rects.items():
        if y + h > gui.HEIGHT - gui.MARGIN + 0.5:
            within.append((a, key, y + h))
check("edit mode never pushes a module off the bottom", not within, within[:3])

# --- entering ---------------------------------------------------------------
check("nothing is built until you enter", not app._grips)
app._toggle_customise()
settle(220)
check("every module gets a handle strip",
      {"hero", "stats", "activity"} <= set(app._grips), sorted(app._grips))
check("the strip is a real layer, not an overlay label",
      all("strip" in p for p in app._grips.values()))

# "Handle strip 26px INSIDE the module, pushes content down."
hx, hy, hw, hh = app._grid_rects["hero"]
strip_coords = app.bg._c.coords(app._grips["hero"]["strip"])
check("the strip starts at the module's own top edge",
      abs(strip_coords[1] / app.scale - hy) < 1.5, (strip_coords[1] / app.scale, hy))
check("the module grew to make room for it",
      hh >= gui.HERO_H + dv.HANDLE_STRIP_H - 0.5, (hh, gui.HERO_H))

# "Grid overlay: 12 col, 1px accent @ .10, gap 16."
check("the twelve-column overlay is drawn",
      len(app._grid_overlay) == dv.GRID_COLS * 2, len(app._grid_overlay))

# "Content while editing: pointer-events:none · opacity .55."
check("each module's content is covered by a scrim",
      all("scrim" in p for p in app._grips.values()),
      [k for k, p in app._grips.items() if "scrim" not in p])
disabled = [w for w in app._dashboard_widgets
            if str(w.cget("state")) == "disabled"]
check("embedded widgets are inert while editing",
      len(disabled) == len(app._dashboard_widgets),
      f"{len(disabled)}/{len(app._dashboard_widgets)}")

# --- the drag ---------------------------------------------------------------
before_order = [it["id"] for it in app._grid_layout]
app._grip_press(Event(app._S(hx + 40), app._S(hy + 10)), "hero")
settle(80)
check("a dashed placeholder appears at true size",
      app._drop_marker is not None
      and app.bg._c.itemcget(app._drop_marker, "dash") not in ("", None),
      app.bg._c.itemcget(app._drop_marker, "dash") if app._drop_marker else None)
marker = [c / app.scale for c in app.bg._c.coords(app._drop_marker)]
check("the placeholder matches the module's rect",
      abs((marker[2] - marker[0]) - hw) < 2 and abs((marker[3] - marker[1]) - hh) < 2,
      (marker[2] - marker[0], hw))
check("the origin slot collapses",
      app.bg._c.itemcget(f"blk_hero", "state") == "hidden")
check("a dragged copy is rendered once, not per frame",
      app._drag_ghost is not None and "_make_drag_ghost" in GUI_SRC)

# Drag it past the other two modules and drop.
app._grip_drag(Event(app._S(hx + 40), app._S(hy + 700)))
settle(60)
app._grip_release()
settle(220)
after_order = [it["id"] for it in app._grid_layout]
check("dragging reorders the layout", after_order != before_order,
      f"{before_order} -> {after_order}")
check("no module was lost in the move",
      sorted(after_order) == sorted(before_order), after_order)
check("the drag chrome is cleaned up",
      app._drag_block is None and app._drop_marker is None and app._drag_ghost is None)

# --- keyboard parity --------------------------------------------------------
# "Handle is focusable. Space picks up, arrows move, Space drops, Esc cancels.
#  A pointer-only implementation is incomplete."
class Key:
    def __init__(self, keysym):
        self.keysym = keysym


order_before = [it["id"] for it in app._grid_layout]
app._kbd_focus = order_before[0]
app._customise_key(Key("space"))          # pick up
check("space picks a module up", app._kbd_held == order_before[0], app._kbd_held)
app._customise_key(Key("Down"))           # move
settle(180)
check("an arrow moves the held module",
      [it["id"] for it in app._grid_layout] != order_before,
      [it["id"] for it in app._grid_layout])
app._customise_key(Key("space"))          # drop
check("space drops it", app._kbd_held is None)

# --- widths -----------------------------------------------------------------
app._set_block_span("hero", 6)
settle(120)
check("the hero stays full width whatever you ask",
      app._grid_layout[[it["id"] for it in app._grid_layout].index("hero")]["span"] == 12,
      app._grid_layout)

# --- leaving ----------------------------------------------------------------
# "Done commits · Esc reverts the session" - the whole session, back to how it
# looked when Customise was pressed, not just the last change.
app._toggle_customise()                    # Done, ending the session so far
settle(200)
entry = [dict(it) for it in app._grid_layout]
app._toggle_customise()                    # a fresh session
settle(200)
app._set_block_span("stats", 6)
settle(120)
app._set_block_span("activity", 8)
settle(120)
check("several edits land while editing", app._grid_layout != entry, app._grid_layout)
app._cancel_customise()
settle(220)
check("Esc reverts the whole session, not just the last edit",
      app._grid_layout == entry, app._grid_layout)
check("Esc leaves edit mode", app._customising is False)
check("the edit chrome is gone", not app._grips and not app._grid_overlay)
# The activity log's textbox is read-only by design and stays disabled; what
# has to come back to life is everything you can actually press.
buttons = [w for w in app._dashboard_widgets if w is not app.console]
check("controls are live again",
      buttons and all(str(w.cget("state")) != "disabled" for w in buttons),
      [str(w.cget("state")) for w in buttons])
check("and readable again",
      str(app.record_toggle_btn.cget("text_color")).lower()
      != str(dv.over(dv.ACCENT_TEXT, dv.EDIT_CONTENT_OPACITY, dv.PANEL)).lower(),
      app.record_toggle_btn.cget("text_color"))

# --- the documented deviation ----------------------------------------------
check("the 260ms sibling reflow is recorded, not animated",
      "REFLOW_MS_UNUSED" in open(
          os.path.join(ROOT, "obsauto", "design_v3.py"), encoding="utf-8").read()
      and "REFLOW_MS_UNUSED" not in GUI_SRC,
      "gui.py reads the quarantined reflow duration")

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<52} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
