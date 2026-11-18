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

import os
import sys
import threading
import time

try:
    import pystray
except ImportError:
    pystray = None

# Win11 keeps one subkey per tray icon it has ever seen. IsPromoted 0 = the
# overflow (the arrow by the clock), 1 = the visible row.
_NOTIFY_SETTINGS = r"Control Panel\NotifyIconSettings"
_TRAY_TOOLTIP = "Nebula"


def _art():
    from .icon_art import (
        ARC_PERIOD_S, generate_recording_frames, generate_state_icons)
    return ARC_PERIOD_S, generate_recording_frames, generate_state_icons

ICON_PATH = None  # unused - kept only in case something still imports it

# The recording arc, at the rate the icon design asks for. Frames are
# pre-rendered once and cached on the icon, so a tick is an assignment and a
# list index - never a draw.
RECORDING_FPS = 10


def set_tray_state(icon, state):
    """Swap the tray icon for `state`, animating the arc while recording.

    Both hosts call this rather than assigning ``icon.icon`` themselves, so
    the animation lives in one place and cannot drift between the Tk build and
    the webview one.

    v3 retired the old tray spin for good reason: a permanent 12fps rotation
    said nothing while redrawing forever. This is the opposite case - the arc
    runs *only* while recording, which is exactly when motion carries the
    meaning, and stops dead the moment it ends.
    """
    if icon is None:
        return
    _stop_recording_arc(icon)
    icons = getattr(icon, "_nebula_icons", None) or {}
    if state == "recording":
        _start_recording_arc(icon, icons)
    elif state in icons:
        icon.icon = icons[state]


def _stop_recording_arc(icon):
    stop = getattr(icon, "_nebula_arc_stop", None)
    if stop is not None:
        stop.set()
    icon._nebula_arc_stop = None


def _start_recording_arc(icon, icons):
    frames = getattr(icon, "_nebula_arc_frames", None)
    if frames is None:
        # Match whatever size the static icons were built at, so the tray does
        # not change resolution when recording starts.
        ref = icons.get("idle")
        size = ref.size[0] if ref is not None else 64
        arc_period, generate_recording_frames, _icons = _art()
        frames = generate_recording_frames(size=size, fps=RECORDING_FPS)
        icon._nebula_arc_frames = frames
    else:
        arc_period = _art()[0]
    if not frames:
        return

    icon.icon = frames[0]           # land on the state immediately, not in 100ms
    stop = threading.Event()
    icon._nebula_arc_stop = stop
    period = arc_period / float(len(frames))

    def run():
        i = 1
        while not stop.wait(period):
            # A stopped thread must never paint over the icon its successor
            # just set. Checking identity - not just the flag - closes the gap
            # between set() and this thread noticing it.
            if getattr(icon, "_nebula_arc_stop", None) is not stop:
                return
            try:
                icon.icon = frames[i % len(frames)]
            except Exception:
                return              # tray torn down under us
            i += 1

    threading.Thread(target=run, daemon=True, name="nebula-tray-arc").start()


def is_nebula_entry(exe_path, tooltip, own_exe):
    """True when a NotifyIconSettings entry is this app's icon.

    Same executable name as us, and something that says Nebula: the
    tooltip pystray registered, or an exe that is itself named Nebula.
    A bare pythonw.exe entry with some other tooltip is another app.
    """
    exe = os.path.basename(str(exe_path or "")).lower()
    own = os.path.basename(str(own_exe or "")).lower()
    if not exe or exe != own:
        return False
    tip = str(tooltip or "").strip().lower()
    return tip.startswith(_TRAY_TOOLTIP.lower()) or exe.startswith("nebula")


def demote_to_overflow(own_exe=None, log=None):
    """Move this app's tray icon into the overflow. Returns keys changed.

    Never hides it (that is a different setting) and never restarts
    Explorer. Only keys :func:`is_nebula_entry` accepts are written.
    """
    if os.name != "nt":
        return 0
    import winreg
    own_exe = own_exe or sys.executable
    changed = 0
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _NOTIFY_SETTINGS)
    except OSError:
        return 0
    with root:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                key = winreg.OpenKey(
                    root, name, 0,
                    winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE)
            except OSError:
                continue
            with key:
                values = {}
                for value_name in ("ExecutablePath", "InitialTooltip",
                                   "IsPromoted"):
                    try:
                        values[value_name] = winreg.QueryValueEx(
                            key, value_name)[0]
                    except OSError:
                        values[value_name] = None
                if not is_nebula_entry(values["ExecutablePath"],
                                       values["InitialTooltip"], own_exe):
                    continue
                if values["IsPromoted"] == 0:
                    changed += 1
                    continue
                try:
                    winreg.SetValueEx(key, "IsPromoted", 0,
                                      winreg.REG_DWORD, 0)
                    changed += 1
                except OSError as exc:
                    if log:
                        log(f"[Tray] Couldn't move the icon to the overflow: {exc}")
    return changed


def _demote_soon(log, tries=10, delay_s=1.0):
    """Explorer writes the key a moment after the icon registers. Retry."""
    def run():
        for _ in range(tries):
            try:
                if demote_to_overflow(log=log):
                    return
            except Exception as exc:
                if log:
                    log(f"[Tray] Overflow demotion failed: {exc}")
                return
            time.sleep(delay_s)

    threading.Thread(target=run, daemon=True, name="nebula-tray-demote").start()


def build_tray_icon(app_window, icon_path):
    if pystray is None:
        raise ImportError("pystray is not available")
    _period, _frames, generate_state_icons = _art()
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

    icon = pystray.Icon("nebula", icons["idle"], _TRAY_TOOLTIP, menu)
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
        _log("[Tray] Icon registered. It lives in the overflow arrow next "
             "to the clock.")
        # The tray icon is Nebula's only taskbar presence, and it belongs in
        # the overflow rather than the visible row.
        _demote_soon(_log)

    def _run():
        try:
            icon.run(setup=_ready)
        except Exception as exc:
            _log(f"[Tray] The tray icon failed to start: {exc}")

    threading.Thread(target=_run, daemon=True).start()
    return icon
