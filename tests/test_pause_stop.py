"""Stopping a paused recording must resume first.

Closing a game (or pressing Stop & save) while OBS is paused used to send
StopRecord straight into a paused output. OBS can hang forever in that state
- the encoder's end_data_capture thread never runs while paused - and Nebula
then looked frozen because GetRecordStatus was waiting on the same wedged
websocket from the Tk thread.

    python tests/test_pause_stop.py
"""
import os
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.classifier import Classifier
from obsauto.monitor import Monitor
from obsauto.obs_client import OBSClient

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class TrackingOBS:
    """Records the call order. Pause/resume/stop mutate local state."""

    def __init__(self):
        self.connected = True
        self.recording = False
        self.paused = False
        self.calls = []
        self.stop_hangs = False  # if True, stop blocks while paused (OBS bug)

    def get_record_status(self):
        self.calls.append("status")
        return {"outputActive": self.recording, "outputPaused": self.paused,
                "outputDuration": 8000, "outputBytes": 4096}

    def is_recording(self):
        return self.recording

    def start_record(self):
        self.calls.append("start")
        self.recording, self.paused = True, False

    def pause_record(self):
        self.calls.append("pause")
        self.paused = True

    def resume_record(self):
        self.calls.append("resume")
        self.paused = False

    def stop_record(self):
        # Mirror OBSClient.stop_record: lift pause, then stop.
        if self.recording and self.paused:
            self.resume_record()
        if self.stop_hangs and self.paused:
            # Would hang forever in real OBS; the test fails if we get here.
            raise AssertionError("StopRecord called while still paused")
        self.calls.append("stop")
        self.recording, self.paused = False, False
        return {"outputPath": None}

    def set_record_directory(self, path):
        pass

    def set_input_settings(self, *a, **k):
        pass


# ---- OBSClient.stop_record lifts pause ------------------------------------

class StubClient(OBSClient):
    def __init__(self):
        # Skip the real websocket ctor wiring we don't need.
        self.host = self.port = self.password = None
        self.on_log = lambda msg: None
        self._ws = None
        self._connected = threading.Event()
        self._identified = threading.Event()
        self._identified.set()
        self._lock = threading.Lock()
        self._pending = {}
        self._stop = False
        self.last_handshake_ms = 1
        self.on_event = None
        self.calls = []
        self.active = True
        self.paused = True

    def call(self, request_type, request_data=None, timeout=5):
        self.calls.append(request_type)
        if request_type == "GetRecordStatus":
            return {"outputActive": self.active, "outputPaused": self.paused}
        if request_type == "ResumeRecord":
            self.paused = False
            return {}
        if request_type == "StopRecord":
            if self.paused:
                raise AssertionError("StopRecord while paused")
            self.active = False
            return {"outputPath": None}
        return {}


stub = StubClient()
out = stub.stop_record()
check("OBSClient resumes before StopRecord",
      stub.calls == ["GetRecordStatus", "ResumeRecord", "StopRecord"],
      stub.calls)
check("OBSClient stop returns outputPath", out == {"outputPath": None})
check("OBSClient leaves recording inactive", not stub.active)

stub2 = StubClient()
stub2.paused = False
stub2.stop_record()
check("OBSClient skips Resume when not paused",
      stub2.calls == ["GetRecordStatus", "StopRecord"], stub2.calls)

# ---- Monitor game-close while manually paused -----------------------------

config = {
    "poll_interval_seconds": 1,
    "idle_timeout_seconds": 4,
    "min_clip_seconds": 0,
    "reconnect_interval_seconds": 10,
    "keep_alive_audio_processes": [],
    "recording_root": os.environ.get("TEMP", "."),
    "obs_path": "",
}
obs = TrackingOBS()
logs = []
mon = Monitor(obs, Classifier(), config, on_log=logs.append)
target = (111, "game.exe", "Game", os.path.join(config["recording_root"], "Game"))
mon._recording_target = target
mon._recording_started_at = time.time() - 30
obs.recording, obs.paused = True, True
obs.stop_hangs = True
obs.calls.clear()

ok = mon._stop_current_recording("Game")
check("monitor stop succeeds while paused", ok)
check("monitor resumed before stop",
      "resume" in obs.calls and obs.calls.index("resume") < obs.calls.index("stop"),
      obs.calls)
check("monitor cleared auto-paused flag", not mon._auto_paused)
check("monitor left OBS not recording", not obs.recording and not obs.paused)
check("monitor logged the resume-before-stop",
      any("Resuming paused recording before stop" in m for m in logs), logs)

# ---- Manual Stop & save while paused (hero / tray) ------------------------

from obsauto import gui, hotkey
from obsauto.config import load_config
from obsauto.gui import AppWindow

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))

gui_obs = TrackingOBS()
# Transport uses the raw methods; don't auto-lift inside stop so the GUI's
# own resume-before-stop is what we are measuring.
def stop_only():
    if gui_obs.stop_hangs and gui_obs.paused:
        raise AssertionError("StopRecord called while still paused")
    gui_obs.calls.append("stop")
    gui_obs.recording, gui_obs.paused = False, False
    return {"outputPath": None}
gui_obs.stop_record = stop_only
app.obs = gui_obs
app.monitor._recording_target = target
logged = []
app._log = lambda message: logged.append(message)
app._toast_replace = lambda *a, **k: None

gui_obs.recording, gui_obs.paused = True, True
gui_obs.stop_hangs = True
gui_obs.calls.clear()
app._is_recording, app._is_paused = True, True
app._toggle_record()

end = time.perf_counter() + 1.5
while time.perf_counter() < end and "stop" not in gui_obs.calls:
    app.root.update()
    time.sleep(0.01)

check("manual stop resumes before StopRecord",
      "resume" in gui_obs.calls
      and "stop" in gui_obs.calls
      and gui_obs.calls.index("resume") < gui_obs.calls.index("stop"),
      gui_obs.calls)
check("manual stop left OBS idle", not gui_obs.recording)
check("no callback exceptions during pause-stop",
      not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

# ---- Status poll must not block the Tk thread -----------------------------

blocked = {"hit": False}

def slow_status():
    blocked["hit"] = threading.current_thread() is not threading.main_thread()
    time.sleep(0.4)
    return {"outputActive": False, "outputPaused": False,
            "outputDuration": 0, "outputBytes": 0}

app.obs = TrackingOBS()
app.obs.connected = True
app.obs.get_record_status = slow_status
app._poll_in_flight = False
t0 = time.perf_counter()
app._poll_obs_status()
# The Tk call itself must return immediately; the sleep lives on a worker.
check("status poll returns without waiting on OBS",
      time.perf_counter() - t0 < 0.15,
      f"{(time.perf_counter() - t0) * 1000:.0f} ms")

end = time.perf_counter() + 1.5
while time.perf_counter() < end and not blocked["hit"]:
    app.root.update()
    time.sleep(0.01)
check("status poll runs GetRecordStatus off the Tk thread", blocked["hit"])

# Drain the apply callback so we don't leave a dangling after.
end = time.perf_counter() + 1.0
while time.perf_counter() < end and app._poll_in_flight:
    app.root.update()
    time.sleep(0.01)

# Let any in-flight transport worker finish before tearing the loop down.
end = time.perf_counter() + 0.5
while time.perf_counter() < end and getattr(app, "_transport_busy", False):
    app.root.update()
    time.sleep(0.01)
app.root.update()

try:
    app.root.destroy()
except Exception:
    pass

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
