"""Classifier.peek answers from cache only - never Steam, never network.

note_manual_stop runs on the Tk thread. Its target lookup used full
classify(), whose lazy refresh_steam_index() can issue a synchronous
Steam Store request (classify_appid) and freeze the window on Stop.
peek() is the UI-thread contract: known games/non-games and an
already-loaded Steam index answer instantly; anything that would need a
scan returns ("unknown", None) instead of blocking.

    python tests/test_classifier_peek.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import classifier as classifier_mod

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def fresh(tmp):
    c = classifier_mod.Classifier.__new__(classifier_mod.Classifier)
    import threading
    c._lock = threading.RLock()
    c._data = {"games": {}, "non_games": {}}
    c._steam_index = {}
    c._steam_index_loaded = False
    return c


# --- known classifications answer without any index --------------------------
c = fresh(None)
c._data["games"]["helldivers2.exe"] = {"display_name": "Helldivers 2"}
c._data["non_games"]["discord.exe"] = {"display_name": ""}

result = c.peek(r"C:\Games\Helldivers 2\helldivers2.exe", "helldivers2.exe")
check("known game peeks as game", result == ("game", "Helldivers 2"), result)

result = c.peek("", "discord.exe")
check("known non-game peeks as non_game", result == ("non_game", None), result)

# --- unloaded index must NOT trigger the Steam scan --------------------------
scanned = {"n": 0}


def _boom(*a, **k):
    scanned["n"] += 1
    raise AssertionError("refresh_steam_index must not run on peek()")


c.refresh_steam_index = _boom
result = c.peek(r"C:\Whatever\newgame.exe", "newgame.exe")
check("unloaded index declines to unknown",
      result == ("unknown", None), result)
check("steam scan was not triggered", scanned["n"] == 0, scanned["n"])

# --- loaded index answers installdir hits, still offline ---------------------
c._steam_index_loaded = True
c._steam_index = {"elden ring": "ELDEN RING"}
c._steam_installdir_for_path = lambda exe_path: (
    "elden ring" if "elden ring" in (exe_path or "").lower() else None)

result = c.peek(r"D:\Steam\elden ring\start.exe", "start.exe")
check("loaded index hit peeks as game", result == ("game", "ELDEN RING"), result)

result = c.peek(r"C:\Temp\random.exe", "random.exe")
check("loaded index miss stays unknown", result == ("unknown", None), result)

print("\n%d checks" % len(results))
failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print("%-4s %-46s %s" % ("PASS" if ok else "FAIL", name, detail))
if failed:
    print("FAILURES PRESENT (%d checks)" % (len(results) - len(failed)))
    sys.exit(1)
print("ALL PASS")
