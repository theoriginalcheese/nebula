"""Natural game-close arms a same-game reopen quiet window.

After the recording target's process exits, Monitor waits
same_game_reopen_cooldown_seconds before auto-starting that same exe again.
A different game still auto-starts immediately. No record-prompt is used.

    python tests/test_reopen_cooldown.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.monitor import Monitor

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class FakeOBS:
    def __init__(self):
        self.connected = True
        self.recording = False
        self.starts = 0
        self.stops = 0

    def is_recording(self):
        return self.recording

    def stop_record(self):
        self.stops += 1
        self.recording = False
        return {"outputPath": None}

    def start_record(self):
        self.starts += 1
        self.recording = True

    def set_record_directory(self, path):
        pass

    def set_input_settings(self, *a, **k):
        pass

    def get_record_status(self):
        return {"outputActive": self.recording}


class FakeClassifier:
    def is_game(self, *a, **k):
        return True


prompts = []
notifies = []


def on_prompt(*a):
    prompts.append(a)


def on_notify(event, display_name, details=None):
    notifies.append((event, display_name))


config = {
    "poll_interval_seconds": 1,
    "idle_timeout_seconds": 9999,
    "min_clip_seconds": 0,
    "reconnect_interval_seconds": 10,
    "holdoff_same_game_seconds": 60,
    "same_game_reopen_cooldown_seconds": 30,
    "keep_alive_audio_processes": [],
    "recording_root": os.environ.get("TEMP", "."),
    "obs_path": "",
}

obs = FakeOBS()
mon = Monitor(obs, FakeClassifier(), config,
              on_record_prompt=on_prompt, on_notify=on_notify)
mon._retarget_game_capture = lambda *a, **k: None
mon._basename_running = staticmethod(lambda b: False)

root = config["recording_root"]
target_a = (111, "gamea.exe", "Game A", os.path.join(root, "GameA"))
target_b = (222, "gameb.exe", "Game B", os.path.join(root, "GameB"))

# Pretend we were recording A, then the process vanished → apply None.
mon._recording_target = target_a
obs.recording = True
mon._apply_target(None)
check("natural stop clears recording target", mon._recording_target is None)
check("natural stop arms reopen cooldown",
      mon._reopen_cooldown_basename == "gamea.exe", mon._reopen_cooldown_basename)
check("cooldown until is in the future",
      mon._reopen_cooldown_until > time.time(), mon._reopen_cooldown_until)

check("same game blocked during cooldown",
      mon._reopen_cooldown_active("gamea.exe"))
check("other game not blocked",
      not mon._reopen_cooldown_active("gameb.exe"))

# Simulate the loop branch: same game while cooldown active → no start.
starts_before = obs.starts
if mon._reopen_cooldown_active(target_a[1]):
    pass  # skip apply
else:
    mon._apply_target(target_a)
check("same game does not start during cooldown", obs.starts == starts_before)

# Other game starts immediately.
mon._apply_target(target_b)
check("other game starts during same-game cooldown",
      obs.starts == starts_before + 1, obs.starts)
check("start toast fired for other game",
      notifies and notifies[-1][0] == "start", notifies)
check("cooldown still remembers closed game",
      mon._reopen_cooldown_basename == "gamea.exe")

# Expire cooldown → same game may start; clears on successful start.
mon._recording_target = None
obs.recording = False
mon._reopen_cooldown_until = time.time() - 1
check("cooldown inactive after expiry",
      not mon._reopen_cooldown_active("gamea.exe"))
# Re-arm then expire for apply_target clear path
mon._arm_reopen_cooldown("gamea.exe")
mon._reopen_cooldown_until = time.time() - 1
starts_before = obs.starts
# Force active check to clear expired state, then start
check("expired active-check clears state",
      not mon._reopen_cooldown_active("gamea.exe"))
mon._arm_reopen_cooldown("gamea.exe")
mon._reopen_cooldown_until = time.time() - 1
mon.clear_reopen_cooldown()  # simulate expiry clear then apply
mon._apply_target(target_a)
check("same game starts after cooldown",
      obs.starts == starts_before + 1, obs.starts)
check("no hold-off prompts used", prompts == [], prompts)

# Accept path clears cooldown (no prior target → apply won't re-arm).
mon._recording_target = None
obs.recording = False
mon._arm_reopen_cooldown("gamea.exe")
mon.clear_hold_off()
mon._hold_off_pending = target_a
mon.accept_record_prompt()
check("accept clears reopen cooldown",
      mon._reopen_cooldown_basename is None)

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
