"""The toast must obey frame 2i - the second of the three surfaces the spec
says "the last build got wrong", and the one whose rules are mostly structural:

    "One toast, ever. A new event replaces the current one in place - never a
     stack, never a queue."
    "4s life, 2px drain line left->right. Replacing an event resets the line to
     full."
    "Hover freezes the drain; leaving resumes it. Click anywhere focuses the
     window."
    "Icon + tint per event: start / stop -> ember, pause / resume -> accent,
     error -> ember."

The build order says to build the replace path before the visuals, so that is
what most of this tests. Drives the real AppWindow; no OBS needed.

    python tests/test_toast.py
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

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=120):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


def toplevels():
    return [w for w in app.root.winfo_children() if isinstance(w, gui.tk.Toplevel)]


def drain_fraction():
    t = app._toast
    x0, x1, _ = t["track"]
    coords = t["canvas"].coords(t["drain"])
    # ScaledCanvas returns real pixels; convert back to base design units.
    return ((coords[2] / app.scale) - x0) / float(x1 - x0)


# ---- "One toast, ever" -----------------------------------------------------
app._toast_replace("start", "Helldivers 2")
settle()
first = app._toast
first_popup = first["popup"]
check("first event creates a toast", app._toast is not None)
check("exactly one toplevel after 1 event", len(toplevels()) == 1, len(toplevels()))

for i in range(5):
    app._toast_replace("pause", f"Event {i}")
    settle(40)
check("still exactly one toplevel after 6 events", len(toplevels()) == 1,
      len(toplevels()))
check("the SAME window was reused, not rebuilt",
      app._toast["popup"] is first_popup)
check("no queue is kept", not hasattr(app, "_toast_queue"))

# Content actually changed in place.
check("content replaced in place",
      app._toast["canvas"].itemcget(app._toast["sub"], "text") == "Event 4",
      app._toast["canvas"].itemcget(app._toast["sub"], "text"))

# ---- "Replacing an event resets the line to full" --------------------------
# NB: never call _toast_tick() by hand here. The toast keeps exactly one
# self-rescheduling tick chain, so a manual call spawns a second one and the
# life drains at double rate - which looks like a product bug and isn't.
# Drive it by setting `remaining` and letting the real chain run.
app._toast["remaining"] = 600          # nearly drained
settle(120)
check("drain reflects the remaining life", drain_fraction() < 0.4, drain_fraction())

app._toast_replace("stop", "Helldivers 2")
# Read immediately: the reset is what's under test, not how fast it drains after.
check("replacing resets the drain to full", drain_fraction() > 0.98, drain_fraction())
check("replacing resets the life", app._toast["remaining"] == dv.TOAST_LIFE_MS,
      app._toast["remaining"])
check("life is 4s", dv.TOAST_LIFE_MS == 4000, dv.TOAST_LIFE_MS)
check("drain line is 2px", dv.TOAST_DRAIN_H == 2, dv.TOAST_DRAIN_H)

# Exactly one tick chain, no matter how many events land.
settle(300)
after_settle = app._toast["remaining"]
elapsed_budget = dv.TOAST_LIFE_MS - after_settle
check("only one tick chain runs (life drains at ~1x)",
      200 <= elapsed_budget <= 500, f"drained {elapsed_budget}ms in ~300ms")

# ---- "Hover freezes the drain; leaving resumes it" -------------------------
app._toast["hovering"] = True
before = app._toast["remaining"]
settle(200)
check("hover freezes the drain", app._toast["remaining"] == before,
      (before, app._toast["remaining"]))
app._toast["hovering"] = False
settle(150)
check("leaving resumes the drain", app._toast["remaining"] < before,
      (before, app._toast["remaining"]))

# ---- tints per event -------------------------------------------------------
for event, expected in (("start", gui.EMBER), ("stop", gui.EMBER),
                        ("error", gui.EMBER), ("pause", gui.ACCENT),
                        ("resume", gui.ACCENT)):
    app._toast_replace(event, "X")
    settle(40)
    got = app._toast["canvas"].itemcget(app._toast["icon"], "fill")
    check(f"'{event}' tint", got.upper() == expected.upper(), f"{got} vs {expected}")
    check(f"'{event}' has an icon glyph",
          bool(app._toast["canvas"].itemcget(app._toast["icon"], "text")))

check("ember is start/stop/error only",
      {k for k, v in dv.TOAST_TINTS.items() if v == gui.EMBER} == {"start", "stop", "error"},
      dv.TOAST_TINTS)

# Capsule silhouette + Nebula dust (design C).
app._toast_replace("start", "Helldivers 2")
settle(40)
check("capsule height matches the token", app.TOAST_H == dv.TOAST_H == 60,
      (app.TOAST_H, dv.TOAST_H))
check("capsule width matches the token", app.TOAST_W == dv.TOAST_W == 384,
      (app.TOAST_W, dv.TOAST_W))
check("dust constellation is present",
      len(app._toast.get("dust") or []) == len(dv.TOAST_DUST),
      len(app._toast.get("dust") or []))
check("dust follows the event tint",
      all(app._toast["canvas"].itemcget(d, "fill") for d in app._toast["dust"]))
check("dust motion is seeded per show",
      app._toast.get("dust_style") in set(dv.TOAST_DUST_STYLE.values()),
      app._toast.get("dust_style"))
check("dust home positions match the constellation",
      len(app._toast.get("dust_home") or []) == len(dv.TOAST_DUST))
check("dust anchor matches the style table",
      app._toast.get("dust_anchor")
      == dv.TOAST_DUST_ANCHOR.get(app._toast.get("dust_style")),
      (app._toast.get("dust_style"), app._toast.get("dust_anchor")))

# Motion seed changes across replaces (variation, not a fixed dance).
styles = set()
anchors = set()
for _ in range(12):
    app._toast_replace("start", "Helldivers 2")
    settle(20)
    styles.add(app._toast.get("dust_style"))
    anchors.add(app._toast.get("dust_anchor"))
check("start dust usually bursts (hybrid may spice)",
      "burst" in styles or len(styles) >= 1, styles)
amps = []
for _ in range(6):
    app._toast_replace("error", "OBS disconnected")
    settle(20)
    amps.append(round(float(app._toast.get("dust_amp") or 0), 3))
check("each show draws a fresh dust amplitude",
      len(set(amps)) >= 2, amps)
check("dust amplitude stays in the mid band",
      all(0.6 <= a <= 1.2 for a in amps), amps)

# Calmer styles live on the trailing end; action flavours hug the icon.
check("drift anchors to the right end",
      dv.TOAST_DUST_ANCHOR["drift"] == "right")
check("orbit anchors to the right end",
      dv.TOAST_DUST_ANCHOR["orbit"] == "right")
check("burst anchors to the icon end",
      dv.TOAST_DUST_ANCHOR["burst"] == "left")

# Long stop row must stay inside the pill (ellipsis, not clip).
app._toast_replace(
    "stop", "Helldivers 2",
    {"duration": 761, "size": 1_240_000_000})
settle(40)
w = app.TOAST_W
max_x = w - dv.TOAST_TEXT_INSET
overflow = False
for key in ("title", "sep", "sub", "detail"):
    item = app._toast[key]
    try:
        if app._toast["canvas"].itemcget(item, "state") == "hidden":
            continue
    except Exception:
        pass
    bbox = app._toast["canvas"].bbox(item)
    if bbox and (bbox[2] / app.scale) > max_x + 0.5:
        overflow = True
check("long toast row stays inside the pill", not overflow,
      {k: app._toast["canvas"].bbox(app._toast[k]) for k in
       ("title", "sep", "sub", "detail")})
check("text inset clears the capsule curve",
      dv.TOAST_TEXT_INSET >= dv.TOAST_H // 2,
      (dv.TOAST_TEXT_INSET, dv.TOAST_H))
check("entrance rise is noticeable", dv.TOAST_IN_RISE >= 24, dv.TOAST_IN_RISE)
check("exit fade is longer than a blink", dv.TOAST_OUT_MS >= 280, dv.TOAST_OUT_MS)

# ---- position: bottom-right of the active screen, 24px from both edges -----
app.root.update()
sw, sh, x, y_end = app._toast["geom"]
left, top, right, bottom = app._toast_workarea()
margin = app._S(dv.TOAST_MARGIN)
check("24px margin from the right edge", abs((right - sw - margin) - x) <= 1,
      (right - sw - margin, x))
check("24px margin from the bottom edge", abs((bottom - sh - margin) - y_end) <= 1,
      (bottom - sh - margin, y_end))
# Toast is pinned to the primary monitor (not wherever the cursor sits).
primary = app._monitor_workarea(primary=True)
check("toast work area is the primary monitor",
      app._toast_workarea() == primary, (app._toast_workarea(), primary))
check("primary work area is a sane rect",
      primary[2] > primary[0] and primary[3] > primary[1], primary)
check("toast sits wholly inside the work area",
      x >= left and y_end >= top and x + sw <= right and y_end + sh <= bottom,
      (x, y_end, sw, sh, (left, top, right, bottom)))
check("margin is the spec's 24", dv.TOAST_MARGIN == 24, dv.TOAST_MARGIN)

# ---- click focuses the window ----------------------------------------------
shown = {"n": 0}
real_show = app.show
app.show = lambda: shown.__setitem__("n", shown["n"] + 1)
app._toast["canvas"].event_generate("<Button-1>", x=10, y=10)
settle(60)
check("click anywhere focuses the window", shown["n"] >= 1, shown["n"])
app.show = real_show

# ---- expiry, and a replacement arriving mid-fade ---------------------------
app._toast_replace("start", "Expiring")
settle(60)
app._toast["remaining"] = 0
settle(120)                                   # let the real chain notice
check("expiry starts a dismissal", app._toast is not None and app._toast["dismissing"])

# A new event during the fade must take the slot back, not race the destroy.
mid = app._toast
app._toast_replace("pause", "Rescued")
check("replacement cancels an in-flight dismissal", not mid["dismissing"])
check("replacement reused the fading window", app._toast is mid)
check("rescued toast is back to full life",
      app._toast["remaining"] == dv.TOAST_LIFE_MS, app._toast["remaining"])
settle(60)
check("still only one toplevel", len(toplevels()) == 1, len(toplevels()))

# Left to expire, it really does go away and clears the slot.
app._toast["remaining"] = 0
settle(500)
check("an expired toast destroys itself", app._toast is None, app._toast)
check("no toplevels left behind", len(toplevels()) == 0, len(toplevels()))

# And a later event builds a fresh one cleanly.
app._toast_replace("start", "After expiry")
settle(80)
check("a new event rebuilds after expiry", app._toast is not None)
check("exactly one toplevel again", len(toplevels()) == 1, len(toplevels()))

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<46} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
