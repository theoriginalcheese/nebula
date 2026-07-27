"""Per-game encoder profiles - spec 7d.

Two of the spec's rules are safety rules rather than features, and both are
asserted against the module rather than left to callers:

    "Scope guard: resolution, fps, encoder, bitrate, scene. That is the whole
     feature. No audio tracks, no filters, no output paths, no encoder presets
     - those stay in OBS, and Nebula must never silently overwrite settings the
     user changed there."

    "Never apply mid-recording. Queue it for the next start."

The apply sequence is returned as data by plan(), so its order - which the spec
says matters - can be checked without an OBS to talk to.

    python tests/test_profiles.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import classifier as classifier_module
from obsauto import profiles
from obsauto.classifier import Classifier

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


# ---------------------------------------------------------------------------
# The scope guard
# ---------------------------------------------------------------------------
wide = {
    "enabled": True, "res": "2560x1440", "fps": 60, "encoder": "nvenc_h264",
    "bitrate_kbps": 18000, "scene": "Game Capture",
    # Everything below is outside the feature and must not survive.
    "audio_tracks": [1, 2], "filters": ["sharpen"], "output_path": "D:/elsewhere",
    "encoder_preset": "p7", "rescale": True,
}
clean = profiles.sanitise(wide)
check("the five sanctioned fields survive",
      all(clean.get(k) == wide[k] for k in profiles.FIELDS), clean)
for extra in ("audio_tracks", "filters", "output_path", "encoder_preset", "rescale"):
    check(f"{extra} is dropped", extra not in clean, clean)
check("only enabled plus the five remain",
      set(clean) <= set(profiles.FIELDS) | {"enabled"}, sorted(clean))

check("a malformed resolution is dropped, not guessed",
      "res" not in (profiles.sanitise({"res": "big"}) or {}),
      profiles.sanitise({"res": "big"}))
check("...leaving nothing worth storing",
      profiles.sanitise({"res": "big"}) is None)
check("a numeric string resolution normalises",
      profiles.sanitise({"res": "1920X1080"})["res"] == "1920x1080")
check("a nonsense fps is dropped",
      "fps" not in (profiles.sanitise({"fps": "sixty"}) or {}))
check("bitrate is clamped to the sane range",
      profiles.sanitise({"bitrate_kbps": 9_000_000})["bitrate_kbps"]
      == profiles.BITRATE_RANGE[1],
      profiles.sanitise({"bitrate_kbps": 9_000_000}))
check("an empty profile is None, not an empty dict",
      profiles.sanitise({}) is None and profiles.sanitise(None) is None)
check("a non-dict is refused", profiles.sanitise("nope") is None)

# ---------------------------------------------------------------------------
# The apply sequence - "order matters"
# ---------------------------------------------------------------------------
steps = profiles.plan(clean)
names = [s[0] for s in steps]
check("video settings come first", names[0] == "SetVideoSettings", names)
check("the scene comes last", names[-1] == "SetCurrentProgramScene", names)
check("encoder and bitrate sit between them",
      names.index("SetProfileParameter") < names.index("SetCurrentProgramScene")
      and names.index("SetProfileParameter") > 0, names)
check("resolution maps to both base and output canvas",
      steps[0][1]["baseWidth"] == steps[0][1]["outputWidth"] == 2560, steps[0][1])
check("fps goes as a numerator over 1",
      (steps[0][1]["fpsNumerator"], steps[0][1]["fpsDenominator"]) == (60, 1),
      steps[0][1])

# "SetVideoSettings - res + fps, only if changed."
same = {"baseWidth": 2560, "baseHeight": 1440, "outputWidth": 2560,
        "outputHeight": 1440, "fpsNumerator": 60, "fpsDenominator": 1}
unchanged = profiles.plan(clean, current_video=same, current_scene="Game Capture")
check("an unchanged canvas is not reset",
      "SetVideoSettings" not in [s[0] for s in unchanged],
      [s[0] for s in unchanged])
check("an unchanged scene is not switched",
      "SetCurrentProgramScene" not in [s[0] for s in unchanged],
      [s[0] for s in unchanged])
check("a changed canvas is applied",
      "SetVideoSettings" in [s[0] for s in profiles.plan(
          clean, current_video=dict(same, baseWidth=1920))])
check("no profile means no calls", profiles.plan(None) == [])


class FakeOBS:
    def __init__(self):
        self.calls = []

    def get_video_settings(self):
        return {}

    def get_current_program_scene(self):
        return "Other"

    def call(self, name, payload=None):
        self.calls.append(name)

    def set_profile_parameter(self, category, name, value):
        self.calls.append(f"param:{name}")


obs = FakeOBS()
logged = []
check("a profile applies when nothing is recording",
      profiles.apply(obs, clean, is_recording=False, on_log=logged.append) is True)
check("...and reaches OBS", obs.calls, obs.calls)
check("every change is logged as [Profile]",
      logged and all(m.startswith("[Profile]") for m in logged), logged)

obs = FakeOBS()
logged = []
check("a profile is refused mid-recording",
      profiles.apply(obs, clean, is_recording=True, on_log=logged.append) is False)
check("...and nothing is sent to OBS", obs.calls == [], obs.calls)
check("...and it says it is queued for the next start",
      any("next start" in m for m in logged), logged)

# ---------------------------------------------------------------------------
# Storage, alongside the classification
# ---------------------------------------------------------------------------
classifier_module.DATA_FILE = os.path.join(
    tempfile.mkdtemp(prefix="nebula-profiles-"), "games.json")
classifier = Classifier()
classifier.mark_game("helldivers2.exe", "Helldivers 2")

check("a game with no profile inherits the default",
      profiles.for_game(classifier, "helldivers2.exe") is None)
check("saving onto an unknown game is refused",
      profiles.save(classifier, "nope.exe", clean) is False)

check("a profile saves", profiles.save(classifier, "helldivers2.exe", clean) is True)
stored = profiles.for_game(classifier, "helldivers2.exe")
check("...and reads back", stored and stored["res"] == "2560x1440", stored)
check("the lookup is case-insensitive",
      profiles.for_game(classifier, "HELLDIVERS2.EXE") is not None)

with open(classifier_module.DATA_FILE, encoding="utf-8") as f:
    on_disk = json.load(f)
check("it lives inside the game's entry, so it syncs",
      "profile" in on_disk["games"]["helldivers2.exe"],
      on_disk["games"]["helldivers2.exe"])
check("the classification is untouched",
      on_disk["games"]["helldivers2.exe"]["display_name"] == "Helldivers 2")

# A profile that a synced file smuggled extra keys into must still be narrowed.
on_disk["games"]["helldivers2.exe"]["profile"]["output_path"] = "D:/hijack"
with open(classifier_module.DATA_FILE, "w", encoding="utf-8") as f:
    json.dump(on_disk, f)
reloaded = Classifier()
check("extra keys from a synced file are still dropped on read",
      "output_path" not in (profiles.for_game(reloaded, "helldivers2.exe") or {}),
      profiles.for_game(reloaded, "helldivers2.exe"))

check("a disabled profile is not applied",
      profiles.for_game(
          type("C", (), {"_data": {"games": {"x.exe": {
              "profile": {"enabled": False, "res": "1x1"}}}}})(), "x.exe") is None)

check("removing a profile leaves the game classified",
      profiles.save(classifier, "helldivers2.exe", None) is True
      and profiles.for_game(classifier, "helldivers2.exe") is None
      and "helldivers2.exe" in classifier._data["games"])

# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
check("the column summarises as the frame does",
      profiles.summary(clean).startswith("1440p60"), profiles.summary(clean))
check("the bitrate reads in Mb/s", "18 Mb/s" in profiles.summary(clean),
      profiles.summary(clean))
check("no profile summarises as nothing", profiles.summary(None) == "")
check("the GB/h estimate is derived from the bitrate",
      abs(profiles.estimated_gb_per_hour(18000) - 7.54) < 0.05,
      profiles.estimated_gb_per_hour(18000))
check("no bitrate means no estimate",
      profiles.estimated_gb_per_hour(None) is None)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<52} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
