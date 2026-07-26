"""The tray surface must obey frame 2j - it's one of the three the spec calls out.

    "The three surfaces the last build got wrong. Read the rules under each
     frame literally."

So this asserts the rules literally: the icon reflects state, the tooltip is
game + elapsed, Quit exists only in the tray menu, and both window buttons hide
rather than exit. Drives AppWindow's real state rather than mocking it.

Needs a desktop session; no OBS and no tray registration required - the menu is
built against a stub icon so nothing touches the real notification area.

    python tests/test_tray.py
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow
from obsauto.icon_art import TRAY_STATES, generate_state_icons

config_module.save_config = lambda *a, **k: None

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


class StubIcon:
    """Stands in for the pystray icon - same attributes gui.py touches."""
    def __init__(self):
        self.icon = None
        self.title = ""
        self._nebula_icons = generate_state_icons(size=32)


app.tray_icon = StubIcon()


def set_state(connected, recording=False, paused=False, game=None, elapsed=""):
    app._obs_connected = connected
    app._is_recording = recording
    app._is_paused = paused
    app._current_game = game
    app._tray_elapsed = elapsed
    app._update_tray_tooltip()
    return app.tray_status()


# ---- icon states: idle = accent outline, recording = ember filled,
#      disconnected = neutral with a slash ----
check("three tray icon states exist", set(TRAY_STATES) ==
      {"idle", "recording", "disconnected"}, TRAY_STATES)

icons = generate_state_icons(size=32)
check("each tray state renders a distinct image",
      len({i.tobytes() for i in icons.values()}) == 3)
# The slash has to survive the shrink to a real tray size - a colour-only
# difference would be indistinguishable at 16px.
small = {k: v.resize((16, 16)).tobytes() for k, v in icons.items()}
check("states stay distinct at 16px", len(set(small.values())) == 3)

status = set_state(connected=False)
check("disconnected state selected", status["state"] == "disconnected", status["state"])
check("disconnected icon pushed", app._tray_icon_state == "disconnected",
      app._tray_icon_state)

status = set_state(connected=True)
check("idle state when connected and not recording", status["state"] == "idle",
      status["state"])
check("idle icon pushed", app._tray_icon_state == "idle", app._tray_icon_state)

status = set_state(connected=True, recording=True, game="Helldivers 2",
                   elapsed="01:47:22")
check("recording state selected", status["state"] == "recording", status["state"])
check("recording icon pushed", app._tray_icon_state == "recording",
      app._tray_icon_state)

# "Tooltip = game + elapsed."
check("tooltip carries the game", "Helldivers 2" in app.tray_icon.title,
      app.tray_icon.title.replace("\n", " | "))
check("tooltip carries the elapsed time", "01:47:22" in app.tray_icon.title,
      app.tray_icon.title.replace("\n", " | "))
check("tooltip within the Windows 127-char limit", len(app.tray_icon.title) <= 127,
      len(app.tray_icon.title))

# A paused recording is still live as far as the tray icon is concerned, but the
# menu must offer Resume rather than Pause.
status = set_state(connected=True, recording=True, paused=True, game="Helldivers 2",
                   elapsed="01:47:22")
check("paused reports its own state", status["state"] == "paused", status["state"])
check("paused keeps the recording icon", app._tray_icon_state == "recording",
      app._tray_icon_state)

# ---- the menu (built against the stub, never registered) ----
import pystray
from obsauto.tray_app import build_tray_icon

built = {}
real_icon_cls = pystray.Icon


class CapturedIcon:
    def __init__(self, name, image, title, menu):
        built.update(name=name, image=image, title=title, menu=menu)
        self.visible = False
        self.icon = image
        self.title = title
        self.menu = menu

    def run(self):
        pass

    def stop(self):
        pass


pystray.Icon = CapturedIcon
try:
    build_tray_icon(app, None)
finally:
    pystray.Icon = real_icon_cls

items = list(built["menu"])


def labels():
    out = []
    for item in items:
        try:
            out.append(str(item.text))
        except Exception:
            out.append("")
    return out


text = labels()
check("menu built", bool(items), len(items))

# "Quit exists only in this menu."
check("Quit is in the tray menu", any("Quit" in t for t in text), text)

# "The header block is not a menu item - not hoverable, not clickable."
# A Win32 menu can only hold items, so the equivalent is a disabled one.
header = [i for i in items if str(i.text) in (app.tray_status()["heading"],
                                              app.tray_status()["detail"])]
check("header block present", len(header) >= 1, [str(i.text) for i in header])
check("header block is not clickable", all(not i.enabled for i in header))

# "Single click = show window."
defaults = [i for i in items if i.default]
check("exactly one default item", len(defaults) == 1, [str(i.text) for i in defaults])
check("single click shows the window", defaults and "Show" in str(defaults[0].text),
      str(defaults[0].text) if defaults else "none")

# Transport entries only exist while there is something to act on.
set_state(connected=True)
visible_idle = [str(i.text) for i in items if i.visible]
check("no Stop recording while idle",
      not any("Stop recording" in t for t in visible_idle), visible_idle)
set_state(connected=True, recording=True, game="Helldivers 2", elapsed="00:00:05")
visible_rec = [str(i.text) for i in items if i.visible]
check("Stop recording appears while recording",
      any("Stop recording" in t for t in visible_rec), visible_rec)
set_state(connected=True, recording=True, paused=True, game="Helldivers 2")
check("paused offers Resume, not Pause",
      any("Resume recording" in str(i.text) for i in items if i.visible))

# ---- window chrome: both - and x hide, neither quits ----
hidden = {"n": 0}
app._hide = lambda: hidden.__setitem__("n", hidden["n"] + 1)
quit_calls = {"n": 0}
app.quit = lambda: quit_calls.__setitem__("n", quit_calls["n"] + 1)
src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "obsauto", "gui.py"), encoding="utf-8").read()
titlebar = src.split("def _build_titlebar", 1)[1].split("def _build_topbar", 1)[0]
check("close button hides to tray", titlebar.count("self._hide") >= 2, titlebar.count("self._hide"))
check("no quit path in the titlebar", "self.quit" not in titlebar)

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<44} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
