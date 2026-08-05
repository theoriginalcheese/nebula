"""Toast (2i) and mini overlay (2k) as separate pywebview windows.

These are deliberately *not* part of the main ``index.html`` surface — another
agent owns ``spike/app.py`` and ``spike/host.py``. This module defines the
windows, their JS APIs, and the interface the host must call.

Wire-up (for the host agent):

    windows = NebulaWindows(host, config)
    host._windows = windows

    # on monitor notify:
    host._on_notify -> windows.toast_replace(event, display_name, details)

    # after poll when recording state changes:
    windows.overlay_sync()

    # palette / tray "Show mini overlay":
    windows.overlay_show()

    # on quit:
    windows.destroy()
"""
from __future__ import annotations

import atexit
import ctypes
import json
import os
import threading
import time

import psutil
import webview

from obsauto import design_v3 as dv
from obsauto.config import save_config

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
TOAST_HTML = os.path.join(WEB, "toast.html")
OVERLAY_HTML = os.path.join(WEB, "overlay.html")

TOAST_W, TOAST_H = 336, 88

# Segoe Fluent Icons — same verified codepoints as gui.py, keyed by Phosphor name.
_ICON_CODEPOINTS = {
    "record": 0xE7C8,
    "pause": 0xE769,
    "play": 0xE768,
    "scissors": 0xE8C6,
    "square": 0xE73B,
    "arrows-in-simple": 0xE73F,
    "plugs": 0xEB55,
}
ICON_GLYPHS = {name: chr(cp) for name, cp in _ICON_CODEPOINTS.items()}

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WM_CLOSE = 0x0010

_LIVENESS_INTERVAL = 3.0
_AUXILIARY_TITLES = frozenset(("Nebula Toast", "Nebula Overlay"))


# --- monitor geometry -------------------------------------------------------

def _toast_workarea():
    """Work area of the monitor the cursor is on (frame 2i positioning)."""
    try:
        from ctypes import Structure, byref, c_long, c_ulong, c_wchar, sizeof, windll

        class POINT(Structure):
            _fields_ = [("x", c_long), ("y", c_long)]

        class RECT(Structure):
            _fields_ = [("left", c_long), ("top", c_long),
                        ("right", c_long), ("bottom", c_long)]

        class MONITORINFOEXW(Structure):
            _fields_ = [("cbSize", c_ulong), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", c_ulong),
                        ("szDevice", c_wchar * 32)]

        pt = POINT()
        windll.user32.GetCursorPos(byref(pt))
        monitor = windll.user32.MonitorFromPoint(pt, 2)
        info = MONITORINFOEXW()
        info.cbSize = sizeof(MONITORINFOEXW)
        if windll.user32.GetMonitorInfoW(monitor, byref(info)):
            r = info.rcWork
            return r.left, r.top, r.right, r.bottom, monitor
    except Exception:
        pass
    return 0, 0, 1920, 1040, None


def _monitor_scale(monitor_handle):
    """pywebview positions in logical px; ``GetMonitorInfo`` is physical."""
    if monitor_handle is None:
        return 1.0
    try:
        from ctypes import byref, c_ulong, windll
        dpi_x = c_ulong()
        dpi_y = c_ulong()
        windll.shcore.GetDpiForMonitor(monitor_handle, 0, byref(dpi_x), byref(dpi_y))
        return dpi_x.value / 96.0
    except Exception:
        return 1.0


def _toast_place(right, bottom, monitor_handle):
    """Logical x/y for ``create_window``, on the PRIMARY monitor.

    pywebview multiplies ``x``/``y`` by the DPI of the monitor the window is
    *created* on - always the primary - while ``GetMonitorInfo`` work areas are
    physical. Dividing by some *other* monitor's scale therefore lands the
    window at (that monitor's coords x primary scale), which on a mixed-DPI
    desktop is nowhere useful: aiming at the bottom of the 100% screen put the
    toast at y=1452 on a desktop 1440 tall, i.e. off the bottom edge.

    Both halves now use the primary, so the division and pywebview's
    multiplication cancel exactly. 2i asks for the cursor's monitor and this
    deliberately does not do that - a toast you cannot see is worse than one on
    the wrong screen, and every attempt to place it cross-monitor
    (SetWindowPos, SetThreadDpiAwarenessContext) was silently virtualised.

    ``right``/``bottom``/``monitor_handle`` are ignored, kept so the call sites
    and _toast_workarea() need not change.
    """
    rect = (ctypes.c_long * 4)()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    scale = _primary_scale()
    x = (rect[2] / scale) - TOAST_W - dv.TOAST_MARGIN
    y = (rect[3] / scale) - TOAST_H - dv.TOAST_MARGIN
    return x, y


def _corner_physical(w_css, h_css, lift=0):
    """Bottom-right of the cursor's monitor, in PHYSICAL screen pixels.

    ``lift`` raises it by that many physical pixels, so two windows can share
    the corner without sharing the spot.
    """
    # PRIMARY monitor, deliberately - not the one the cursor is on.
    #
    # 2i says "the monitor the cursor is on", and that is what this did. But a
    # cross-monitor SetWindowPos from this process gets its coordinates
    # virtualised whenever the target monitor's DPI differs from the primary's:
    # asking for (-360, 968) on the 100% screen landed the window at
    # (-540, 1452) - the same numbers times the primary's 1.5, off the bottom
    # of the desktop. Asking for a point already on the primary came back
    # exact, every time. SetThreadDpiAwarenessContext did not hold.
    #
    # A toast the user cannot see is worse than a toast on the wrong monitor,
    # and this is the one case that is reliably correct. Revisit if the
    # placement ever needs to follow the cursor again.
    rect = (ctypes.c_long * 4)()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    right, bottom = rect[2], rect[3]
    scale = _primary_scale()
    margin = int(dv.TOAST_MARGIN * scale)
    x = right - int(w_css * scale) - margin
    y = bottom - int(h_css * scale) - margin - lift
    return x, y


def _primary_scale():
    """Primary monitor's logical-to-physical scale."""
    try:
        dc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)   # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, dc)
        return (dpi or 96) / 96.0
    except Exception:
        return 1.0


def _make_transparent(window, host=None):
    """Key the window's fill out, so the page's rounded corners really are
    transparent rather than sitting in a coloured box.

    Four approaches, in the order they were tried against a real toast:

    1. ``background_color`` alone - the rectangular window paints GROUND_DEEP
       behind the rounded card: a near-black box.
    2. pywebview ``transparent=True`` - worse, a *white* box. That path sets
       the WebView2 background transparent but takes the ``else`` branch that
       would have set the form's BackColor, so the form keeps the WinForms
       default.
    3. ``SetWindowRgn`` with a rounded region - ``GetWindowRgn`` confirmed a
       COMPLEX region of the right size was applied and the box was still
       there. WebView2 draws through DirectComposition, which a GDI window
       region does not clip.
    4. DWM's ``DWMWA_WINDOW_CORNER_PREFERENCE`` - no effect. DWM does not round
       frameless ``WS_POPUP`` windows; it rounds windows it draws a frame for.

    What works is (2) done properly: WebView2's background transparent *and*
    the form's BackColor set to a colour that is then keyed out. Black is safe
    here - the darkest thing the toast actually paints is GROUND_DEEP
    (16, 14, 27), so nothing real is lost to the key.
    """
    def apply():
        try:
            hwnd = int(window.native.Handle.ToInt64())
            pref = ctypes.c_int(2)   # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), ctypes.c_int(33),
                ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception as exc:
            if host is not None and hasattr(host, "_log"):
                host._log("[Windows] DWM round failed: %s" % exc)

    _run_on_gui(host, apply)


def _place_physical(window, x, y, host=None):
    """Move a window by PHYSICAL screen pixels, bypassing pywebview.

    ``move()`` and the ``x``/``y`` given to ``create_window`` are *logical*
    pixels, converted with ``GetDpiForWindow`` of the monitor the window is on
    **at that moment** - which, before it has been positioned, is the primary.
    On a mixed-DPI desktop that is not the monitor the position was computed
    for, and the two scales multiply out:

        1920x1080 @100% work area -> y = 1080 - 88 - 16 = 976 logical
        applied on the 150% primary               -> 976 * 1.5 = 1464 physical

    on a desktop only 1440 tall. The toast was landing completely off-screen
    whenever the cursor sat on the lower-DPI monitor. Placing in physical
    pixels has no conversion to disagree about.

    ``.Handle`` is a WinForms property, so this has to run on the GUI thread.
    """
    def apply():
        try:
            import ctypes
            hwnd = int(window.native.Handle.ToInt64())
            SWP_NOSIZE, SWP_NOACTIVATE = 0x0001, 0x0010
            HWND_TOPMOST = -1
            # The *thread* has to be per-monitor aware, not just the process.
            # WinForms leaves this GUI thread on a system-aware context, and a
            # system-aware caller gets its coordinates virtualised: asking for
            # (-360, 968) on the 100% monitor landed the window at
            # (-540, 1452) - the same numbers times the primary's 1.5 - which
            # is off the bottom of the desktop. Asking for a point already on
            # the primary came back exact, which is what made this look
            # intermittent rather than systematic.
            prev_ctx = None
            try:
                fn = ctypes.windll.user32.SetThreadDpiAwarenessContext
                fn.argtypes = [ctypes.c_void_p]
                fn.restype = ctypes.c_void_p
                prev_ctx = fn(ctypes.c_void_p(-4))   # PER_MONITOR_AWARE_V2
            except Exception:
                prev_ctx = None
            try:
                ctypes.windll.user32.SetWindowPos(
                    hwnd, HWND_TOPMOST, int(x), int(y), 0, 0,
                    SWP_NOSIZE | SWP_NOACTIVATE)
            finally:
                if prev_ctx:
                    try:
                        fn(ctypes.c_void_p(prev_ctx))
                    except Exception:
                        pass
        except Exception as exc:
            if host is not None and hasattr(host, "_log"):
                host._log("[Windows] physical placement failed: %s" % exc)

    _run_on_gui(host, apply)


def _monitor_key(x, y):
    """Key for ``mini_overlay_positions`` — matches gui.py / test_step7."""
    try:
        from ctypes import Structure, byref, c_long, c_ulong, c_wchar, sizeof, windll

        class POINT(Structure):
            _fields_ = [("x", c_long), ("y", c_long)]

        class RECT(Structure):
            _fields_ = [("left", c_long), ("top", c_long),
                        ("right", c_long), ("bottom", c_long)]

        class MONITORINFOEXW(Structure):
            _fields_ = [("cbSize", c_ulong), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", c_ulong),
                        ("szDevice", c_wchar * 32)]

        monitor = windll.user32.MonitorFromPoint(POINT(int(x), int(y)), 2)
        info = MONITORINFOEXW()
        info.cbSize = sizeof(MONITORINFOEXW)
        if windll.user32.GetMonitorInfoW(monitor, byref(info)):
            r = info.rcWork
            return "%d,%d,%d,%d" % (r.left, r.top, r.right, r.bottom), (
                r.left, r.top, r.right, r.bottom)
    except Exception:
        pass
    return "primary", (0, 0, 1920, 1080)


def _hide_from_taskbar(window, on_log=None):
    """2k: no taskbar entry.

    ⚠️ Must run on the GUI thread. ``native.Handle`` is a WinForms property and
    reading it from another thread throws - which, under the old bare
    ``except: pass``, meant this silently did nothing and the overlay kept its
    taskbar entry. Only the ``.Handle`` read is thread-bound; ``SetWindowLongW``
    is a plain Win32 call on an HWND and would have been fine either way.
    """
    try:
        import ctypes
        hwnd = int(window.native.Handle.ToInt64())
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception as exc:
        if on_log:
            on_log("[Overlay] taskbar hide failed: %s" % exc)


def _format_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.0f %s" % (n, unit) if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f GB" % n


def _master_window(host):
    """The primary pywebview window — child windows must be born on its thread."""
    if host and getattr(host, "window", None):
        return host.window
    if webview.windows:
        return webview.windows[0]
    return None


def _run_on_gui(host, fn, wait=True):
    """Run ``fn`` on pywebview's WinForms thread (same as ``gui.py``'s ``_ui()``).

    ``create_window`` after ``webview.start()`` only registers a native HWND when
    called from that thread. Worker threads (Monitor, ``call_soon`` drain, hotkeys)
    otherwise get a Python ``Window`` handle that never appears in the shell.

    ``wait=False`` posts with ``BeginInvoke`` instead of ``Invoke``. Use it for
    anything that *creates* a window. pywebview's own winforms backend already
    marshals a secondary ``create_window`` to this same thread::

        _main_window_created.wait()
        i = list(BrowserView.instances.values())[0]
        i.Invoke(Func[Type](create))

    so a blocking ``Invoke`` from a worker nests one synchronous hop inside
    another and pins the GUI thread for the whole of WebView2's construction -
    measured at ~20s here, during which the app is frozen and PrintWindow on it
    hangs. Posting instead lets the delegate run as an ordinary queued message
    with the pump still turning. The caller gets no return value and no
    exception, which is fine for fire-and-forget window work and wrong for
    anything whose result is read back.
    """
    master = _master_window(host)
    if master is None:
        fn()
        return
    try:
        native = master.native
    except Exception:
        fn()
        return
    try:
        if native.InvokeRequired:
            from System import Func, Type
            if wait:
                native.Invoke(Func[Type](fn))
            else:
                native.BeginInvoke(Func[Type](fn))
        else:
            fn()
    except Exception as exc:
        host = host or type("_", (), {"_log": print})()
        log = getattr(host, "_log", None)
        if log:
            log("[Windows] GUI dispatch failed: %s" % exc)
        fn()


def _off_gui(fn):
    """Run ``fn`` anywhere EXCEPT pywebview's WinForms thread.

    The exact inverse of ``_run_on_gui``, and just as load-bearing. pywebview's
    ``evaluate_js`` is::

        self.webview.Invoke(... ExecuteScriptAsync(script).ContinueWith(
            callback, self.syncContextTaskScheduler))
        semaphore.acquire()

    The continuation is scheduled on the synchronisation context - the GUI
    thread - and then the *caller* blocks on the semaphore. Call it from the
    GUI thread and that thread waits forever on work only it can run. The
    window stops pumping, Windows substitutes a ``class='Ghost'`` stand-in, and
    any WebView2 created around then never initialises: its page never loads,
    so its script never executes.

    That is one deadlock behind two symptoms - the toast freezing the app on
    its first event, and the mini overlay coming up permanently blank.

    ``evaluate_js`` marshals to the GUI thread by itself, so a plain worker
    thread is not just safe here, it is the only correct caller.
    """
    threading.Thread(target=fn, daemon=True).start()


def _pid_alive(pid):
    """True if ``pid`` still exists."""
    try:
        return psutil.pid_exists(pid)
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def _hwnd_alive(hwnd):
    try:
        import ctypes
        return bool(ctypes.windll.user32.IsWindow(int(hwnd)))
    except Exception:
        return False


def _iter_auxiliary_windows():
    """Yield ``(hwnd, title, pid)`` for every visible toast/overlay window."""
    try:
        import ctypes
        import ctypes.wintypes as wt

        user32 = ctypes.windll.user32
        out = []

        @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value
            if title not in _AUXILIARY_TITLES:
                return True
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            out.append((int(hwnd), title, int(pid.value)))
            return True

        user32.EnumWindows(cb, 0)
        return out
    except Exception:
        return []


def _close_foreign_window(hwnd, pid):
    """Ask a foreign toast/overlay HWND to go away."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        if not _pid_alive(pid):
            user32.DestroyWindow(hwnd)
            return True
        if user32.PostMessageW(hwnd, WM_CLOSE, 0, 0):
            return True
        user32.EndTask(hwnd, False, True)
        return True
    except Exception:
        return False


def reclaim_orphan_windows(keep_pid=None):
    """Close toast/overlay windows owned by a dead Nebula process.

    The single-instance mutex guarantees at most one live host, so any
    auxiliary window whose PID is not ``keep_pid`` is an orphan.
    """
    keep_pid = keep_pid if keep_pid is not None else os.getpid()
    closed = []
    for hwnd, title, pid in _iter_auxiliary_windows():
        if pid == keep_pid:
            continue
        if _close_foreign_window(hwnd, pid):
            closed.append((hwnd, title, pid))
    return closed


def _host_process_alive(host, pid):
    if not _pid_alive(pid):
        return False
    if host is None:
        return False
    if getattr(host, "_quitting", False):
        return False
    master = _master_window(host)
    if master is None:
        return True
    try:
        hwnd = int(master.native.Handle.ToInt64())
    except Exception:
        return True
    return _hwnd_alive(hwnd)


def _force_destroy_window(win):
    if win is None:
        return
    try:
        win.destroy()
    except Exception:
        pass


class _LivenessWatch:
    """Close auxiliary windows when the host process or main window is gone."""

    def __init__(self, windows):
        self._windows = windows
        self._pid = os.getpid()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="NebulaAuxLiveness",
                                         daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(_LIVENESS_INTERVAL):
            host = self._windows._host
            if not _host_process_alive(host, self._pid):
                self._windows._teardown_without_host()
                return


def _force_destroy_controller(ctl):
    """Best-effort destroy that does not need a live host GUI thread."""
    ctl._alive = getattr(ctl, "_alive", False)
    if hasattr(ctl, "_open"):
        ctl._open = False
    if getattr(ctl, "_ready", None):
        ctl._ready.clear()
    _force_destroy_window(getattr(ctl, "_window", None))
    ctl._window = None


def _humanise(event):
    """'rec_start' -> 'Rec start'. Never an invented sentence - the event name
    is the only thing actually known about an unmapped event."""
    text = str(event or "").replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:] if text else "Nebula"


def _toast_content(event, display_name, details):
    tint_name = {
        "start": "ember", "stop": "ember", "error": "ember",
        "pause": "accent", "resume": "accent", "prompt": "accent",
    }.get(event, "accent")
    role = {"start": "start", "stop": "square", "pause": "pause",
            "resume": "resume", "error": "disconnected",
            "prompt": "start"}.get(event, "start")
    if role in dv.ICONS:
        glyph_key = dv.ICONS[role]
    else:
        glyph_key = role
    glyph = ICON_GLYPHS.get(glyph_key) or ICON_GLYPHS.get(role, "")
    # The five keys above are exactly what obsauto emits through on_notify, so
    # the fallback should never fire in practice. It exists because when it did
    # fire - a probe passing a session_log type like "rec_start" - the raw
    # identifier was rendered straight at the user. A future event name would do
    # the same silently. Humanise it instead: still honest about which event it
    # was, but readable.
    title = {
        "start": "Recording started",
        "stop": "Recording stopped",
        "pause": "Recording paused",
        "resume": "Recording resumed",
        "error": "Something went wrong",
        "prompt": "Record again?",
    }.get(event) or _humanise(event)
    if isinstance(details, dict) and details.get("title"):
        title = details["title"]
    parts = []
    if details:
        if isinstance(details, str):
            parts.append(details)
        else:
            duration = details.get("duration")
            if duration is not None:
                mm, ss = divmod(int(duration), 60)
                parts.append("%02d:%02d" % (mm, ss))
            size = details.get("size")
            if size is not None:
                parts.append(_format_bytes(size))
    return {
        "tint": tint_name,
        "glyph": glyph,
        "title": title,
        "sub": display_name or "",
        "detail": "  ·  ".join(parts),
    }


# --- toast ------------------------------------------------------------------

class ToastApi:
    """JS bridge for the toast window."""

    def __init__(self, controller):
        self._ctl = controller
        self._window = None

    def config(self):
        return {
            "w": TOAST_W,
            "h": TOAST_H,
            "life_ms": dv.TOAST_LIFE_MS,
            "drain_h": dv.TOAST_DRAIN_H,
            "margin": dv.TOAST_MARGIN,
            "in_ms": dv.TOAST_IN_MS,
            "in_rise": dv.TOAST_IN_RISE,
            "out_ms": dv.TOAST_OUT_MS,
        }

    def consume_pending(self):
        return self._ctl._take_pending()

    def ready(self):
        self._ctl._on_ready()

    def focus_main(self):
        self._ctl._focus_main()

    def on_expired(self):
        self._ctl._on_expired()


class ToastController:
    """One toast for the process life — replace in place, never a stack."""

    TITLE = "Nebula Toast"

    def __init__(self, host):
        self._host = host
        self._api = ToastApi(self)
        self._window = None
        self._ready = threading.Event()
        self._pending = None
        self._alive = False

    def replace(self, event, display_name, details=None):
        try:
            content = _toast_content(event, display_name, details)
        except Exception as exc:
            self._log("[Toast] content failed: %s" % exc)
            return
        # Posted, not blocking. The first toast of a session is the one that
        # builds the window, and doing that inside a synchronous Invoke pins
        # the GUI thread for the whole of WebView2's construction - the app
        # goes "not responding" until it finishes. Every later toast only
        # mutates the existing window and would be fine either way, but the
        # first one is exactly the case being reported. See _run_on_gui.
        _run_on_gui(self._host, lambda: self._replace_gui(content), wait=False)

    def _replace_gui(self, content):
        self._pending = content
        if self._window is None:
            self._create()
        elif self._ready.is_set():
            self._push(content)

    def _take_pending(self):
        out = self._pending
        self._pending = None
        return out

    def _create(self):
        # Approximate only - correct on a single-DPI desktop, and superseded by
        # _reposition()'s physical placement on the first push either way.
        # create_window has no physical-pixel option, so this is as good as the
        # starting point gets.
        left, top, right, bottom, monitor = _toast_workarea()
        x, y = _toast_place(right, bottom, monitor)

        win = webview.create_window(
            self.TITLE,
            TOAST_HTML,
            js_api=self._api,
            width=TOAST_W,
            height=TOAST_H,
            # pywebview defaults min_size=(200, 100) and the winforms backend
            # applies it as MinimumSize, so an 88px-tall toast was silently
            # clamped to 100 - an opaque, always-on-top dead band below the
            # card, on a frameless window with no way to see where it ends.
            min_size=(TOAST_W, TOAST_H),
            x=x,
            y=y,
            frameless=True,
            easy_drag=False,
            on_top=True,
            hidden=False,
            resizable=False,
            # shadow=True makes pywebview call ExtendFrameIntoClientArea, which
            # gives DWM a frame to own - the documented precondition for
            # DWMWA_WINDOW_CORNER_PREFERENCE having any effect. A bare
            # frameless popup is not rounded by DWM at all.
            shadow=True,
            focus=False,
            background_color=dv.GROUND_DEEP,
        )
        if win is None:
            self._log("[Toast] create_window returned None")
            return
        self._window = win
        self._api._window = win
        self._alive = True

    def _on_ready(self):
        self._ready.set()
        # Clip to the card's own corner radius, once the window exists at its
        # final size. Without this the rectangular window shows around the
        # rounded card as a coloured box.
        _make_transparent(self._window, self._host)
        # Place it here, unconditionally. _reposition() otherwise only runs
        # from _push(), and on the *first* toast _push never runs: toast.js
        # pulls the content itself via consume_pending() before calling
        # ready(), so _pending is already None by the time we get here. That
        # left the first toast - the only one most sessions ever show - sitting
        # wherever pywebview's create-time x/y put it, which on a mixed-DPI
        # desktop is off-screen entirely.
        self._reposition()
        if self._pending:
            self._push(self._pending)
            self._pending = None

    def _push(self, content):
        if not self._window or not self._alive:
            return

        def run():
            try:
                payload = json.dumps(content, ensure_ascii=False)
                self._window.evaluate_js("window.toastReplace(%s)" % payload)
                self._reposition()
                self._window.show()
            except Exception as exc:
                self._log("[Toast] push failed: %s" % exc)

        # Every caller of this reaches it on the GUI thread (_replace_gui via
        # _run_on_gui, _on_ready via the bridge), and evaluate_js deadlocks
        # there. See _off_gui.
        _off_gui(run)

    def _reposition(self):
        if not self._window:
            return
        # Same logical coordinates create_window was given, through the same
        # pywebview scaling. Going around it with SetWindowPos was the thing
        # that kept getting virtualised.
        left, top, right, bottom, monitor = _toast_workarea()
        x, y = _toast_place(right, bottom, monitor)
        try:
            self._window.move(x, y)
            self._window.on_top = True
        except Exception:
            pass

    def _focus_main(self):
        host = self._host
        if host and hasattr(host, "show"):
            host.call_soon(host.show)

    def _on_expired(self):
        def expire():
            self._alive = False
            self._ready.clear()
            if self._window:
                try:
                    self._window.destroy()
                except Exception:
                    pass
            self._window = None

        _run_on_gui(self._host, expire)

    def destroy(self):
        def teardown():
            self._alive = False
            if self._window:
                try:
                    self._window.destroy()
                except Exception:
                    pass
            self._window = None

        _run_on_gui(self._host, teardown)

    def _log(self, msg):
        host = self._host
        if host and hasattr(host, "_log"):
            host._log(msg)


# --- overlay ------------------------------------------------------------------

class OverlayApi:
    """JS bridge for the mini overlay."""

    def __init__(self, controller):
        self._ctl = controller
        self._window = None

    def config(self):
        return {
            "w": dv.MINI_W,
            "h": dv.MINI_H,
            "fade_after_ms": dv.MINI_FADE_AFTER_MS,
            "faded_opacity": dv.MINI_FADED_OPACITY,
            "snap_px": dv.MINI_SNAP_PX,
            "glyphs": {
                "record": ICON_GLYPHS["record"],
                "pause": ICON_GLYPHS["pause"],
                "resume": ICON_GLYPHS["play"],
                "square": ICON_GLYPHS["square"],
                "mark_clip": ICON_GLYPHS["scissors"],
                "collapse_mini": ICON_GLYPHS["arrows-in-simple"],
            },
        }

    def consume_snapshot(self):
        return self._ctl._take_snapshot()

    def ready(self):
        self._ctl._on_ready()

    def drag_by(self, dx, dy):
        self._ctl._drag_by(dx, dy)

    def drag_end(self):
        self._ctl._snap()

    def action(self, name):
        self._ctl._action(name)


class OverlayController:
    """296×54 always-on-top overlay — never while idle."""

    TITLE = "Nebula Overlay"

    def __init__(self, host, config):
        self._host = host
        self._config = config
        self._api = OverlayApi(self)
        self._window = None
        self._ready = threading.Event()
        self._snapshot = None
        self._open = False

    def _state_allows(self):
        host = self._host
        if not host:
            return False
        state = host.hero_state() if hasattr(host, "hero_state") else "idle"
        return state in ("recording", "paused")

    def _readout(self):
        host = self._host
        if not host:
            return {"elapsed": "", "game": "", "paused": False}
        state = host.hero_state() if hasattr(host, "hero_state") else "idle"
        readouts = host.hero_readouts() if hasattr(host, "hero_readouts") else {}
        game = getattr(host, "_current_game", None) or getattr(host, "_tray_game", None)
        return {
            "elapsed": readouts.get("elapsed") or "",
            "game": game or "",
            "paused": state == "paused",
        }

    def show(self):
        if not self._state_allows():
            self._log("[Manual] Mini overlay only appears while recording.")
            return
        # Posted, not blocking: _show_gui builds a WebView2 window, and that
        # must not run inside a synchronous Invoke. See _run_on_gui.
        _run_on_gui(self._host, self._show_gui, wait=False)

    def _show_gui(self):
        if self._window is None:
            self._create()
        self._snapshot = self._readout()
        if self._ready.is_set():
            self._push(self._snapshot)
        try:
            self._window.show()
            self._window.on_top = True
        except Exception:
            pass
        self._open = True
        # host.hide() -> host._sleep(False) -> evaluate_js on the MAIN window,
        # and we are on the GUI thread here. Calling it inline deadlocks that
        # thread, which is what left the just-created overlay a Ghost window
        # with a page that never loaded. See _off_gui.
        if self._host and hasattr(self._host, "hide"):
            _off_gui(self._host.hide)

    def hide(self, restore=False):
        _run_on_gui(self._host, lambda: self._hide_gui(restore))

    def _hide_gui(self, restore=False):
        self._open = False
        if self._window:
            try:
                self._window.hide()
            except Exception:
                pass
        if restore and self._host and hasattr(self._host, "show"):
            self._host.show()

    def sync(self):
        """Mirror host poll onto the overlay; close when recording ends."""
        _run_on_gui(self._host, self._sync_gui)

    def _sync_gui(self):
        if not self._open and self._window is None:
            return
        if not self._state_allows():
            self._hide_gui(restore=False)
            if self._window:
                try:
                    self._window.destroy()
                except Exception:
                    pass
            self._window = None
            self._ready.clear()
            return
        if not self._open:
            return
        data = self._readout()
        if not data["elapsed"]:
            return
        self._push(data)

    def _take_snapshot(self):
        out = self._snapshot
        self._snapshot = None
        return out

    def _create(self):
        sw, sh = dv.MINI_W, dv.MINI_H
        x, y = self._saved_position(sw, sh)
        win = webview.create_window(
            self.TITLE,
            OVERLAY_HTML,
            js_api=self._api,
            width=sw,
            height=sh,
            # As the toast: without this, pywebview's min_size=(200, 100)
            # clamps the 54px overlay to 100, so nearly half the window was an
            # opaque always-on-top band hanging below the visible card.
            min_size=(sw, sh),
            x=x,
            y=y,
            frameless=True,
            easy_drag=False,
            on_top=True,
            # NOT hidden=True. _create() runs inside _run_on_gui's *synchronous*
            # native.Invoke, i.e. on the WinForms thread. create_window(hidden)
            # then waits on a window event that only that same thread can
            # deliver, so it deadlocks: the Invoke never returns, _show_gui
            # never runs, and the overlay never appears - silently, because
            # nothing throws. The toast never hit this because it creates
            # visible. _create() is only ever called when we are about to show
            # the overlay anyway, so there is nothing to hide it from.
            resizable=False,
            # As the toast: shadow=True extends the frame, which is what lets
            # DWM round the window. See _make_transparent.
            shadow=True,
            focus=False,
            background_color=dv.GROUND_DEEP,
        )
        if win is None:
            self._log("[Overlay] create_window returned None")
            return
        self._window = win
        self._api._window = win
        threading.Timer(0.5, self._apply_taskbar_hide).start()

    def _apply_taskbar_hide(self):
        if not self._window:
            return
        # Fired from a threading.Timer, i.e. not the GUI thread, and
        # _hide_from_taskbar reads a WinForms property. Marshal it. Safe to
        # block here: no window creation and no evaluate_js on this path.
        _run_on_gui(self._host,
                    lambda: _hide_from_taskbar(self._window, self._log))

    def _saved_position(self, sw, sh):
        left, top, right, bottom, monitor = _toast_workarea()
        scale = _monitor_scale(monitor)
        key, _rect = _monitor_key((left + right) / 2, (top + bottom) / 2)
        saved = (self._config.get("mini_overlay_positions") or {}).get(key)
        if saved and len(saved) == 2:
            x, y = int(saved[0]), int(saved[1])
            x = max(left, min(x, right - int(sw * scale)))
            y = max(top, min(y, bottom - int(sh * scale)))
            return x / scale, y / scale
        # Default clear of the toast's slot. Both windows are bottom-right,
        # always-on-top, and the toast arrives unannounced - sharing the corner
        # means the first rec_start covers the overlay with a toast. Stack the
        # overlay directly above the toast band instead. Only the *default*
        # moves; a dragged position is whatever the user chose.
        margin = dv.TOAST_MARGIN
        x = (right / scale) - sw - margin
        y = (bottom / scale) - sh - margin - TOAST_H - margin
        return x, y

    def _drag_by(self, dx, dy):
        if not self._window:
            return
        try:
            self._window.move(self._window.x + int(dx), self._window.y + int(dy))
        except Exception:
            pass

    def _snap(self):
        if not self._window:
            return
        sw, sh = dv.MINI_W, dv.MINI_H
        x, y = self._window.x, self._window.y
        key, (left, top, right, bottom) = _monitor_key(x + sw / 2, y + sh / 2)
        snap = dv.MINI_SNAP_PX
        if abs(x - left) <= snap:
            x = left
        elif abs((x + sw) - right) <= snap:
            x = right - sw
        if abs(y - top) <= snap:
            y = top
        elif abs((y + sh) - bottom) <= snap:
            y = bottom - sh
        try:
            self._window.move(x, y)
        except Exception:
            pass
        positions = dict(self._config.get("mini_overlay_positions") or {})
        positions[key] = [x, y]
        self._config["mini_overlay_positions"] = positions
        save_config(self._config)

    def _action(self, name):
        host = self._host
        if not host:
            return
        if name == "collapse":
            self.hide(restore=True)
            def teardown():
                if self._window:
                    try:
                        self._window.destroy()
                    except Exception:
                        pass
                self._window = None
                self._ready.clear()
            _run_on_gui(self._host, teardown)
            return
        if name == "pause":
            host.call_soon(host._toggle_pause)
        elif name == "stop":
            host.call_soon(host._toggle_record)
        elif name == "mark":
            host.call_soon(lambda: self._mark_clip())

    def _mark_clip(self):
        host = self._host
        if not host or not getattr(host, "_is_recording", False):
            return
        try:
            from obsauto import session_log
            game = getattr(host, "_current_game", None) or getattr(host, "_tray_game", None)
            session_log.append({"type": "mark", "game": game or ""})
            host._log("[Manual] Mark recorded.")
        except Exception as exc:
            host._log("[Manual] Mark failed: %s" % exc)

    def _on_ready(self):
        self._ready.set()
        _make_transparent(self._window, self._host)
        if self._snapshot:
            self._push(self._snapshot)
        # _show_gui's show() runs in the same breath as _create(), which can be
        # before the native window is realised; that show is lost inside an
        # `except: pass`. Showing again here - after the page has handshaked -
        # is the reliable point, and matches how the toast has always done it.
        if self._open and self._window:
            try:
                self._window.show()
                self._window.on_top = True
            except Exception as exc:
                self._log("[Overlay] show on ready failed: %s" % exc)

    def _push(self, data):
        if not self._window:
            return

        def run():
            try:
                payload = json.dumps(data, ensure_ascii=False)
                self._window.evaluate_js("window.overlayUpdate(%s)" % payload)
            except Exception as exc:
                self._log("[Overlay] push failed: %s" % exc)

        # _show_gui and _sync_gui both reach here on the GUI thread, where
        # evaluate_js deadlocks. See _off_gui.
        _off_gui(run)

    def destroy(self):
        def teardown():
            self._open = False
            if self._window:
                try:
                    self._window.destroy()
                except Exception:
                    pass
            self._window = None

        _run_on_gui(self._host, teardown)

    def _log(self, msg):
        host = self._host
        if host and hasattr(host, "_log"):
            host._log(msg)


# --- facade -------------------------------------------------------------------

class NebulaWindows:
    """Both auxiliary windows — what ``NebulaHost`` should own."""

    def __init__(self, host, config):
        self._host = host
        self._config = config
        self._teardown_lock = threading.Lock()
        self._teardown_done = False
        reclaim_orphan_windows()
        self.toast = ToastController(host)
        self.overlay = OverlayController(host, config)
        self._liveness = _LivenessWatch(self)
        atexit.register(self._atexit_teardown)

    def toast_replace(self, event, display_name, details=None):
        self.toast.replace(event, display_name, details)

    def overlay_show(self):
        self.overlay.show()

    def overlay_hide(self, restore=False):
        self.overlay.hide(restore=restore)

    def overlay_sync(self):
        self.overlay.sync()

    def _atexit_teardown(self):
        try:
            self.destroy()
        except Exception:
            pass

    def _teardown_without_host(self):
        with self._teardown_lock:
            if self._teardown_done:
                return
            self._teardown_done = True
        if getattr(self, "_liveness", None):
            self._liveness.stop()
        _force_destroy_controller(self.toast)
        _force_destroy_controller(self.overlay)

    def destroy(self):
        with self._teardown_lock:
            if self._teardown_done:
                return
            self._teardown_done = True
        if getattr(self, "_liveness", None):
            self._liveness.stop()
        self.toast.destroy()
        self.overlay.destroy()


# --- demo / screenshot helper -----------------------------------------------

class _DemoHost:
    """Minimal host for ``python -m spike.windows`` screenshots."""

    def __init__(self):
        self.window = None
        self._current_game = "Helldivers 2"
        self._tray_game = self._current_game
        self._tray_elapsed = "01:47:22"
        self._is_recording = True
        self._visible = False

    def hero_state(self):
        return "recording"

    def hero_readouts(self):
        return {"elapsed": self._tray_elapsed, "size": "4.2 GB", "bitrate": "12.4 Mb/s"}

    def call_soon(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def show(self):
        self._visible = True

    def hide(self):
        self._visible = False

    def _toggle_pause(self):
        pass

    def _toggle_record(self):
        pass

    def _log(self, msg):
        print(msg)


def _demo_boot(windows):
    time.sleep(1.2)
    windows.toast_replace("start", "Helldivers 2", {"duration": 107, "size": 4_500_000_000})
    time.sleep(0.8)
    windows.overlay_show()


def demo():
    """Launch toast + overlay for visual verification.

        python -m spike.windows
    """
    from obsauto.config import load_config

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    host = _DemoHost()
    cfg = load_config()
    windows = NebulaWindows(host, cfg)

    # Hidden master window — pywebview needs one before start().
    master = webview.create_window(
        "Nebula",
        html="<html><body style='margin:0;background:#0A0812'></body></html>",
        width=400,
        height=300,
        hidden=True,
        frameless=True,
    )
    host.window = master

    def boot():
        threading.Thread(target=_demo_boot, args=(windows,), daemon=True).start()

    webview.start(boot, debug=False)
    windows.destroy()
    try:
        master.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    demo()
