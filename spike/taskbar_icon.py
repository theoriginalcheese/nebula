"""Hover-only orbit animation for the Windows taskbar button.

Resting state is the static Nebula mark. While the cursor sits on *our*
taskbar button we rotate icon_art frames through ``Form.Icon`` /
``WM_SETICON``. Off-hover snaps back to rest.

Win11 hosts app buttons inside ``DesktopWindowContentBridge`` (XAML), not
under classic ``MSTaskListWClass`` toolbar messages. We resolve our button
via UI Automation on that bridge and hit-test its bounding rect.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time


def start(host):
    """Arm the hover-orbit thread on ``host``. Idempotent."""
    if getattr(host, "_taskbar_icon_thread", None) and host._taskbar_icon_thread.is_alive():
        return
    host._taskbar_icon_stop.clear()
    host._taskbar_icon_thread = threading.Thread(
        target=lambda: _run(host), daemon=True, name="nebula-taskbar-icon")
    host._taskbar_icon_thread.start()


def _run(host):
    import ctypes
    from ctypes import byref, c_long, Structure

    from obsauto.icon_art import generate_animation_frames, generate_static_icon

    user32 = ctypes.windll.user32
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x0010
    WM_SETICON = 0x0080
    ICON_SMALL, ICON_BIG = 0, 1
    GCL_HICON, GCL_HICONSM = -14, -34
    is_64 = ctypes.sizeof(ctypes.c_void_p) == 8
    SetClassLong = (user32.SetClassLongPtrW if is_64 else user32.SetClassLongW)

    poll_ms = 0.08
    tick_ms = 0.36
    idle_ms = 0.50
    rect_refresh_s = 1.0

    work = tempfile.mkdtemp(prefix="nebula-tbicon-")
    paths = []
    handles = []
    drawing_icons = []
    rest_drawing = None
    rest_handle = None

    try:
        rest_path = os.path.join(work, "rest.ico")
        generate_static_icon(size=32).save(
            rest_path, format="ICO", sizes=[(16, 16), (32, 32)])
        paths.append(rest_path)
        rest_handle = user32.LoadImageW(
            None, rest_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)

        frames = generate_animation_frames(size=32, n_frames=24)
        for i, frame in enumerate(frames):
            path = os.path.join(work, "f%02d.ico" % i)
            frame.save(path, format="ICO", sizes=[(16, 16), (32, 32)])
            paths.append(path)
            h = user32.LoadImageW(None, path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
            if h:
                handles.append(h)
        host._taskbar_icon_handles = list(handles) + (
            [rest_handle] if rest_handle else [])

        try:
            from System.Drawing import Icon as DrawingIcon
            from System.IO import MemoryStream

            with open(rest_path, "rb") as f:
                rest_drawing = DrawingIcon(MemoryStream(f.read()))
            for path in paths[1:]:
                with open(path, "rb") as f:
                    drawing_icons.append(DrawingIcon(MemoryStream(f.read())))
        except Exception as exc:
            host._log("[Icon] WinForms Icon build failed: %s" % exc)
            drawing_icons = []
            rest_drawing = None

        if not handles:
            host._log("[Icon] No taskbar HICONs loaded.")
            return

        host._log("[Icon] Taskbar hover-orbit armed (%d frames)." % len(handles))

        class POINT(Structure):
            _fields_ = [("x", c_long), ("y", c_long)]

        hwnd = 0
        idx = 0
        hovering = False
        applied_rest = False
        uia = _uia()
        button_rects = []
        last_rect_at = 0.0

        while not host._taskbar_icon_stop.is_set() and not host._quitting:
            try:
                hwnd = _resolve_hwnd(host, user32, hwnd)
                if not hwnd:
                    time.sleep(idle_ms)
                    continue
                if not user32.IsWindow(hwnd):
                    hwnd = 0
                    time.sleep(idle_ms)
                    continue

                mapped = bool(user32.IsWindowVisible(hwnd)) and (
                    not bool(user32.IsIconic(hwnd)))
                if not mapped:
                    if hovering:
                        hovering = False
                        applied_rest = False
                    time.sleep(idle_ms)
                    continue

                now = time.monotonic()
                if now - last_rect_at >= rect_refresh_s or not button_rects:
                    button_rects = _our_button_rects(uia)
                    last_rect_at = now

                pt = POINT()
                user32.GetCursorPos(byref(pt))
                over = _point_in_rects(pt.x, pt.y, button_rects)

                if over:
                    if not hovering:
                        hovering = True
                        idx = 0
                        host._log("[Icon] Taskbar hover — orbit.")
                    i = idx % len(handles)
                    _apply_icon(
                        host, user32, SetClassLong, hwnd,
                        handles[i],
                        drawing_icons[i] if drawing_icons else None,
                        GCL_HICON, GCL_HICONSM,
                        WM_SETICON, ICON_SMALL, ICON_BIG)
                    idx += 1
                    applied_rest = False
                    time.sleep(tick_ms)
                else:
                    if hovering or not applied_rest:
                        was = hovering
                        hovering = False
                        _apply_icon(
                            host, user32, SetClassLong, hwnd,
                            rest_handle or handles[0],
                            rest_drawing or (drawing_icons[0] if drawing_icons else None),
                            GCL_HICON, GCL_HICONSM,
                            WM_SETICON, ICON_SMALL, ICON_BIG)
                        applied_rest = True
                        if was:
                            host._log("[Icon] Taskbar hover ended — rest.")
                    time.sleep(poll_ms)
            except Exception:
                hwnd = 0
                hovering = False
                applied_rest = False
                button_rects = []
                time.sleep(idle_ms)

    except Exception as exc:
        host._log("[Icon] Taskbar orbit failed: %s" % exc)
    finally:
        for h in list(handles) + ([rest_handle] if rest_handle else []):
            if not h:
                continue
            try:
                user32.DestroyIcon(h)
            except Exception:
                pass
        host._taskbar_icon_handles = []
        try:
            for path in paths:
                try:
                    os.remove(path)
                except OSError:
                    pass
            os.rmdir(work)
        except OSError:
            pass


def _uia():
    try:
        import comtypes.client
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
        return comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
    except Exception:
        try:
            import comtypes.client
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
            return comtypes.client.CreateObject(CUIAutomation, interface=IUIAutomation)
        except Exception:
            return None


def _resolve_hwnd(host, user32, current):
    form = getattr(host.window, "native", None) if host.window else None
    if form is not None:
        try:
            return int(form.Handle.ToInt64())
        except Exception:
            pass
    if current and user32.IsWindow(current):
        return current
    return user32.FindWindowW(None, "Nebula") or 0


def _content_bridge_hwnds():
    import ctypes
    from ctypes import wintypes, WINFUNCTYPE, c_bool

    user32 = ctypes.windll.user32
    out = []

    @WINFUNCTYPE(c_bool, wintypes.HWND, wintypes.LPARAM)
    def on_top(hwnd, _lp):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if buf.value not in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return True

        @WINFUNCTYPE(c_bool, wintypes.HWND, wintypes.LPARAM)
        def on_child(child, _lp2):
            b2 = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child, b2, 256)
            if "DesktopWindowContentBridge" in b2.value:
                out.append(int(child))
            return True

        user32.EnumChildWindows(hwnd, on_child, 0)
        return True

    user32.EnumWindows(on_top, 0)
    return out


def _is_our_button_name(name):
    n = (name or "").strip().lower()
    if not n:
        return False
    if n.startswith("nebula"):
        return True
    # Dev / unpackaged runs still show as pythonw's "Python - …" on the bar.
    if n.startswith("python"):
        return True
    return False


def _our_button_rects(uia):
    """Screen rects of every taskbar button that is ours."""
    if uia is None:
        return []
    try:
        from comtypes.gen.UIAutomationClient import (
            TreeScope_Descendants,
            UIA_ButtonControlTypeId,
            UIA_ControlTypePropertyId,
        )
    except Exception:
        return []

    rects = []
    try:
        bcond = uia.CreatePropertyCondition(
            UIA_ControlTypePropertyId, UIA_ButtonControlTypeId)
    except Exception:
        return []

    for hwnd in _content_bridge_hwnds():
        try:
            el = uia.ElementFromHandle(hwnd)
            if el is None:
                continue
            btns = el.FindAll(TreeScope_Descendants, bcond)
        except Exception:
            continue
        try:
            count = int(btns.Length)
        except Exception:
            continue
        for i in range(count):
            try:
                btn = btns.GetElement(i)
                name = btn.CurrentName or ""
                if not _is_our_button_name(name):
                    continue
                r = btn.CurrentBoundingRectangle
                left, top, right, bottom = int(r.left), int(r.top), int(r.right), int(r.bottom)
                if right > left and bottom > top:
                    rects.append((left, top, right, bottom))
            except Exception:
                continue
    return rects


def _point_in_rects(x, y, rects):
    for left, top, right, bottom in rects:
        if left <= x < right and top <= y < bottom:
            return True
    return False


def _apply_icon(host, user32, SetClassLong, hwnd, hicon, drawing_icon,
                GCL_HICON, GCL_HICONSM, WM_SETICON, ICON_SMALL, ICON_BIG):
    if hicon:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
        try:
            SetClassLong(hwnd, GCL_HICON, hicon)
            SetClassLong(hwnd, GCL_HICONSM, hicon)
        except Exception:
            pass
    if drawing_icon is None:
        return
    form = getattr(host.window, "native", None) if host.window else None
    if form is None:
        return
    try:
        def set_it():
            form.Icon = drawing_icon
        if form.InvokeRequired:
            from System import Action
            form.BeginInvoke(Action(set_it))
        else:
            set_it()
    except Exception:
        pass
