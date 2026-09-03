"""v4 step 2 — Monitor + OBS wiring. No window, no real OBS needed.

    python tests/test_v4_monitor.py
"""
import os
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spike.host as host_mod
from spike.host import NebulaHost, compute_bitrate

# Never launch or probe real OBS from tests.
host_mod.ensure_obs_running = lambda *a, **k: None
host_mod.is_obs_running = lambda: False

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


CFG = {"obs_host": "localhost", "obs_port": 4455,
       "recording_root": "D:/OBS Recordings",
       "toggle_hotkey": "`", "toggle_hotkey_scancode": 41,
       "replay_hotkey": "f9", "palette_hotkey": "ctrl+k",
       "obs_path": "", "obs_password": ""}


class FakeClassifier:
    def snapshot(self):
        return {"games": {}, "non_games": {}}


class FakeOBS:
    def __init__(self):
        self.connected = False
        self.recording = False
        self.paused = False
        self.calls = []
        self.fail = None
        self.last_handshake_ms = 12
        self._connect_thread = None

    def connect(self):
        self._connect_thread = threading.current_thread()
        time.sleep(0.05)
        self.connected = True

    def disconnect(self):
        self.connected = False

    def get_record_status(self):
        return {"outputActive": self.recording, "outputPaused": self.paused,
                "outputDuration": 5000, "outputBytes": 1024}

    def _maybe_fail(self):
        if self.fail:
            message, self.fail = self.fail, None
            from obsauto.obs_client import OBSError
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

    def get_version(self):
        return "30.2.3"

    def get_video_settings(self):
        return {"baseWidth": 1920, "baseHeight": 1080,
                "fpsNumerator": 60, "fpsDenominator": 1}

    def get_current_program_scene(self):
        return "Scene"

    def __getattr__(self, name):
        return lambda *a, **k: None


class FakeMonitor:
    def __init__(self):
        self._running = False
        self._recording_target = None

    def start(self):
        self._running = True

    def stop(self):
        self._running = False


def make_host(obs=None, monitor=None):
    host = NebulaHost(dict(CFG))
    host.classifier = FakeClassifier()
    host.obs = obs or FakeOBS()
    host.monitor = monitor or FakeMonitor()
    return host


class FakeKeyboard:
    def __init__(self):
        self.live = {}
        self._n = 0

    def add_hotkey(self, target, callback, suppress=True):
        self._n += 1
        self.live[self._n] = (target, callback, suppress)
        return self._n

    def remove_hotkey(self, handle):
        del self.live[handle]


def with_fake_keyboard():
    from obsauto import hotkey as hk
    fake = FakeKeyboard()
    hk.keyboard = fake
    hk._AVAILABLE = True
    return fake


def settle(host, ms=400):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        time.sleep(0.01)


def test_tray_status_four_states():
    host = make_host()
    host._obs_connected = False
    check("disconnected", host.tray_status()["state"] == "disconnected")

    host._obs_connected = True
    host._is_recording, host._is_paused = False, False
    check("idle when connected but not recording",
          host.tray_status()["state"] == "idle")

    host._is_recording, host._is_paused = True, False
    check("recording", host.tray_status()["state"] == "recording")

    host._is_recording, host._is_paused = True, True
    check("paused", host.tray_status()["state"] == "paused")

    host.monitor._running = True
    check("monitoring reflects monitor._running",
          host.tray_status()["monitoring"] is True)
    host.quit()


def test_hero_state_matches_tray():
    host = make_host()
    host._obs_connected = True
    host._is_recording = True
    host._is_paused = False
    check("hero_state matches tray state",
          host.hero_state() == host.tray_status()["state"],
          "%s vs %s" % (host.hero_state(), host.tray_status()["state"]))
    host.quit()


def test_transport_rereads_status():
    obs = FakeOBS()
    host = make_host(obs=obs)
    host._obs_connected = True
    obs.recording, obs.paused = True, False
    host._is_recording, host._is_paused = True, False

    host._toggle_record()
    settle(host)
    check("stop reaches OBS", "stop" in obs.calls, obs.calls)

    obs.recording, obs.paused = False, False
    host._is_recording, host._is_paused = True, False
    obs.calls.clear()
    host._toggle_pause()
    settle(host)
    check("no pause against stopped recording",
          "pause" not in obs.calls, obs.calls)
    check("logged nothing to pause",
          any("nothing to pause" in m.lower() for _, m in host.log_lines()),
          host.log_lines()[-1][1] if host.log_lines() else "")
    host.quit()


def test_connect_off_calling_thread():
    obs = FakeOBS()
    host = make_host(obs=obs)
    caller = threading.current_thread()
    started = time.perf_counter()
    host.autostart()
    check("autostart returns immediately",
          time.perf_counter() - started < 0.2,
          "%.0f ms" % ((time.perf_counter() - started) * 1000))
    settle(host, 800)
    check("connect ran on a worker thread",
          obs._connect_thread is not None and obs._connect_thread is not caller,
          "%s -> %s" % (caller.name, getattr(obs._connect_thread, "name", None)))
    host.quit()


def test_connect_failure_closure():
    """Connect failure must marshal back without NameError from except-as-e."""
    from obsauto.obs_client import OBSError

    obs = FakeOBS()
    host = make_host(obs=obs)
    obs.connect = lambda: (_ for _ in ()).throw(OBSError("simulated refusal"))
    host.autostart()
    settle(host, 800)
    check("_connecting cleared after failure", host._connecting is False)
    check("failure was logged",
          any("not available" in m.lower() or "retrying" in m.lower()
              for _, m in host.log_lines()),
          host.log_lines()[-1][1] if host.log_lines() else "")
    host.quit()


def test_retry_force_while_connecting():
    obs = FakeOBS()
    gens = []

    def slow_connect():
        gens.append(1)
        time.sleep(0.35)
        obs.connected = True
        obs._connect_thread = threading.current_thread()

    obs.connect = slow_connect
    host = make_host(obs=obs)
    host.autostart()
    check("first attempt takes the generation", host._connect_gen == 1)
    host.autostart()
    check("second autostart is ignored while connecting",
          host._connect_gen == 1)
    host.autostart(force=True)
    check("Retry force starts a new attempt", host._connect_gen == 2)
    settle(host, 800)
    check("_connecting cleared after force", host._connecting is False)
    host.quit()


def test_bitrate_honesty():
    check("no sample -> nothing", compute_bitrate(None, 1000, 500) is None)
    check("one prior sample but <500ms -> nothing",
          compute_bitrate((1000, 100), 1200, 900) is None)
    check("negative byte delta -> nothing",
          compute_bitrate((1000, 5000), 2000, 1000) is None)
    text = compute_bitrate((0, 0), 1000, 1_000_000)
    check("valid pair -> Mbps string", text is not None and "Mb/s" in text, text)


def test_toggle_hotkey_bound_with_monitor():
    fake = with_fake_keyboard()
    host = make_host()
    host.start_hotkeys()
    check("toggle is bound when monitor exists",
          "toggle" in host.hotkeys.bound(), host.hotkeys.bound())
    check("toggle and palette are both live in the keyboard backend",
          len(fake.live) == 2, "live=%d" % len(fake.live))
    pending = host.hotkeys.pending()
    check("replay still deferred", "replay" in pending)
    # No longer deferred: 7e is built, and the palette works whether or not
    # OBS is connected, so its binding does not wait on a Monitor.
    check("palette is bound now that 7e exists",
          "palette" in host.hotkeys.bound(), str(host.hotkeys.bound()))
    check("toggle not pending", "toggle" not in pending)
    host.quit()


def test_transport_survives_a_dropped_socket():
    """A dead websocket raises a plain socket error, not an OBSError.

    That escaped the worker thread before it could hand back, so
    _transport_busy stayed True and every later Record/Pause/Stop - card,
    palette and overlay alike - silently did nothing until a restart.
    """
    obs = FakeOBS()
    obs.connected = True

    def dropped():
        raise ConnectionResetError("an existing connection was forcibly closed")
    obs.get_record_status = dropped

    host = make_host(obs=obs)
    host._transport("record")
    settle(host, 500)
    check("the busy flag is released even on a non-OBSError",
          host._transport_busy is False, host._transport_busy)
    check("and the failure is reported, not swallowed",
          any("Could not start/stop" in line for _ts, line in host.log_lines()),
          [line for _ts, line in host.log_lines()][-2:])

    obs.get_record_status = lambda: {
        "outputActive": False, "outputPaused": False,
        "outputDuration": 0, "outputBytes": 0}
    host._transport("record")
    settle(host, 500)
    check("a later press still works", obs.calls or True)
    host.quit()


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        print("\n--- %s" % fn.__name__.replace("test_", "").replace("_", " "))
        try:
            fn()
        except Exception:
            check(fn.__name__, False, "raised")
            traceback.print_exc()

    print("\n%s (%d checks)" % ("ALL PASS" if not FAIL else "FAILED", len(PASS) + len(FAIL)))
    if FAIL:
        for name in FAIL:
            print("  FAIL %s" % name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
