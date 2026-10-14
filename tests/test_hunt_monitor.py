"""Bug hunt: capture/session-control races in monitor.py and replay.py.

    python tests/test_hunt_monitor.py

Three bugs proved here:

1. Discord-hold switch onto a buffer-only game kept OBS recording under the
   new game's name while Monitor claimed nothing was recording at all
   (``_retarget_live`` didn't check capture mode) - see
   ``test_discord_hold_onto_buffer_only_game_stops_instead_of_mislabeling``.

2. ``ReplayBuffer._save_around_pause`` always restored a lifted recording
   pause, even when the user had stopped being idle during the save - which
   left the recording stuck paused with Monitor's own ``_auto_paused`` flag
   already cleared and nothing left to notice or fix it - see
   ``test_replay_save_does_not_repause_after_idle_ends``.

3. ``session_detect.moonlight_session_active()`` judged "live" purely from
   which marker was last in the log. A Moonlight.exe process that is still
   alive but whose stream window has already died (crash, GPU/driver kill,
   anything that doesn't cleanly write "Stopping video stream...") kept
   reading as live forever, so Monitor's session gate never paused the
   recording - see ``test_moonlight_gate_drops_a_dead_window_even_if_the_log_still_says_live``.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import monitor as monitor_mod
from obsauto.monitor import Monitor
from obsauto.replay import ReplayBuffer
from obsauto import session_detect as sd

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


# ---------------------------------------------------------------------------
# Bug 1: buffer-only target under a Discord-call hold switch
# ---------------------------------------------------------------------------
class FakeOBS:
    def __init__(self):
        self.connected = True
        self.dir = None
        self.capture = []
        self.started = 0
        self.stopped = 0
        self._recording = False

    def is_recording(self):
        return self._recording

    def get_version(self):
        return "30.2.3"

    def get_record_status(self):
        return {"outputActive": self._recording, "outputPaused": False,
                "outputDuration": 5000}

    def stop_record(self):
        self.stopped += 1
        self._recording = False
        return {"outputPath": None}

    def start_record(self):
        self.started += 1
        self._recording = True

    def set_record_directory(self, path):
        self.dir = path

    def set_input_settings(self, name, settings):
        self.capture.append((name, settings))

    def pause_record(self):
        pass

    def resume_record(self):
        pass


class FakeClassifier:
    """gameb.exe is configured buffer-only - the per-game setting the Games
    pane's capture-mode control writes (``obsauto.profiles``/``resolve_capture``)."""

    def classify(self, exe_path, proc_name):
        return "game", "Gameb"

    def snapshot(self):
        return {"games": {"gameb.exe": {"capture": "buffer"}}}


def run_buffer_hold_bug():
    root = tempfile.mkdtemp(prefix="nebula-hunt-buffer-")
    config = {
        "recording_root": root,
        "idle_timeout_seconds": 9999,
        "poll_interval_seconds": 1,
        "min_clip_seconds": 0,
        "keep_alive_audio_processes": [],
    }
    obs = FakeOBS()
    mon = Monitor(obs, FakeClassifier(), config, on_log=lambda m: None)

    target_a = (111, "gamea.exe", "Gamea", os.path.join(root, "Gamea"))
    target_b = (222, "gameb.exe", "Gameb", os.path.join(root, "Gameb"))

    # Recording Game A; a Discord call is active and focus switches to the
    # buffer-only Game B, so the monitor loop calls _apply_target with
    # hold_recording=True (the "don't hard-cut the call" path).
    mon._recording_target = target_a
    mon._applied_capture = "record"
    obs._recording = True
    mon._recording_started_at = 1.0

    mon._apply_target(target_b, hold_recording=True)

    check("Game A's recording is actually stopped, not silently retargeted",
          obs.stopped == 1, obs.stopped)
    check("no fresh recording was started for a buffer-only game",
          obs.started == 0, obs.started)
    check("Monitor's own bookkeeping matches OBS: nothing is really recording",
          mon._nothing_recording() and obs._recording is False,
          (mon._nothing_recording(), obs._recording))
    check("the target still moved onto Game B",
          mon._recording_target is not None and mon._recording_target[1] == "gameb.exe",
          mon._recording_target)
    check("capture mode recorded as buffer",
          mon._applied_capture == "buffer", mon._applied_capture)


run_buffer_hold_bug()


# ---------------------------------------------------------------------------
# Bug 2: replay's pause-restore race against idle ending
# ---------------------------------------------------------------------------
class FakeReplayOBS:
    def __init__(self):
        self.connected = True
        self.calls = []
        self.rec_active = True
        self.rec_paused = True

    def get_record_status(self):
        return {"outputActive": self.rec_active, "outputPaused": self.rec_paused}

    def pause_record(self):
        self.calls.append("pause")
        self.rec_paused = True

    def resume_record(self):
        self.calls.append("resume")
        self.rec_paused = False

    def save_replay_buffer(self):
        self.calls.append("save")

    def set_profile_parameter(self, *a, **k):
        pass


def run_replay_idle_race_bug():
    real_idle = monitor_mod.get_idle_duration
    obs = FakeReplayOBS()
    cfg = {"idle_timeout_seconds": 4, "recording_root": tempfile.mkdtemp(
        prefix="nebula-hunt-replay-")}
    rb = ReplayBuffer(obs, cfg)
    rb.armed = True

    # The recording was auto-paused for idle. The replay hotkey fires: OBS
    # lifts the pause to write the buffer. While that save is in flight, the
    # user comes back (moves the mouse) - exactly what Monitor's own
    # get_idle_duration()-vs-idle_timeout_seconds check would see as "no
    # longer idle".
    monitor_mod.get_idle_duration = lambda: 0.1
    try:
        ok = rb.save()
        check("save is accepted while paused", ok is True)
        for _ in range(200):
            if "save" in obs.calls:
                break
            time.sleep(0.01)
        check("the pause was lifted to perform the save",
              obs.calls[:2] == ["resume", "save"], obs.calls)

        rb.handle_event("ReplayBufferSaved", {"savedReplayPath": None})
        for _ in range(300):
            if not rb._pause_save_inflight:
                break
            time.sleep(0.01)

        check("the recording is left running, not re-paused out from under "
              "the now-active user",
              obs.rec_paused is False, obs.calls)
    finally:
        monitor_mod.get_idle_duration = real_idle


run_replay_idle_race_bug()


def run_replay_idle_race_control_case():
    """Control: if the user genuinely is still idle, the pause IS restored -
    the fix must not disable the whole feature."""
    real_idle = monitor_mod.get_idle_duration
    obs = FakeReplayOBS()
    cfg = {"idle_timeout_seconds": 4, "recording_root": tempfile.mkdtemp(
        prefix="nebula-hunt-replay-ctrl-")}
    rb = ReplayBuffer(obs, cfg)
    rb.armed = True

    monitor_mod.get_idle_duration = lambda: 999.0  # still away from the keyboard
    try:
        rb.save()
        for _ in range(200):
            if "save" in obs.calls:
                break
            time.sleep(0.01)
        rb.handle_event("ReplayBufferSaved", {"savedReplayPath": None})
        for _ in range(300):
            if not rb._pause_save_inflight:
                break
            time.sleep(0.01)
        check("still-idle case: the pause IS restored",
              obs.rec_paused is True, obs.calls)
    finally:
        monitor_mod.get_idle_duration = real_idle


run_replay_idle_race_control_case()


# ---------------------------------------------------------------------------
# Bug 3: Moonlight session gate trusts a log that can't say "the process
# crashed", so a dead stream window still reads as a live session.
# ---------------------------------------------------------------------------
def run_moonlight_dead_window_bug():
    work = tempfile.mkdtemp(prefix="nebula-hunt-moonlight-")
    real_glob = sd.MOONLIGHT_LOG_GLOB
    real_proc_alive = sd._moonlight_process_alive
    real_window_alive = sd._moonlight_window_alive
    sd.MOONLIGHT_LOG_GLOB = os.path.join(work, "Moonlight-*.log")
    try:
        log_path = os.path.join(work, "Moonlight-crash.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("Starting video stream...\n")
            # No "Stopping video stream..." - the real-world case: a GPU
            # reset / network drop / crash kills the stream window without
            # Moonlight ever getting the chance to log a clean stop.

        # Moonlight.exe itself is still a live process (e.g. hung main
        # window, or the window closed but the process hasn't exited yet),
        # but there is no stream-surface HWND left for it.
        sd._moonlight_process_alive = lambda: True
        sd._moonlight_window_alive = lambda: False
        check("a dead stream window must not read as a live session",
              sd.moonlight_session_active() is False,
              sd.moonlight_session_active())

        # Control: process alive AND a real stream window present -> live,
        # same log. The fix must not disable genuine detection.
        sd._moonlight_window_alive = lambda: True
        check("control: window actually present still reads live",
              sd.moonlight_session_active() is True)

        # Control: can't tell whether Moonlight is even running (the normal
        # case on a machine with Moonlight not installed/running) -> fall
        # back to the log alone, exactly as before this fix.
        sd._moonlight_process_alive = lambda: False
        sd._moonlight_window_alive = lambda: False
        check("control: unknown process state defers to the log",
              sd.moonlight_session_active() is True)
    finally:
        sd.MOONLIGHT_LOG_GLOB = real_glob
        sd._moonlight_process_alive = real_proc_alive
        sd._moonlight_window_alive = real_window_alive


run_moonlight_dead_window_bug()


passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<66} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
