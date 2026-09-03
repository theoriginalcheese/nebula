"""Hold recording across game switches while Discord call is active.

    python tests/test_discord_hold.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import discord_detect
from obsauto.monitor import Monitor

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


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
        # The loop asks this every tick to tell "OBS is up" from "OBS is up
        # but not accepting requests yet" (websocket 207).
        return "30.2.3"

    def get_record_status(self):
        return {"outputActive": self._recording, "outputPaused": False}

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
    def classify(self, exe_path, proc_name):
        name = (proc_name or "").lower()
        if name in ("gamea.exe", "gameb.exe"):
            return "game", name.replace(".exe", "").title()
        return "not_game", proc_name


def run():
    root = tempfile.mkdtemp(prefix="nebula-hold-")
    config = {
        "recording_root": root,
        "idle_timeout_seconds": 9999,
        "poll_interval_seconds": 1,
        "min_clip_seconds": 0,
        "keep_alive_audio_processes": [],
    }
    obs = FakeOBS()
    logs = []
    mon = Monitor(obs, FakeClassifier(), config, on_log=logs.append)

    target_a = (111, "gamea.exe", "Gamea", os.path.join(root, "Gamea"))
    target_b = (222, "gameb.exe", "Gameb", os.path.join(root, "Gameb"))

    # Seed as if already recording Game A.
    mon._recording_target = target_a
    obs._recording = True
    mon._recording_started_at = 1.0

    # Without Discord call → normal apply stops then starts.
    mon._apply_target(target_b, hold_recording=False)
    check("normal switch stops recording", obs.stopped == 1, obs.stopped)
    check("normal switch starts fresh", obs.started == 1, obs.started)
    check("normal switch updates target",
          mon._recording_target[1] == "gameb.exe", mon._recording_target)

    # Reset: recording Game A again.
    mon._recording_target = target_a
    obs._recording = True
    obs.stopped = 0
    obs.started = 0
    obs.dir = None

    mon._apply_target(target_b, hold_recording=True)
    check("hold switch does not stop", obs.stopped == 0, obs.stopped)
    check("hold switch does not start", obs.started == 0, obs.started)
    check("hold switch updates target",
          mon._recording_target[1] == "gameb.exe", mon._recording_target)
    check("hold switch retargets directory",
          obs.dir == os.path.join(root, "Gameb"), obs.dir)
    check("hold logged Discord call reason",
          any("Discord call" in m for m in logs), logs[-3:])

    # Same target is a no-op.
    before = (obs.stopped, obs.started, obs.dir)
    mon._apply_target(target_b, hold_recording=True)
    check("hold same target is no-op",
          (obs.stopped, obs.started, obs.dir) == before)

    # Probe helper stays honest.
    discord_detect._reset_cache_for_tests()
    check("discord_voice_active is bool",
          isinstance(discord_detect.discord_voice_active(force=True), bool))


run()
passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
