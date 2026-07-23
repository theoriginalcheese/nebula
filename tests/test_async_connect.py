"""Regression tests for the OBS connect path and deferred-callback error handling.

Run it directly (needs a desktop session - it creates a real, hidden Tk window):

    python tests/test_async_connect.py

Covers three things that have actually broken:

1. `autostart()` must not block the Tk thread. `obs.connect()` blocks for up to
   its 5s socket timeout, and that IS the normal startup case (we usually just
   launched OBS and it's still booting). Done inline it froze the window for
   seconds on launch and again on every 10s retry.

2. Nothing may escape into a Tk callback. `except X as e` unbinds `e` at the end
   of the block, so a lambda that captures `e` and runs later via `after()`
   dies with "NameError: cannot access free variable 'e'". Both the connect
   failure path and the Steam-rescan failure path had exactly this bug, and
   under pythonw the traceback goes to a stderr that doesn't exist - i.e. it
   fails completely silently in normal use.

3. A failed connect must never leave `_connecting` stuck True, or every future
   reconnect attempt is blocked for the life of the process.

This runs under a real `mainloop()` on purpose: cross-thread `root.after()`
raises "main thread is not in main loop" when Tk is driven by `update()`
instead, which would make the test diverge from production.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None            # don't grab a global hotkey
gui.ensure_obs_running = lambda *a, **k: time.sleep(0.2)  # don't launch OBS

from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow
from obsauto.obs_client import OBSError

SLOW = 1.5  # how long the simulated connect hangs before failing

app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()

callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb))
)

results = []


def check(name, passed, detail):
    results.append((name, bool(passed), str(detail)))


def first_error():
    return callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean"


def obs_title():
    return app.bg.itemcget(app._obs_card_title, "text")


def case_slow_failure():
    """A slow connect that fails: UI stays live, state resets, nothing raises."""
    def failing_connect():
        time.sleep(SLOW)
        raise OBSError("simulated: connection refused")

    app.obs.connect = failing_connect
    started = time.perf_counter()
    app.autostart()
    check("autostart returns immediately", time.perf_counter() - started < 0.5,
          f"{(time.perf_counter() - started) * 1000:.1f} ms")

    # A 50ms heartbeat proves the event loop keeps running during the connect.
    beat = {"ticks": 0, "last": time.perf_counter(), "worst": 0.0}

    def tick():
        now = time.perf_counter()
        beat["worst"] = max(beat["worst"], now - beat["last"])
        beat["last"] = now
        beat["ticks"] += 1
        app.root.after(50, tick)

    tick()

    def assert_after_connect():
        check("UI stayed responsive during connect",
              beat["ticks"] > 20 and beat["worst"] < 0.5,
              f"{beat['ticks']} beats, worst gap {beat['worst'] * 1000:.0f} ms")
        check("failure path raised nothing", not callback_errors, first_error())
        check("_connecting reset after failure", app._connecting is False, app._connecting)
        check("status shows Disconnected", "disconnect" in obs_title().lower(), obs_title())
        case_unexpected_error()

    app.root.after(int((SLOW + 0.9) * 1000), assert_after_connect)


def case_unexpected_error():
    """A non-OSError escaping connect must not wedge reconnection forever."""
    callback_errors.clear()
    app._connecting = False
    app.monitor._running = False

    def weird_connect():
        raise ValueError("simulated: unexpected library error")

    app.obs.connect = weird_connect
    app.autostart()

    def assert_not_wedged():
        check("unexpected error doesn't wedge reconnect", app._connecting is False,
              app._connecting)
        check("unexpected error raised nothing", not callback_errors, first_error())
        case_rescan_failure()

    app.root.after(700, assert_not_wedged)


def case_rescan_failure():
    """The Steam rescan failure path had the same late-binding trap."""
    callback_errors.clear()

    def boom():
        raise RuntimeError("simulated: steam scan blew up")

    app.classifier.register_all_steam_games = boom
    app._rescan_steam()

    def assert_recovered():
        check("rescan failure raised nothing", not callback_errors, first_error())
        check("rescan button re-enabled", app.rescan_btn.cget("state") == "normal",
              app.rescan_btn.cget("state"))
        app.root.quit()

    app.root.after(900, assert_recovered)


EXPECTED_CHECKS = 9

app.root.after(10, case_slow_failure)
app.root.after(20000, app.root.quit)  # safety net so a hang can't block forever
app.root.mainloop()

passed_all = all(p for _, p, _ in results) and len(results) == EXPECTED_CHECKS
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<40} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} "
      f"({len(results)}/{EXPECTED_CHECKS} checks ran)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
