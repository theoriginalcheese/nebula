"""Fresh-install defaults, and that a friend build doesn't ship home-network hints.

    python tests/test_friend_first_run.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import config as config_mod
from obsauto import monitor as mon
from obsauto import settings_spec
from spike.app import start_hidden_for

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


root = config_mod.default_recording_root().replace("\\", "/")
check("default clips folder is Videos/Nebula",
      root.endswith("/Videos/Nebula"), root)
check("DEFAULTS uses that folder",
      config_mod.DEFAULTS["recording_root"].replace("\\", "/") == root)
check("fresh idle is not four seconds",
      int(config_mod.DEFAULTS["idle_timeout_seconds"]) >= 30)
check("fresh hotkey is not a bare backtick",
      config_mod.DEFAULTS["toggle_hotkey"] != "`"
      and config_mod.DEFAULTS["toggle_hotkey_scancode"] is None)

check("setup shows the window", start_hidden_for(["Nebula.exe"], True) is False)
check("later launches stay in the tray", start_hidden_for(["Nebula.exe"], False) is True)
check("--show still opens", start_hidden_for(["Nebula.exe", "--show"], False) is False)

hints = "\n".join((f.hint or "") for f in settings_spec.FIELDS)
banned = (
    "192.168.68.59",
    "100.84.207.58",
    "100.90.134.9",
    "tail25e601",
    "mum's",
    "dad's",
    "alien-pc",
)
for needle in banned:
    check("settings hint has no %s" % needle, needle not in hints.lower() and needle not in hints)

shipped = []
for base in ("obsauto", "spike"):
    for dirpath, _dirs, files in os.walk(base):
        if "web" in dirpath.replace("\\", "/").split("/"):
            continue
        for name in files:
            if name.endswith(".py"):
                shipped.append(os.path.join(dirpath, name))
blob = []
for path in shipped:
    with open(path, encoding="utf-8") as fh:
        blob.append(fh.read())
source = "\n".join(blob)
for needle in banned:
    check("shipped python has no %s" % needle, needle not in source)


class _Cls:
    def __init__(self):
        self.queued = []
        self._seen = set()

    def classify(self, path, name):
        return "unknown", None

    def queue_for_manual_review(self, basename):
        self.queued.append(basename)
        if basename in self._seen:
            return False
        self._seen.add(basename)
        return True

    def display_lookup(self, name):
        return None


asked = []
cls = _Cls()
fg = (1, r"D:\Games\coolgame.exe", "coolgame.exe", "Cool Game", "UnityWndClass")
visible = [
    fg,
    (2, r"C:\Apps\spotify.exe", "spotify.exe", "Spotify", "Chrome"),
]
orig_fg = mon.get_foreground_window_info
orig_vis = mon.list_visible_windows
try:
    mon.get_foreground_window_info = lambda: fg
    mon.list_visible_windows = lambda: visible
    watcher = mon.Monitor(
        object(), cls, {"recording_root": "C:/tmp/nebula-friend-test"},
        on_unknown_app=lambda basename, label: asked.append((basename, label)),
    )
    first = watcher._find_new_game_target()
    second = watcher._find_new_game_target()
finally:
    mon.get_foreground_window_info = orig_fg
    mon.list_visible_windows = orig_vis

check("unknown foreground is not recorded yet", first is None and second is None)
check("background apps are not queued",
      cls.queued == ["coolgame.exe", "coolgame.exe"], cls.queued)
check("the toast fires once", asked == [("coolgame.exe", "Cool Game")], asked)


class _Mix(_Cls):
    def classify(self, path, name):
        if (path or "").lower().endswith("eldenring.exe"):
            return "game", "Elden Ring"
        return "unknown", None


mix = _Mix()
mix_asked = []
chat = (3, r"C:\Apps\discord.exe", "discord.exe", "Discord", "Chrome")
game = (4, r"D:\Games\eldenring.exe", "eldenring.exe", "Elden Ring", "UnityWndClass")
orig_remember = mon.app_icons.remember
try:
    mon.app_icons.remember = lambda *args, **kwargs: None
    mon.get_foreground_window_info = lambda: chat
    mon.list_visible_windows = lambda: [chat, game]
    watcher = mon.Monitor(
        object(), mix, {"recording_root": "C:/tmp/nebula-friend-test"},
        on_unknown_app=lambda basename, label: mix_asked.append((basename, label)),
    )
    picked = watcher._find_new_game_target()
finally:
    mon.get_foreground_window_info = orig_fg
    mon.list_visible_windows = orig_vis
    mon.app_icons.remember = orig_remember

check("a visible game still wins",
      picked is not None and picked[2] == "Elden Ring", picked)
check("discord is not asked while that game is up",
      mix.queued == [] and mix_asked == [], (mix.queued, mix_asked))

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print("[%s] %s" % (mark, name) + ((" — %s" % detail) if detail and not passed else ""))
    if not passed:
        failed += 1
print("\n%d/%d passed" % (len(results) - failed, len(results)))
sys.exit(1 if failed else 0)
