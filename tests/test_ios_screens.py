"""The iOS app contains the build-spec screens and keeps secrets off the phone binary.

    python tests/test_ios_screens.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IOS = os.path.join(ROOT, "ios")

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def files():
    found = []
    for dirpath, _dirs, names in os.walk(IOS):
        for name in names:
            if name.endswith(".swift"):
                found.append(os.path.join(dirpath, name))
    return found


TEXT = "\n".join(open(path, encoding="utf-8").read() for path in files())

for phrase in (
    "Pair with your PC",
    "Ready when you are",
    "Is this a game?",
    "Stream to this phone",
    "Delete this clip from Studio PC and nas-vault?",
    "Save as new clip",
    "Steam auto-classifies",
    "When a game launches",
    "It’s a game —",
    "Studio PC is offline",
    "OBS isn’t connected on Studio PC",
    "Launch on PC",
    "Earth",
    "Moonrise",
    "Solar live",
    "kSecClassGenericPassword",
    "clip.delete",
    "session.start",
    "app.classify",
):
    check("ios app contains %s" % phrase, phrase in TEXT)

check(
    "the only file removal is a temporary share copy",
    TEXT.count("removeItem") == 1 and "temporaryDirectory" in TEXT,
)
check("phone preferences are not in the keychain store", "UserDefaults" not in TEXT)

passed_all = all(ok for _, ok, _ in results)
for name, ok, detail in results:
    print("%s  %-62s %s" % ("PASS" if ok else "FAIL", name, detail))
print("\n%s (%d checks)" % ("ALL PASS" if passed_all else "FAILURES PRESENT", len(results)))
sys.exit(0 if passed_all else 1)
