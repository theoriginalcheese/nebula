"""Frame-pacing budget for the visible window.

This exists because the Aurora redesign shipped a stutter that took three
attempts to diagnose. On this window, *any* canvas change forces a full
window-level composite costing ~100ms at 1770x1140 - and the cost is flat: it
does not scale with how much changed. Attribution runs showed moving the
full-window nebula image, swapping the 690px glow and recolouring a single 2px
star all cost the same, and halving the canvas contents barely moved it.

So a per-frame animation timer is not "a bit expensive" here, it is fatal: the
old ~12fps decorative animation produced p50 110ms frames (~9fps) with a core
pegged at 95%. Removing it gave p50 16ms at ~4%.

This test fails if a repaint-per-frame timer is ever reintroduced.

    python tests/test_frame_pacing.py

Needs a desktop session; it briefly shows the window. No OBS required.
"""
import os
import sys
import time

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

# Generous enough to survive a loaded machine, tight enough that a
# repaint-per-frame timer (which measured ~110ms) can't sneak back in.
P50_BUDGET_MS = 45.0

app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)


class FakeOBS:
    """A live, recording OBS, so the timer/size readouts tick every second."""
    connected = True
    started = time.time()

    def get_record_status(self):
        elapsed = int((time.time() - self.started) * 1000)
        return {"outputActive": True, "outputPaused": False,
                "outputDuration": elapsed, "outputBytes": elapsed * 3000}


app.obs = FakeOBS()
app.root.deiconify()
app.root.geometry("+60+60")
app.root.update()

gaps, state = [], {"last": time.perf_counter()}


def beat():
    now = time.perf_counter()
    gaps.append(now - state["last"])
    state["last"] = now
    app.root.after(16, beat)


app.root.after(1, beat)
app.root.after(5000, app.root.quit)
app.root.mainloop()

data = sorted(gaps[3:])          # discard warm-up
p50 = data[len(data) // 2] * 1000
p95 = data[int(len(data) * 0.95)] * 1000
janky = sum(1 for g in data if g > 0.033)

results = [
    ("p50 frame time within budget", p50 < P50_BUDGET_MS,
     f"{p50:.1f}ms (budget {P50_BUDGET_MS:.0f}ms)"),
    ("most frames are not janky", janky < len(data) * 0.25,
     f"{janky}/{len(data)} over 33ms"),
    ("no per-frame canvas animation timers",
     not any(hasattr(app, name) for name in ("_animate_backdrop", "_animate_hero")),
     "backdrop/hero animation timers absent"),
]

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<38} {detail}")
print(f"\np95 {p95:.1f}ms over {len(data)} frames")
print("ALL PASS" if passed_all else "FAILURES PRESENT")

app.root.destroy()
sys.exit(0 if passed_all else 1)
