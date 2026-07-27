"""What does typing in the Settings form actually cost on this machine?

Read the numbers, not just the PASS. This exists because of a claim that could
not be verified where the Settings editor was written (a Linux X session, which
doesn't reproduce Windows' DWM compositing at all): on this window *any* change
forces a full window-level composite, measured at ~100ms at 1770x1140, and a
text field costs one of those per keystroke. That's unavoidable for a text
field - so the design spends exactly that and no more (no live validation, no
status updates as you type). See the note above `_build_settings`.

If a keystroke really does cost ~100ms here, typing is a ~9fps experience and an
in-view form may be the wrong shape. That's a judgement call for a human looking
at real numbers, so this measures rather than merely asserts. Two views of it:

- **per-keystroke cost** - insert one character, force the redraw, time it;
  median over many, minus the cost of forcing a redraw that changes nothing.
  This is the direct answer.
- **event-loop rate** - beats per second of a 16ms heartbeat, idle vs while
  typing. This is what the lag actually feels like.

Note on statistics: p50 frame time (what test_frame_pacing uses) is *blind*
here. Keystrokes are sparse relative to the heartbeat, so most beats fall in the
gaps and the median stays clean even when every keystroke is catastrophic - an
injected 80ms stall per character left p50 at 16.1ms while quietly halving the
loop rate. Don't "simplify" this back to a p50.

The pass threshold is deliberately generous and only catches "you cannot type in
this". Anything above roughly 40ms per keystroke deserves a look even though it
passes; CLAUDE.md has the fallback (a separate Toplevel is a smaller composite
surface and is known to be cheap - the notification popup animates happily).

    python tests/test_settings_typing.py

Needs a desktop session; it briefly shows the window. No OBS required. Measure
with the window ACTUALLY MAPPED - profiling a withdrawn window skips real
painting and understates everything by ~100x.
"""
import os
import statistics
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import config as config_module, gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None
config_module.save_config = lambda *a, **k: None

from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

# The manual-review poll can open a modal dialog and block a headless run.
AppWindow._poll_manual_review = lambda self: None

# Only catches "typing is impossible". The printed cost is the real signal.
KEYSTROKE_BUDGET_MS = 150.0
SAMPLES = 40

app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.deiconify()
app.root.geometry("+60+60")
app._show_view("settings")
app.root.update()

callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb))
)

# A field whose value is never saved, so this test can't change the config.
# This pane keys its fields to (widget, Field); the Cursor branch this test
# came from stored the widget alone.
app._show_settings_group("recording")
field = app._settings_fields["recording_root"][0]


# ---- 1. direct cost of one keystroke ----------------------------------
def timed(action):
    samples = []
    for _ in range(SAMPLES):
        start = time.perf_counter()
        action()
        app.root.update_idletasks()   # force the redraw this caused
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)

# Baseline: the cost of forcing a redraw when nothing changed, so what's left
# after subtracting it is the keystroke's own cost.
baseline_ms = timed(lambda: None)
keystroke_ms = timed(lambda: field.insert("end", "x")) - baseline_ms


# ---- 2. what it does to the event loop --------------------------------
phase = {"name": "idle"}
beats = {"idle": 0, "typing": 0}
started = {"idle": time.perf_counter(), "typing": None}
ended = {}


def beat():
    # stop() flips the phase to "done" and quits, but a beat already queued
    # still fires - and "done" isn't a counter, so indexing it raised KeyError
    # intermittently. Count only the two measured phases, and stop rescheduling
    # once the run is over.
    if phase["name"] == "done":
        return
    beats[phase["name"]] += 1
    app.root.after(16, beat)


def type_a_character():
    if phase["name"] != "typing":
        return
    field.insert("end", "x")
    app.root.after(60, type_a_character)


def start_typing():
    ended["idle"] = time.perf_counter()
    phase["name"] = "typing"
    started["typing"] = time.perf_counter()
    type_a_character()


def stop():
    ended["typing"] = time.perf_counter()
    phase["name"] = "done"
    app.root.quit()


app.root.after(1, beat)
app.root.after(2000, start_typing)
app.root.after(4500, stop)
app.root.mainloop()

idle_rate = beats["idle"] / (ended["idle"] - started["idle"])
typing_rate = beats["typing"] / (ended["typing"] - started["typing"])

results = [
    ("typing stays usable", keystroke_ms < KEYSTROKE_BUDGET_MS,
     f"{keystroke_ms:.1f}ms per keystroke (budget {KEYSTROKE_BUDGET_MS:.0f}ms)"),
    ("the event loop keeps up while typing", typing_rate > idle_rate * 0.5,
     f"{typing_rate:.0f}/s typing vs {idle_rate:.0f}/s idle"),
    ("no callback exceptions while typing", not callback_errors,
     callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean"),
]

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<42} {detail}")
print(f"\nredraw with no change   {baseline_ms:6.1f}ms   (baseline, subtracted)")
print(f"cost of one keystroke   {keystroke_ms:6.1f}ms")
print(f"event loop idle         {idle_rate:6.0f} beats/s")
print(f"event loop while typing {typing_rate:6.0f} beats/s")
if keystroke_ms > 40:
    print("\n^ That is high. Typing will feel laggy. Read this module's "
          "docstring and CLAUDE.md's 'never animate the canvas per-frame' note "
          "before deciding what to do about it.")
print("ALL PASS" if passed_all else "FAILURES PRESENT")

app.root.destroy()
sys.exit(0 if passed_all else 1)
