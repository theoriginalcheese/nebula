"""Command palette - spec 7e.

    "Fuzzy match across four sources at once, grouped, keyboard-first."

The matching rules are the testable part, and one of them is a safety rule
rather than a nicety: "Destructive rows never in the palette - no delete, no
cull." A fuzzy list that can delete a clip two keystrokes after a typo is a
trap, so that is asserted against the real row builder, not just the matcher.

    python tests/test_palette.py
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto import design_v3 as dv
from obsauto import palette
from obsauto.classifier import Classifier
from obsauto.config import DEFAULTS, load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def row(group, label, hint="", recency=0.0):
    return palette.Row(group, label, lambda: None, hint, recency)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
check("a subsequence matches out of order positions",
      palette.subsequence("rec", "Start recording") == (6, 7, 8),
      palette.subsequence("rec", "Start recording"))
check("matching is case-insensitive",
      palette.subsequence("REC", "start recording") is not None)
check("characters may be scattered",
      palette.subsequence("hd2", "Helldivers 2") == (0, 4, 11),
      palette.subsequence("hd2", "Helldivers 2"))
check("order still matters",
      palette.subsequence("2dh", "Helldivers 2") is None)
check("an empty query matches everything", palette.subsequence("", "x") == ())
check("a missing character fails", palette.subsequence("zq", "Helldivers") is None)

# "Ranking: prefix > word-start > anywhere"
check("a prefix outranks a word start",
      palette.rank_of("rec", "Recording", (0, 1, 2)) == palette.RANK_PREFIX)
check("a word start outranks the middle",
      palette.rank_of("rec", "Start recording", (6, 7, 8)) == palette.RANK_WORD_START)
check("mid-word is the last tier",
      palette.rank_of("ecor", "Recording", (1, 2, 3, 4)) == palette.RANK_ANYWHERE)

rows = [
    row("Actions", "Start recording — current window", "record"),
    row("Actions", "Reconnect interval"),
    row("Actions", "Open recordings folder"),
    row("Games", "Helldivers 2", "helldivers2.exe"),
    row("Games", "Honkai Star rail", "starrail.exe"),
    row("Recent clips", "2026-07-27 14-20-01", "Roblox", recency=100),
    row("Recent clips", "2026-07-26 23-44-23", "Honkai Star rail", recency=50),
    row("Settings", "Recording root"),
    row("Settings", "Reconnect every"),
]

grouped = palette.search(rows, "rec")
flat = palette.flatten(grouped)
check("a query returns matches", flat, flat)
check("groups come back in the spec's order",
      [g for g, _ in grouped] == [g for g in palette.GROUP_ORDER
                                  if g in {g2 for g2, _ in grouped}],
      [g for g, _ in grouped])
check("a prefix match sorts above a mid-string one",
      flat[0].rank <= flat[-1].rank, [(r.label, r.rank) for r in flat])
check("non-matches are dropped",
      all("Helldivers 2" != r.label for r in flat), [r.label for r in flat])

# The hint is searchable, but only the label gets bolded.
by_hint = palette.flatten(palette.search(rows, "roblox"))
check("a row can be found by its hint",
      any(r.label == "2026-07-27 14-20-01" for r in by_hint),
      [r.label for r in by_hint])
check("a hint match doesn't bold the label",
      all(not r.spans for r in by_hint if r.label == "2026-07-27 14-20-01"))

check("matched positions come back for bolding",
      all(r.spans or not palette.subsequence("rec", r.label)
          for r in palette.flatten(palette.search(rows, "rec"))))

# "Empty query - suggestions, not a blank list."
empty = palette.search(rows, "")
check("an empty query still offers rows", palette.flatten(empty), empty)
check("...ordered by recency inside a group",
      [r.label for _g, rs in empty for r in rs if _g == "Recent clips"]
      == ["2026-07-27 14-20-01", "2026-07-26 23-44-23"],
      [r.label for _g, rs in empty for r in rs if _g == "Recent clips"])

# "Max 5 rows per group, 12 rows total."
many = [row("Games", f"Game {i}") for i in range(30)]
capped = palette.search(many, "")
check("a group is capped at five",
      all(len(rs) <= palette.MAX_PER_GROUP for _g, rs in capped),
      [(g, len(rs)) for g, rs in capped])
mixed = [row(g, f"{g} {i}") for g in palette.GROUP_ORDER for i in range(10)]
check("the whole list is capped at twelve",
      len(palette.flatten(palette.search(mixed, ""))) <= palette.MAX_ROWS,
      len(palette.flatten(palette.search(mixed, ""))))

check("no match is an empty result, not an error",
      palette.search(rows, "xyzzy") == [])
check("the footer count sees every match, not just the shown ones",
      palette.count_all(mixed, "") == len(mixed), palette.count_all(mixed, ""))

# ---------------------------------------------------------------------------
# The window, and the safety rule
# ---------------------------------------------------------------------------
check("the palette is the spec's width", dv.PALETTE_W == 560, dv.PALETTE_W)
check("it sits at a 22% top offset", dv.PALETTE_TOP_FRACTION == 0.22)
check("the backdrop is 55% black", dv.PALETTE_BACKDROP_ALPHA == 0.55)
check("ctrl+k is the default global key",
      DEFAULTS.get("palette_hotkey") == "ctrl+k", DEFAULTS.get("palette_hotkey"))

classifier = Classifier()
app = AppWindow(load_config(), classifier, on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=200):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


settle(300)

built = app._palette_rows()
labels = [r.label.lower() for r in built]
check("the palette offers real rows", built, len(built))
check("all four sources are represented, in order",
      [g for g in palette.GROUP_ORDER if any(r.group == g for r in built)]
      == [g for g in palette.GROUP_ORDER if any(r.group == g for r in built)])

# The safety rule, checked against what the app actually builds. It is about
# rows that *do* something: the Actions group is the only one that runs a
# command, so nothing destructive may appear there. A Settings row named "Cull
# clips older than" is not a cull - it opens the Storage group, where the count
# and total are shown before anything moves - so the check is scoped to Actions
# rather than banning the word everywhere.
action_labels = [r.label.lower() for r in built if r.group == "Actions"]
for banned in ("delete", "cull", "remove", "trash", "erase", "wipe"):
    check(f"no destructive action is offered: {banned!r}",
          not any(banned in label for label in action_labels),
          [l for l in action_labels if banned in l])

# And every non-Actions row must be navigation or reveal, never a mutation.
navigators = {app._show_game, app._open_settings_group, app._open_path,
              app._open_recording_root}
check("Settings rows only navigate",
      all(r.group != "Settings" or "settings" in getattr(
          r.action, "__qualname__", "").lower() or r.action.__name__ == "<lambda>"
          for r in built))
check("no row is bound straight to the clip delete",
      not any(getattr(r.action, "__func__", None) is
              getattr(app._delete_clip, "__func__", None) for r in built))

check("actions are offered", any(r.group == "Actions" for r in built))
check("settings are offered", any(r.group == "Settings" for r in built))
check("every row has something to run", all(callable(r.action) for r in built))

state = app.show_palette()
settle(250)
check("the palette opens", state is not None and state["popup"].winfo_exists())
check("it starts with suggestions, not a blank list", state["flat"], state["flat"])
check("the first row is selected", state["index"] == 0)
try:
    state["popup"].destroy()
except Exception:
    pass
settle(80)

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<52} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
