"""The game-start watcher decides from files and a process snapshot.

    python tests/test_nebula_on_game.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import nebula_on_game as watch

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


def main():
    data = {
        "games": {"ZenlessZoneZero.exe": {}, "7 billion humans.exe": {}},
        "non_games": {"notepad.exe": {}},
    }
    names = watch.game_exes(data)
    check("games are lowercased", "zenlesszonezero.exe" in names)
    check("spaced names survive", "7 billion humans.exe" in names)
    check("non-games do not wake it", "notepad.exe" not in names)
    check("bad payload still watches cs2", watch.game_exes(None) == {"cs2.exe"})
    check("list payload still watches cs2", watch.game_exes({"games": []}) == {"cs2.exe"})

    check("launch when a game is up and Nebula is not",
          watch.should_launch("zenlesszonezero.exe", False, 10, 0))
    check("no launch while Nebula holds the mutex",
          not watch.should_launch("zenlesszonezero.exe", True, 10, 0))
    check("no launch with nothing running",
          not watch.should_launch("", False, 10, 0))
    check("cooldown blocks a second start",
          not watch.should_launch("zenlesszonezero.exe", False, 10, 15))

    running = {"explorer.exe", "zenlesszonezero.exe", "notepad.exe"}
    check("match is a game exe",
          watch.matching_game(running, names) == "zenlesszonezero.exe")
    check("cs2 outranks another open game",
          watch.matching_game(
              running | {"cs2.exe"}, names) == "cs2.exe")
    check("cs2 wakes nebula with an empty list",
          watch.matching_game({"cs2.exe"}, set()) == "cs2.exe")
    check("no match is empty",
          watch.matching_game({"notepad.exe"}, names) == "")

    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        repo = os.path.join(tmp, "repo")
        os.makedirs(home)
        os.makedirs(repo)
        with open(os.path.join(repo, "config.json"), "w", encoding="utf-8") as handle:
            json.dump({"sync_folder": "OneDrive/ObsAutoFolder"}, handle)
        path = watch.games_json_path(repo, home=home)
        expect = os.path.join(home, "OneDrive", "ObsAutoFolder", "games.json")
        check("relative sync folder hangs off home", os.path.normcase(path) == os.path.normcase(expect))

        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        loaded = watch.load_game_exes(path)
        check("load reads the synced list", "zenlesszonezero.exe" in loaded)
        check("missing file still watches cs2",
              watch.load_game_exes(os.path.join(tmp, "nope.json")) == {"cs2.exe"})

    live = watch.running_exes()
    me = os.path.basename(sys.executable).lower()
    check("process snapshot sees this interpreter", me in live, me)

    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
