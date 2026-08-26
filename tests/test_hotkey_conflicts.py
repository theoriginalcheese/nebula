"""Hotkey collision warnings in HotkeyManager.

Two actions on one physical key both fire - confusing at best (toggle AND
save replay from a single press). The manager now warns honestly. Scope of
the comparison: scancode-to-scancode and name-to-name. A scancode vs a
name is deliberately NOT flagged - resolving a name to a scancode is
layout-dependent, the exact "`"-vs-apostrophe trap hotkey.py documents.

    python tests/test_hotkey_conflicts.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import hotkey as hotkey_mod
from spike.host import HotkeyManager

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class FakeKeyboard:
    def __init__(self):
        self.added = 0

    def add_hotkey(self, *a, **k):
        self.added += 1
        return f"h{self.added}"

    def remove_hotkey(self, handle):
        return True


hotkey_mod.keyboard = FakeKeyboard()
hotkey_mod._AVAILABLE = True

logs = []
hm = HotkeyManager(on_log=logs.append)

# Different scancodes: no warning.
hm.bind("toggle", "f6", lambda: None, scancode=41)
hm.bind("replay", "f9", lambda: None, scancode=67)
check("distinct scancodes stay silent",
      not any("share" in m for m in logs), logs)

# Same scancode via rebinding: warn once per new claimant.
logs.clear()
hm.bind("palette", "x", lambda: None, scancode=41)
check("same scancode warns", any("share" in m and "'toggle' and 'palette'" in m
                                 for m in logs), logs)
# Rebinding the SAME action to the same key must not self-warn.
logs.clear()
hm.bind("palette", "x", lambda: None, scancode=41)
check("same action rebind doesn't self-warn",
      not any("share" in m for m in logs), logs)

# Name-vs-name collisions are caught too.
logs.clear()
hm2 = HotkeyManager(on_log=logs.append)
hm2.bind("toggle", "ctrl+alt+r", lambda: None)
hm2.bind("replay", "CTRL+ALT+R", lambda: None)
check("names compare case-insensitively",
      any("share" in m for m in logs), logs)

# Unbind releases the claim (replay still holds it - so first prove that
# a remaining holder still warns, then free both).
logs.clear()
hm2.bind("palette", "ctrl+alt+r", lambda: None)
check("remaining holder still warns",
      any("'replay' and 'palette' share" in m for m in logs), logs)
hm2.unbind("toggle")
hm2.unbind("replay")
logs.clear()
hm2.bind("palette", "ctrl+alt+r", lambda: None)
check("unbound actions free their key",
      not any("share" in m for m in logs), logs)

# Scancode vs name: cannot be proven layout-independent - no false alarm.
logs.clear()
hm3 = HotkeyManager(on_log=logs.append)
hm3.bind("toggle", "f6", lambda: None)
hm3.bind("replay", "whatever", lambda: None, scancode=41)
check("scancode vs name is not flagged", not any("share" in m for m in logs),
      logs)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<46} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} "
      f"({len(results)} checks)")
sys.exit(0 if passed_all else 1)
