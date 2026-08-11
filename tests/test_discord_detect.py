"""Discord active-call detection — honest False when unknown.

    python tests/test_discord_detect.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import discord_detect as dd

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def run():
    dd._reset_cache_for_tests()

    check("title Voice Connected matches",
          dd._title_says_call("Voice Connected - Discord"))
    check("title ordinary Discord does not match",
          not dd._title_says_call("@Orientate - Discord"))
    check("title empty does not match", not dd._title_says_call(""))

    check("name Voice Connected matches",
          dd._name_says_call("Voice Connected"))
    check("name Return to Call matches",
          dd._name_says_call("Return to Call"))
    check("name Mute alone does not match",
          not dd._name_says_call("Mute"))
    check("name Discord settings does not match",
          not dd._name_says_call("User Settings"))

    # With Discord maybe running locally: never crash, and never invent True
    # from "process exists" alone. (If Anthony is mid-call this may be True —
    # that's fine; we only assert the probe returns a bool.)
    dd._reset_cache_for_tests()
    live = dd.discord_voice_active(force=True)
    check("discord_voice_active returns bool", isinstance(live, bool), live)

    # Cache returns the same value within TTL.
    again = dd.discord_voice_active(force=False)
    check("cache returns same bool", again is live or again == live, (live, again))

    # Force-clear + fake empty pids → False (honest unknown / absent).
    dd._reset_cache_for_tests()
    real_pids = dd._discord_pids
    dd._discord_pids = lambda: set()
    try:
        check("no Discord process -> False",
              dd.discord_voice_active(force=True) is False)
    finally:
        dd._discord_pids = real_pids
        dd._reset_cache_for_tests()


run()
passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
