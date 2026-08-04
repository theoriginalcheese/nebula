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
        """Hand a callback back to the host's UI thread.

        v3's host is a Tk window, so that means ``root.after(0, ...)``. v4's is
        a webview with no Tk root, and exposes ``call_soon()`` instead. Prefer
        that when it exists - the tray does not need to know which renderer it
        is driving, and keeping one copy of this file means the two cannot
        drift apart.
        """
        def handler(icon=None, item=None):
            try:
                marshal = getattr(app_window, "call_soon", None)
                if marshal is not None:
                    marshal(fn)
                else:
                    app_window.root.after(0, fn)
            except RuntimeError:
                pass  # window already torn down
        return handler

    # Every label below is a callable, re-evaluated by Windows each time the
    # menu opens. If one of them raises, the shell gets nothing back and the
    # menu simply never appears - a failure with no console, no traceback and
    # no log line, which is indistinguishable from "the tray is broken".
    # Fall back to a static label instead, and leave a breadcrumb.
    _fallback = {"state": "idle", "heading": "Nebula", "detail": "",
                 "monitoring": False}

    def status():
        try:
            return app_window.tray_status()
        except Exception as exc:
            try:
                app_window._log(f"[Tray] Couldn't read status: {exc}")
            except Exception:
                pass
            return _fallback

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
        # 7a lists the tray among the surfaces that can save a replay. Shown
        # only while the buffer is actually armed - an item that can only tell
        # you it won't work is worse than no item.
        pystray.MenuItem(
            lambda item: f"Save the last {app_window.replay.seconds}s",
            on_tk(app_window._save_replay),
            visible=lambda _item: bool(getattr(app_window, "replay", None))
            and app_window.replay.armed),
        # Hidden until there is a Monitor to toggle. Same reasoning as the
        # replay item above: an entry that can only tell you it won't work is
        # worse than no entry. v3's AppWindow always has one, so this is only
        # ever false during the v4 port, before step 2 lands.
        pystray.MenuItem(
            lambda item: "Monitoring on" if status()["monitoring"] else "Monitoring off",
            on_tk(app_window._toggle_monitoring),
            checked=lambda item: status()["monitoring"],
            visible=lambda _item: getattr(app_window, "monitor", True) is not None),
        pystray.MenuItem("Open recordings", on_tk(app_window._open_recording_root)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Nebula", _quit),
    )

    icon = pystray.Icon("nebula", icons["idle"], "Nebula", menu)
    icon._nebula_icons = icons          # so gui.py can swap without regenerating

    def _log(message):
        try:
            app_window._log(message)
        except Exception:
            pass

    def _ready(tray):
        # pystray calls setup once the icon is actually registered with the
        # shell. Without this the only evidence that the tray exists is
        # whether you can see it - and on Windows 11 a newly-registered icon
        # goes into the hidden overflow by default, so "no menu" and "no icon
        # I could find" look exactly the same. Say so in the log.
        tray.visible = True
        _log("[Tray] Icon registered. If you can't see it, check the "
             "overflow arrow next to the clock and drag Nebula onto the bar.")

    def _run():
        try:
            icon.run(setup=_ready)
        except Exception as exc:
            _log(f"[Tray] The tray icon failed to start: {exc}")

    threading.Thread(target=_run, daemon=True).start()
    return icon
