"""The Recordings and Games lists must actually populate.

Deliberately runs under a real `mainloop()`. Both lists are filled from a worker
thread whose result comes back through `_ui()` -> `root.after`, and Tk refuses a
cross-thread `after()` when it's being driven by `update()` instead of a
mainloop. `_ui()` swallows that, so an update()-pumped test sees the list stuck
on "Scanning..." forever and would happily pass a broken implementation - or,
worse, fail a working one. This bit twice during development; hence its own file.

    python tests/test_list_views.py
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import config as config_module, gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None
config_module.save_config = lambda *a, **k: None

from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()

callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb))
)

captured = {}
results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def labels(frame):
    """Every text label currently rendered inside a scroll list."""
    found = []
    for child in frame.winfo_children():
        for widget in (child, *child.winfo_children()):
            try:
                text = widget.cget("text")
            except Exception:
                continue
            if text:
                found.append(text)
    return found


def open_recordings():
    app._show_view("recordings")
    app.root.after(2000, capture_recordings)


def capture_recordings():
    captured["recordings"] = labels(app._rec_list)
    app._show_view("games")
    app.root.after(1500, capture_games)


def capture_games():
    captured["games"] = labels(app._games_list)
    app.root.quit()


app.root.after(50, open_recordings)
app.root.after(15000, app.root.quit)  # safety net
app.root.mainloop()

rec = captured.get("recordings", [])
games = captured.get("games", [])

check("recordings list resolved", rec and not any("Scanning" in r for r in rec),
      f"{len(rec)} labels")
# Either real folders or an honest empty state - never a stuck spinner.
check("recordings shows folders or an empty state",
      any("clip" in r for r in rec) or any("No per-game folders" in r for r in rec),
      rec[0][:60] if rec else "(nothing)")
check("games list resolved", bool(games), f"{len(games)} labels")
check("games shows entries or an empty state",
      any("Nothing classified" in g for g in games) or len(games) >= 2,
      games[0][:60] if games else "(nothing)")
check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<44} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
