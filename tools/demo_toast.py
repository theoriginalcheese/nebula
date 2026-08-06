"""Show the capsule toast on your desktop — no OBS needed.

    python tools/demo_toast.py

Cycles start → pause → resume → stop → error, then exits.
Hover freezes the drain; click focuses (or creates) the main window briefly.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow


HOLD_MS = 4200

SEQUENCE = [
    ("start", "Helldivers 2", None),
    ("pause", "Helldivers 2", None),
    ("resume", "Helldivers 2", None),
    ("stop", "Helldivers 2", {"duration": 761, "size": 1_240_000_000}),
    ("error", "OBS disconnected", None),
]


def main():
    app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
    # Keep the main window out of the way — the toast is its own toplevel.
    app.root.withdraw()

    def show(i=0):
        if i >= len(SEQUENCE):
            app.root.after(1200, app.root.destroy)
            return
        event, name, details = SEQUENCE[i]
        app._toast_replace(event, name, details)
        app.root.after(HOLD_MS, lambda n=i: show(n + 1))

    app.root.after(200, show)
    app.root.mainloop()


if __name__ == "__main__":
    main()
