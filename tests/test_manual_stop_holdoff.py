"""Manual Stop must not bounce straight back into StartRecord.

After a UI stop, Monitor arms hold-off. The same game waits
holdoff_same_game_seconds before prompting; a different game prompts as soon
as it debounces. Accept clears hold-off and starts; dismiss skips that exe
until it exits.

    python tests/test_manual_stop_holdoff.py
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

    def get_version(self):
        # The loop asks this every tick to tell "OBS is up" from "OBS is up
        # but not accepting requests yet" (websocket 207).
        return "30.2.3"

    def get_record_status(self):
        # _stop_current_recording reads this for outputDuration: the length
        # OBS actually wrote, which is what the cull and the log go by.
        return {"outputActive": self.recording, "outputPaused": False,
                "outputDuration": 600_000, "outputBytes": 1}

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


class FakeClassifier:
    def is_game(self, *a, **k):
        return True


prompts = []


def on_prompt(basename, display_name, reason, target):
    prompts.append((basename, display_name, reason))


config = {
    "poll_interval_seconds": 1,
    "idle_timeout_seconds": 9999,
    "min_clip_seconds": 0,
    "reconnect_interval_seconds": 10,
    "holdoff_same_game_seconds": 60,
    "keep_alive_audio_processes": [],
    "recording_root": os.environ.get("TEMP", "."),
    "obs_path": "",
}

obs = FakeOBS()
mon = Monitor(obs, FakeClassifier(), config, on_record_prompt=on_prompt)
target_a = (111, "gamea.exe", "Game A", os.path.join(config["recording_root"], "GameA"))
target_b = (222, "gameb.exe", "Game B", os.path.join(config["recording_root"], "GameB"))

# Pretend we were recording A, then the user hit Stop.
mon._recording_target = target_a
obs.recording = True
mon.note_manual_stop("gamea.exe", "Game A")
mon._recording_target = None
obs.recording = False
check("hold-off armed after manual stop", mon._hold_off)
check("hold-off remembers basename", mon._hold_off_basename == "gamea.exe")

# Same game before the minute is up → no prompt.
mon._hold_off_since = time.time()
mon._maybe_prompt_hold_off(target_a)
check("no same-game prompt before delay", prompts == [], prompts)

# Same game after the delay → prompt once.
mon._hold_off_since = time.time() - 61
mon._maybe_prompt_hold_off(target_a)
check("same-game prompt after delay", len(prompts) == 1 and prompts[0][2] == "same",
      prompts)
mon._maybe_prompt_hold_off(target_a)
check("same-game prompt is not repeated", len(prompts) == 1, prompts)

# Dismiss → skip until exit.
mon.dismiss_record_prompt("gamea.exe")
check("dismiss adds skip", "gamea.exe" in mon._hold_off_skip)
prompts.clear()
mon._hold_off_prompted = None
mon._maybe_prompt_hold_off(target_a)
check("skipped game does not re-prompt", prompts == [], prompts)

# Different game → switch prompt immediately.
mon._hold_off_prompted = None
mon._maybe_prompt_hold_off(target_b)
check("switch prompt for other game", len(prompts) == 1 and prompts[0][2] == "switch",
      prompts)

# Accept starts recording and clears hold-off.
starts_before = obs.starts
# Avoid real window retarget — stub it.
mon._retarget_game_capture = lambda *a, **k: None
ok = mon.accept_record_prompt()
check("accept returns True", ok)
check("accept cleared hold-off", not mon._hold_off)
check("accept started OBS", obs.starts == starts_before + 1, obs.starts)

# Clear + refresh: when held game is gone, hold-off ends.
mon.note_manual_stop("missing.exe", "Gone")
mon._basename_running = staticmethod(lambda b: False)
mon._refresh_hold_off()
check("hold-off clears when game exits", not mon._hold_off)

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
