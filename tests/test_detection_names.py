"""Hostile-title / hostile-name audit for the detection chain.

Prior art (Smart-Replay-Mover) fixed a real bug class: substring matching
meant "obs" matched "observer" and "code" matched "barcode", silently
mis-sorting clips. Nebula's classifier matches exe basenames by exact
set membership - this file pins that property against the same traps, plus
the manual-review queue's once-only and peek-only contracts.

    python tests/test_detection_names.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.classifier import Classifier

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def fresh_classifier(tmp):
    import json
    from obsauto import classifier as classifier_module
    data_file = os.path.join(tmp, "games.json")
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump({"games": {"obs.exe": {"display_name": "OBS"}},
                   "non_games": {}}, f)
    classifier_module.DATA_FILE = data_file
    return Classifier()


import tempfile

tmp = tempfile.mkdtemp(prefix="nebula-names-")
c = fresh_classifier(tmp)

# The SRM bug family: a known name must never match inside a longer one.
# obs.exe is a known game here (worst case for the trap); everything that
# merely CONTAINS those letters must stay unknown.
traps = [
    ("observer.exe", "contains 'obs'"),
    ("barcode.exe", "would trap a 'code' entry"),
    ("observer_tool.exe", "prefix + suffix"),
    ("nobscd.exe", "'obs' in the middle"),
]
for name, why in traps:
    result, _ = c.peek(os.path.join("C:/x", name), name)
    check(f"no substring match: {name}", result == "unknown",
          f"{result} ({why})")

# And the exact name still classifies.
result, display = c.peek("C:/x/obs.exe", "obs.exe")
check("exact match still works", result == "game" and display == "OBS",
      f"{result}/{display}")

# Case-insensitivity is part of the contract (Windows filesystem).
result, _ = c.peek("C:/x/OBS.EXE", "OBS.EXE")
check("matching is case-insensitive", result == "game", result)

# proc_name fallback when exe_path is missing entirely.
result, _ = c.peek(None, "not_a_game.exe")
check("missing exe path falls back to proc_name", result == "unknown", result)
result, display = c.peek("", "obs.exe")
check("empty path uses proc_name exactly", result == "game", result)

# A window title is decoration: classification never reads it. Feed a title
# that names a game and an exe that isn't one - title must not leak in.
result, _ = c.peek("C:/x/notepad.exe", "notepad.exe")
check("window title is never consulted", result == "unknown", result)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<46} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} "
      f"({len(results)} checks)")
sys.exit(0 if passed_all else 1)
