"""Classifier AppID + sighting counter — frame 2d / hero source (no GUI).

    python3 tests/test_classifier_appid.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import classifier as classifier_module
from obsauto.classifier import Classifier

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


with tempfile.TemporaryDirectory() as tmp:
    data_file = os.path.join(tmp, "games.json")
    classifier_module.DATA_FILE = data_file

    c = Classifier(on_log=lambda _m: None)
    c.mark_game("helldivers2.exe", "Helldivers 2", source="steam", appid="553850")
    check("appid stored on game entry",
          c.appid_for("helldivers2.exe") == "553850",
          c.appid_for("helldivers2.exe"))
    check("snapshot carries appid",
          c.snapshot()["games"]["helldivers2.exe"].get("appid") == "553850")

    c.mark_game("helldivers2.exe", "Helldivers 2", source="manual")
    check("re-mark without appid keeps prior AppID",
          c.appid_for("helldivers2.exe") == "553850")

    check("peek_kind game", c.peek_kind("helldivers2.exe") == "game")
    check("peek_kind denylist", c.peek_kind("chrome.exe") == "non_game")
    check("peek_kind unknown", c.peek_kind("vintagestory.exe") == "unknown")

    c._sighting_gap = 0.0  # no debounce for the test
    assert c.queue_for_manual_review("vintagestory.exe")
    check("first queue counts as seen 1", c.sighting_count("vintagestory.exe") == 1)
    assert not c.queue_for_manual_review("vintagestory.exe")
    check("re-notice bumps seen", c.sighting_count("vintagestory.exe") == 2)

    taken = c.take_pending_review("vintagestory.exe")
    check("take_pending_review returns the item", taken and taken[0] == "vintagestory.exe")
    c.finish_review("vintagestory.exe")
    check("finish_review clears sightings", c.sighting_count("vintagestory.exe") == 0)

    # Steam index normalisation — dict and legacy string both work.
    c._steam_index = {
        "helldivers 2": {"name": "Helldivers 2", "appid": "553850"},
        "legacy": "Legacy Name",
    }
    name, appid = c._steam_entry("helldivers 2")
    check("steam entry dict", (name, appid) == ("Helldivers 2", "553850"))
    name, appid = c._steam_entry("legacy")
    check("steam entry legacy string", (name, appid) == ("Legacy Name", None))


passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<46} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
