"""The Games pane has a visible way in - frame 2d, plus the reported bugs.

Two complaints drove this: "I cant rescan for games" and "nor can I change non
games into games". Neither was a logic bug. Rescan works perfectly and reports
`[Steam] Found 0 Steam game(s)` because this machine's Steam library really is
empty - the games come from HoYoPlay, Roblox and CurseForge. And promotion
worked too, but only on right-click, with nothing on screen saying so, which
from the outside is the same as not existing.

So the assertions here are about *reachability*, not just behaviour: an ignored
row carries a visible button, and there is a path into the game list that
doesn't go through Steam.

    python tests/test_games_pane.py
"""
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import classifier as classifier_module
from obsauto import config as config_module
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

# Never touch the real games.json. A debug run once wrote a junk entry into it
# and the first cleanup silently failed, because Classifier._save() merges with
# whatever is on disk - so popping the key in memory and saving put it straight
# back (CLAUDE.md).
classifier_module.DATA_FILE = os.path.join(
    tempfile.mkdtemp(prefix="nebula-games-"), "games.json")

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def buttons_in(frame):
    import customtkinter as ctk
    return [w for w in walk(frame) if isinstance(w, ctk.CTkButton)]


classifier = Classifier()
classifier.mark_game("helldivers2.exe", "Helldivers 2")
classifier.mark_non_game("chrome.exe")
classifier.mark_non_game("discord.exe")

app = AppWindow(load_config(), classifier, on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))

app._show_view("games")
app._refresh_games()
app.root.update()

# --- the promote affordance is visible, not just bound -----------------------
ignored_rows = app._nongames_list.winfo_children()
check("ignored apps are listed", len(ignored_rows) == 2, len(ignored_rows))

promote_buttons = buttons_in(app._nongames_list)
check("every ignored row carries a visible button",
      len(promote_buttons) == len(ignored_rows),
      f"{len(promote_buttons)} buttons for {len(ignored_rows)} rows")
labels = {b.cget("text") for b in promote_buttons}
check("the button says what it does", labels == {"Make a game"}, labels)

# It must actually promote. _promote_non_game asks for confirmation, then a
# display-name dialog, so stub both rather than the action - the action is
# the thing under test.
import tkinter.messagebox
tkinter.messagebox.askyesno = lambda *a, **k: True
app._ask_display_name = lambda *a, **k: "Discord"
app._promote_non_game("discord.exe")
app.root.update()
check("promoting moves the app into games",
      "discord.exe" in classifier._data.get("games", {}),
      sorted(classifier._data.get("games", {})))
check("promoting removes it from non-games",
      "discord.exe" not in classifier._data.get("non_games", {}),
      sorted(classifier._data.get("non_games", {})))
check("the list redraws without the promoted app",
      len(app._nongames_list.winfo_children()) == 1,
      len(app._nongames_list.winfo_children()))

# --- a way in that isn't Steam ----------------------------------------------
# CTkButton is a CTkFrame subclass, so winfo_class() reports "Frame" - the
# lookup has to be by type, not by Tk class name.
header_labels = {b.cget("text") for b in buttons_in(app.root)}
check("the pane offers a non-Steam way to add a game",
      "Add a game" in header_labels, sorted(t for t in header_labels if t))
check("Rescan names Steam, so an empty result reads as an empty library",
      "Rescan Steam" in header_labels, sorted(t for t in header_labels if t))

# --- the picker filters sensibly --------------------------------------------
gui.list_visible_windows = lambda: [
    (1, r"C:\g\hd2.exe", "helldivers2.exe", "Helldivers 2", "UnityWnd"),
    (2, r"C:\zzz\zzz.exe", "ZenlessZoneZero.exe", "Zenless Zone Zero", "UnityWnd"),
    (3, r"C:\zzz\zzz.exe", "ZenlessZoneZero.exe", "ZZZ", "UnityWnd"),
    (4, r"C:\w\explorer.exe", "explorer.exe", "File Explorer", "CabinetWClass"),
    (5, r"C:\c\chrome.exe", "chrome.exe", "Some tab", "Chrome_WidgetWin_1"),
    (6, r"C:\o\obs64.exe", "obs64.exe", "OBS 30.2", "Qt5152QWindowIcon"),
    (7, r"C:\n\thing.exe", "thing.exe", "", "X"),
]
candidates = app._running_candidates()
names = [proc for proc, _title in candidates]
check("already-classified apps are filtered out",
      "helldivers2.exe" not in names and "chrome.exe" not in names, names)
check("the shell and OBS are filtered out",
      "explorer.exe" not in names and "obs64.exe" not in names, names)
check("a window with no title is skipped", "thing.exe" not in names, names)
check("an unclassified running game is offered",
      "ZenlessZoneZero.exe" in names, names)
check("one row per executable, not per window", len(names) == len(set(names)), names)
titles = dict(candidates)
check("it keeps the longest window title as the name suggestion",
      titles.get("ZenlessZoneZero.exe") == "Zenless Zone Zero",
      titles.get("ZenlessZoneZero.exe"))

# The window title is what gets offered as the folder name - "Zenless Zone
# Zero" is a far better folder than the exe stem "ZenlessZoneZero".
seen = {}
app._ask_display_name = lambda basename, suggestion=None: seen.setdefault(
    "suggestion", suggestion)
check("the picker seeds the folder name from the window title",
      app._ask_display_name("ZenlessZoneZero.exe", "Zenless Zone Zero")
      == "Zenless Zone Zero", seen)

# --- existing damage heals itself on load -----------------------------------
# starrail.exe was filed as both a game and a non-game in two of the three real
# game lists on this machine, which is what the old union merge produced.
import json

with open(classifier_module.DATA_FILE, "w", encoding="utf-8") as f:
    json.dump({"games": {"starrail.exe": {"display_name": "Honkai Star Rail",
                                          "source": "manual"}},
               "non_games": {"starrail.exe": True, "chrome.exe": True}}, f)
healed = Classifier()
check("an app filed in both buckets is repaired on load",
      "starrail.exe" not in healed._data["non_games"],
      sorted(healed._data["non_games"]))
check("healing keeps it as the game it was promoted to",
      "starrail.exe" in healed._data["games"], sorted(healed._data["games"]))
check("healing leaves genuine non-games alone",
      "chrome.exe" in healed._data["non_games"], sorted(healed._data["non_games"]))

healed.mark_non_game("zzz.exe")   # any save persists the repair
with open(classifier_module.DATA_FILE, encoding="utf-8") as f:
    on_disk = json.load(f)
check("the repair reaches the file, so it doesn't come back",
      "starrail.exe" not in on_disk["non_games"], sorted(on_disk["non_games"]))

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<52} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
