"""Per-game capture: recording, replay buffer, or both.

    python tests/test_capture_mode.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.classifier import Classifier, resolve_capture
from obsauto.gamesync import names_only
from obsauto.monitor import Monitor

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


check("unknown capture falls back to record",
      resolve_capture(None, "nope") == "record")
check("buffer override wins",
      resolve_capture("buffer", "record") == "buffer")
check("blank override uses the default",
      resolve_capture(None, "both") == "both")

stripped = names_only({
    "games": {"game.exe": {
        "display_name": "Game", "capture": "buffer", "profile": {"fps": 60},
    }},
    "non_games": {},
})
check("shared upload does not carry capture mode",
      stripped["games"]["game.exe"] == {"display_name": "Game"})

old = None
import obsauto.classifier as classifier_mod
old = classifier_mod.DATA_FILE
tmp = tempfile.mkdtemp()
classifier_mod.DATA_FILE = os.path.join(tmp, "games.json")
try:
    clf = Classifier()
    clf.mark_game("game.exe", "Game", source="manual")
    check("unset capture is absent",
          "capture" not in clf.snapshot()["games"]["game.exe"])
    check("buffer sticks", clf.set_capture("game.exe", "buffer"))
    check("display name survives the capture write",
          clf.snapshot()["games"]["game.exe"]["display_name"] == "Game")
    check("clearing capture returns to the default",
          clf.set_capture("game.exe", None)
          and "capture" not in clf.snapshot()["games"]["game.exe"])
finally:
    classifier_mod.DATA_FILE = old


class FakeOBS:
    def __init__(self):
        self.starts = 0
        self.connected = True

    def get_record_status(self):
        return {"outputActive": False}

    def get_version(self):
        return {"obsVersion": "test"}

    def start_record(self):
        self.starts += 1

    def set_record_directory(self, path):
        pass

    def wait_until_ready(self, timeout=0):
        return True


class ListClassifier:
    def __init__(self, capture=None):
        self._data = {"games": {"game.exe": {
            "display_name": "Game",
        }}}
        if capture:
            self._data["games"]["game.exe"]["capture"] = capture

    def snapshot(self):
        return self._data


def apply(capture, default="record"):
    obs = FakeOBS()
    states = []
    mon = Monitor(
        obs, ListClassifier(capture),
        {"recording_root": tmp, "default_capture_mode": default,
         "min_clip_seconds": 0},
        on_state=lambda **kw: states.append(kw),
        on_log=lambda *a: None)
    mon._retarget_game_capture = lambda *a, **k: None
    mon._basename_running = staticmethod(lambda b: False)
    target = (1, "game.exe", "Game", os.path.join(tmp, "Game"))
    mon._apply_target(target)
    return obs, mon, states


obs, mon, states = apply("buffer")
check("buffer mode does not start a recording", obs.starts == 0, str(obs.starts))
check("buffer mode still locks onto the game",
      mon._recording_target is not None and mon._applied_capture == "buffer")
check("buffer mode tells the host",
      states and states[-1].get("capture") == "buffer")

obs, mon, states = apply(None, "record")
check("recording stays the default", obs.starts == 1, str(obs.starts))

obs, mon, states = apply(None, "buffer")
check("a buffer default skips recording", obs.starts == 0)
check("both still records", apply("both")[0].starts == 1)

obs, mon, states = apply("buffer")
mon._hold_off = True
other = (2, "other.exe", "Other", os.path.join(tmp, "Other"))
mon.classifier._data["games"]["other.exe"] = {"display_name": "Other"}
check("hold-off still blocks after a buffer game",
      mon._auto_start_blocked(other) == "hold")
mon._hold_off = False
mon._reopen_cooldown_basename = "other.exe"
mon._reopen_cooldown_until = 10 ** 12
check("reopen cooldown still blocks after a buffer game",
      mon._auto_start_blocked(other) == "cooldown")

obs, mon, states = apply(None)
starts = obs.starts
mon.classifier._data["games"]["game.exe"]["capture"] = "both"
check("record to both does not restart the clip",
      mon._note_capture_change(mon._recording_target) and obs.starts == starts)
check("record to both updates the applied mode",
      mon._applied_capture == "both")

obs, mon, states = apply("buffer")
mon._hold_off = True
mon.classifier._data["games"]["game.exe"]["capture"] = "record"
check("buffer to record during hold-off does not start",
      mon._note_capture_change(mon._recording_target) and obs.starts == 0)

obs, mon, states = apply("buffer")
mon.classifier._data["games"]["game.exe"]["capture"] = "record"
check("buffer to record needs a real apply",
      mon._note_capture_change(mon._recording_target) is False)
mon._apply_target(mon._recording_target)
check("that apply then starts recording", obs.starts == 1)

failed = [name for name, ok, _detail in results if not ok]
for name, ok, detail in results:
    print("%s  %s%s" % ("ok" if ok else "FAIL", name,
                        ("  " + detail) if detail and not ok else ""))
print("%d/%d" % (len(results) - len(failed), len(results)))
sys.exit(1 if failed else 0)
