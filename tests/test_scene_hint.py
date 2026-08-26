"""Scene-name hint for unclassifiable (anti-cheat) foreground games.

When the exe classifies as unknown but the current OBS program scene exactly
names an already-classified game, that scene is the user's own mapping - use
it. Generic scenes can never fire; nothing is invented; the UI thread
(peek_only) never asks OBS.

    python tests/test_scene_hint.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.monitor import Monitor

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class FakeOBS:
    def __init__(self, scenes):
        self.connected = True
        self.scenes = scenes          # popped per get_current_program_scene call
        self.scene_calls = 0

    def get_current_program_scene(self):
        self.scene_calls += 1
        if callable(self.scenes):
            return self.scenes()
        return self.scenes


class FakeClassifier:
    """Real display_lookup semantics over a tiny registry."""
    GAMES = {"eldenring.exe": {"display_name": "Elden Ring"},
             "valorant_win64.exe": {"display_name": "VALORANT"}}

    def display_lookup(self, name):
        needle = (name or "").strip().lower()
        for base, info in self.GAMES.items():
            if info["display_name"].lower() == needle:
                return base
        return None

    def classify(self, exe_path, proc_name):
        return "unknown", None   # the anti-cheat case: nothing resolvable

    def peek(self, exe_path, proc_name):
        return "unknown", None

    def queue_for_manual_review(self, basename):
        return False


config = {
    "poll_interval_seconds": 1,
    "idle_timeout_seconds": 9999,
    "recording_root": os.environ.get("TEMP", "."),
    "keep_alive_audio_processes": [],
}

logs = []
obs = FakeOBS("Elden Ring")
mon = Monitor(obs, FakeClassifier(), config, on_log=logs.append)
mon._basename_running = staticmethod(lambda b: False)

# Foreground: an exe the classifier cannot resolve.
fg = (4242, "C:/Games/UnknownAC/protected.exe", "protected.exe",
      "AntiCheat Window", "UnrealWindow")


def patch_windows(mon, fg_tuple):
    import obsauto.monitor as m
    m.get_foreground_window_info = lambda: fg_tuple
    m.list_visible_windows = lambda: [fg_tuple] if fg_tuple else []
    mon._retarget_game_capture = lambda *a, **k: None
    return m


patch_windows(mon, fg)

target = mon._find_new_game_target()
check("scene hint resolves unknown exe",
      target is not None and target[2] == "Elden Ring", target)
check("folder follows the scene's game",
      target is not None and target[3].endswith("Elden Ring"), target)
check("hint fired exactly one OBS query (cached afterwards)",
      obs.scene_calls == 1, obs.scene_calls)
again = mon._find_new_game_target()
check("second tick reuses cached scene", obs.scene_calls == 1, obs.scene_calls)
check("one log line, not a flood",
      sum("names a known game" in m for m in logs) == 1,
      logs[-2:] if logs else [])

# A generic scene must never fire.
mon.obs = FakeOBS("Just Chatting")
mon._scene_checked_at = 0.0   # force a refresh past the interval
generic_target = mon._find_new_game_target()
check("generic scene never matches", generic_target is None, generic_target)

# peek_only must not touch OBS at all (UI-thread contract).
obs_quiet = FakeOBS(["Elden Ring"])
mon.obs = obs_quiet
peeked = mon._find_new_game_target(peek_only=True)
check("peek_only never consults OBS or guesses",
      peeked is None and obs_quiet.scene_calls == 0,
      f"{peeked} calls={obs_quiet.scene_calls}")

# Exact-match discipline: case-insensitive yes, substring no.
mon.obs = FakeOBS("elden ring")
mon._scene_checked_at = 0.0
case_target = mon._find_new_game_target()
check("matching is case-insensitive",
      case_target is not None and case_target[2].lower() == "elden ring",
      case_target)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<46} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} "
      f"({len(results)} checks)")
sys.exit(0 if passed_all else 1)
