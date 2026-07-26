"""The system-tray icon and its menu - v3 frame 2j.

The rules that frame states literally, and why each is done the way it is:

* "Both - and x hide to tray. Quit exists only in this menu." The window
  buttons are wired to `_hide` in gui.py; `Quit Nebula` below is the only way
  out of the app.
* "Tray icon states: idle = accent outline, recording = ember filled,
  disconnected = neutral with a slash." Three static icons from icon_art,
  swapped on state change. This replaced a permanent 12fps rotation - the spin
  said nothing about what the app was doing while redrawing forever.
* "Single click = show window. Right click = this menu." `default=True` on
  Show Nebula is what makes a left click activate it.
* "Tooltip = game + elapsed."
* "The header block is not a menu item - not hoverable, not clickable."
  A native Win32 tray menu can only contain menu items, so the closest true
  equivalent is a *disabled* item: Windows neither highlights nor activates
  those. Two of them, since a menu item can't be two lines.

Everything here runs on pystray's own thread, so every callback marshals back
onto the Tk thread with `root.after(0, ...)` rather than touching widgets.
"""

import threading

import pystray

from .icon_art import generate_state_icons

ICON_PATH = None  # unused - kept only in case something still imports it


def build_tray_icon(app_window, icon_path):
    icons = generate_state_icons(size=64)

    def on_tk(fn):
        """Hand a callback back to the Tk thread."""
        def handler(icon=None, item=None):
            try:
                app_window.root.after(0, fn)
            except RuntimeError:
                pass  # window already torn down
        return handler

    def status():
        return app_window.tray_status()

    def recording(_item=None):
        return status()["state"] in ("recording", "paused")

    def _quit(icon, item):
        icon.visible = False
        icon.stop()
        app_window.quit()

    menu = pystray.Menu(
        # --- the header block: state, then game + elapsed. Disabled on
        # purpose, so it reads as a label rather than something to click.
        pystray.MenuItem(lambda item: status()["heading"], None, enabled=False),
        pystray.MenuItem(lambda item: status()["detail"], None, enabled=False),
        pystray.Menu.SEPARATOR,

        pystray.MenuItem("Show Nebula", on_tk(app_window.show), default=True),
        pystray.MenuItem(
            lambda item: "Resume recording" if status()["state"] == "paused"
            else "Pause recording",
            on_tk(app_window._toggle_pause), visible=recording),
        pystray.MenuItem("Stop recording", on_tk(app_window._toggle_record),
                         visible=recording),
        pystray.MenuItem(
            lambda item: "Monitoring on" if status()["monitoring"] else "Monitoring off",
            on_tk(app_window._toggle_monitoring),
            checked=lambda item: status()["monitoring"]),
        pystray.MenuItem("Open recordings", on_tk(app_window._open_recording_root)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Nebula", _quit),
    )

    icon = pystray.Icon("nebula", icons["idle"], "Nebula", menu)
    icon._nebula_icons = icons          # so gui.py can swap without regenerating
    threading.Thread(target=icon.run, daemon=True).start()
    return icon
