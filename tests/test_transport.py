"""Transport commands act on OBS's live state, not a stale poll flag.

This exists because of three lines in the real log:

    23:05:07 [Manual] Recording stopped.
    23:05:08 [Manual] Recording paused.
    23:05:24 [OBS] Failed to resume: ResumeRecord failed: unknown error

The hero card's buttons branched on self._is_recording / self._is_paused, which
_poll_obs_status refreshes once a second (once every five while hidden). Press
Stop and then Pause inside that window and the second press sent PauseRecord to
a recording that had already ended - logged as a success, leaving a card that
offered a Resume OBS then refused. The fix re-reads GetRecordStatus per command.

Runs under a real mainloop: _transport uses a worker thread and marshals back
with root.after, and Tk refuses a cross-thread after() when the loop is being
driven by update()-pumping (CLAUDE.md).

    python tests/test_transport.py
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
from obsauto.obs_client import OBSError

config_module.save_config = lambda *a, **k: None

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class FakeOBS:
    """Records what was asked of it, and answers from its own real state."""

    def __init__(self):
        self.connected = True
        self.recording = False
        self.paused = False
        self.calls = []
        self.fail = None      # set to a message to make the next command raise

    def get_record_status(self):
        return {"outputActive": self.recording, "outputPaused": self.paused,
                "outputDuration": 5000, "outputBytes": 1024}

    def _maybe_fail(self):
        if self.fail:
            message, self.fail = self.fail, None
            raise OBSError(message)

    def start_record(self):
        self.calls.append("start")
        self._maybe_fail()
        self.recording, self.paused = True, False

    def stop_record(self):
        self.calls.append("stop")
        self._maybe_fail()
        self.recording, self.paused = False, False

    def pause_record(self):
        self.calls.append("pause")
        self._maybe_fail()
        self.paused = True

    def resume_record(self):
        self.calls.append("resume")
        self._maybe_fail()
        self.paused = False

    def __getattr__(self, name):
        return lambda *a, **k: None


app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))

obs = FakeOBS()
app.obs = obs
logged = []
app._log = lambda message: logged.append(message)
toasts = []
app._toast_replace = lambda event, name, details=None: toasts.append((event, name))


def settle(ms=700):
    """Wait for a worker round-trip. Safe inside mainloop."""
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


def run():
    # --- the reported bug, exactly ------------------------------------------
    obs.recording, obs.paused = True, False
    app._is_recording, app._is_paused = True, False

    app._toggle_record()                       # "Stop recording"
    settle()
    check("stop reaches OBS", obs.calls[-1] == "stop", obs.calls)
    check("stop is logged as stopped",
          logged[-1].endswith("Recording stopped."), logged[-1])

    # The poll hasn't run yet, so the cached flags still say "recording".
    # This is the one-second window the bug lived in.
    app._is_recording, app._is_paused = True, False
    obs.calls.clear()
    app._toggle_pause()                        # "Pause", pressed a beat later
    settle()
    check("no PauseRecord against a stopped recording",
          "pause" not in obs.calls, obs.calls)
    check("says nothing is recording",
          "nothing to pause" in logged[-1].lower(), logged[-1])
    check("no phantom paused state", not obs.paused, obs.paused)

    # --- the ordinary paths still work --------------------------------------
    obs.calls.clear()
    app._toggle_record()
    settle()
    check("start reaches OBS when idle", obs.calls == ["start"], obs.calls)
    check("OBS is recording", obs.recording and not obs.paused)

    obs.calls.clear()
    app._is_recording, app._is_paused = False, False   # deliberately stale again
    app._toggle_pause()
    settle()
    check("pause works off live state, not the flags",
          obs.calls == ["pause"], obs.calls)
    check("resume is what comes next",
          obs.paused, "OBS should now be paused")

    obs.calls.clear()
    app._toggle_pause()
    settle()
    check("second press resumes", obs.calls == ["resume"], obs.calls)
    check("logged as resumed", logged[-1].endswith("Recording resumed."), logged[-1])

    # --- failures are reported, not swallowed -------------------------------
    obs.calls.clear()
    toasts.clear()
    obs.fail = "PauseRecord failed: unknown error"
    app._toggle_pause()
    settle()
    check("a refused command is logged",
          "could not" in logged[-1].lower(), logged[-1])
    check("a refused command raises a toast",
          toasts and toasts[-1][0] == "error", toasts)
    check("the error text survives the worker boundary",
          "unknown error" in logged[-1], logged[-1])

    # --- one poll chain, not two --------------------------------------------
    # _transport_done calls _poll_now so the card doesn't lag a button press.
    # Done naively that starts a second self-rescheduling timer, which is how
    # the toast once drained at double speed.
    before = app._poll_job
    app._poll_now()
    pending = set(app.root.tk.call("after", "info"))
    check("_poll_now replaces the pending job, never stacks",
          app._poll_job is not None and app._poll_job != before,
          f"{before} -> {app._poll_job}")
    check("the timer it replaced is cancelled, not left running",
          before not in pending, f"cancelled {before}")
    check("the replacement is the one that's scheduled",
          app._poll_job in pending, app._poll_job)

    # --- a busy transport ignores a double press ----------------------------
    obs.calls.clear()
    app._transport_busy = True
    app._toggle_record()
    settle(150)
    check("a second press while one is in flight is dropped",
          obs.calls == [], obs.calls)
    app._transport_busy = False

    check("no callback exceptions", not callback_errors,
          callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

    passed_all = all(p for _, p, _ in results)
    for name, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name:<52} {detail}")
    print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
    app.root.quit()
    app.root.destroy()
    sys.exit(0 if passed_all else 1)


app.root.after(400, run)
app.root.after(30000, app.root.quit)   # safety net
app.root.mainloop()
