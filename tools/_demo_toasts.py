"""Show each toast event and save a PNG of it.

    python tools/_demo_toasts.py
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.nebula_identity import banner, identity
from tools.shoot import grab, grab_screen, looks_blank, set_dpi_aware

print(banner())
print()

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_toast_demo")
os.makedirs(OUT, exist_ok=True)

set_dpi_aware()

_id = identity()
with open(os.path.join(OUT, "IDENTITY.txt"), "w", encoding="utf-8") as f:
    f.write(banner("") + "\n")

app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
# Keep the main window mapped so the toast composites against a real session,
# but park it out of the way of the bottom-right toast.
app.root.geometry("+40+40")
app.root.deiconify()
app.root.update()

callback_errors = []
app.root.report_callback_exception = (
    lambda t, v, tb: callback_errors.append(
        "".join(traceback.format_exception(t, v, tb))))


def settle(ms=500):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


def capture(name):
    toast = app._toast
    assert toast is not None, f"no toast for {name}"
    # Freeze the drain so the bar is full and stable in the shot.
    toast["hovering"] = True
    toast["remaining"] = toast["life"]
    # Finish the entrance / swap pulse at full opacity.
    try:
        toast["popup"].attributes("-alpha", 1.0)
    except Exception:
        pass
    settle(280)
    hwnd = int(toast["popup"].winfo_id())
    img = grab(hwnd)
    how = "PrintWindow"
    if looks_blank(img):
        img = grab_screen(hwnd)
        how = "screen"
    path = os.path.join(OUT, f"{name}.png")
    img.save(path)
    print(f"{name:28s}  {img.width}x{img.height}  via {how}  -> {path}")
    return path


# Standard event flavours (frame 2i)
CASES = [
    ("01_start", "start", "Helldivers 2",
     {"duration": None, "size": None}),
    ("02_start_with_meta", "start", "Helldivers 2",
     None),  # subtitle only — matches the frame copy
    ("03_pause", "pause", "Helldivers 2", None),
    ("04_pause_session", "pause", "Helldivers 2",
     {"reason": "session"}),
    ("05_resume", "resume", "Helldivers 2", None),
    ("06_stop", "stop", "Helldivers 2",
     {"duration": 647, "size": 1_845_000_000}),
    ("07_error", "error", "OBS disconnected", None),
]

for name, event, sub, details in CASES:
    app._toast_replace(event, sub, details)
    settle(450)  # let rise-in / swap settle
    capture(name)

# Prompt toast (hold-off re-record) — taller card with actions
app._toast_replace(
    "prompt", "Helldivers 2",
    {"title": "Record again?"},
    actions=[("Record", lambda: None), ("Not now", lambda: None)],
)
settle(450)
capture("08_prompt")

# Also a "New game detected" prompt variant
app._toast_replace(
    "prompt", "Record Clair Obscur: Expedition 33?",
    {"title": "New game detected"},
    actions=[("Record", lambda: None), ("Not now", lambda: None)],
)
settle(450)
capture("09_prompt_new_game")

if callback_errors:
    print("\ncallback errors:")
    for e in callback_errors:
        print(e)

print(f"\nWrote {len(CASES) + 2} shots to {OUT}")
app.root.destroy()
