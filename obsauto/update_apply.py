"""Visible packaged update: a small window, then the exe swap.

The build you are leaving does this, not the one being installed. It copies
itself to ``_nebula_updater.exe`` (Windows will read a running image), shows
the window, waits until Nebula has actually quit, then copies the download
over ``Nebula.exe`` and starts that. A silent helper is what made an update
look like nothing had happened.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time

APPLY_FLAG = "--apply-update"
UPDATER_NAME = "_nebula_updater.exe"

# Stages the bar is allowed to show. Each one is a real step, not a guess.
_WAIT = "Waiting for Nebula to close…"
_REPLACE = "Replacing Nebula…"
_CHECK = "Verifying the new file…"
_START = "Starting Nebula…"


def _log(target, message):
    try:
        folder = os.path.join(os.path.dirname(os.path.abspath(target)), "logs")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "update-apply.log")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except OSError:
        pass


def pid_alive(pid):
    """True when ``pid`` is still running.

    ``OpenProcess`` succeeds for a process that has already exited if anything
    still holds a handle. ``WaitForSingleObject`` is what tells those apart.
    """
    if not pid or pid < 0:
        return False
    try:
        import ctypes
        SYNCHRONIZE = 0x00100000
        WAIT_TIMEOUT = 0x102
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _spawn(target):
    """Start ``target`` detached, without inheriting a PyInstaller unpack dir."""
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [target], cwd=os.path.dirname(target), close_fds=True,
        creationflags=flags, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)


def apply_downloaded_exe(target, source, pid, on_status=None, cancel=None,
                         launch=True):
    """Wait for ``pid`` to exit, copy ``source`` onto ``target``, start it.

    ``on_status(text, percent)`` is called from this thread. ``cancel`` is a
    ``threading.Event`` checked only while waiting — once the copy starts,
    cancelling would leave a half-written exe, so it is ignored.
    """
    def report(text, pct):
        if on_status:
            on_status(text, int(pct))

    target = os.path.abspath(target)
    source = os.path.abspath(source)
    # Staged beside the exe, then swapped with os.replace. A failed copy must
    # not leave a half-written Nebula.exe, because this process only runs
    # after the old one has already quit.
    staged = target + ".new"
    replaced = False
    try:
        if not os.path.isfile(source):
            raise RuntimeError("Update file missing: %s" % source)

        report(_WAIT, 8)
        for i in range(120):
            if cancel is not None and cancel.is_set():
                raise RuntimeError("Update cancelled. Nebula was not changed.")
            if not pid_alive(pid):
                break
            report(_WAIT, min(40, 8 + i // 3))
            time.sleep(0.5)
        else:
            raise RuntimeError(
                "Nebula didn't close, so the new version was not installed.")
        if cancel is not None and cancel.is_set():
            raise RuntimeError("Update cancelled. Nebula was not changed.")

        report(_REPLACE, 60)
        try:
            os.remove(staged)
        except OSError:
            pass
        for _attempt in range(20):
            try:
                shutil.copyfile(source, staged)
                break
            except OSError:
                time.sleep(0.4)
        else:
            raise RuntimeError(
                "Couldn't write the new Nebula.exe. "
                "The installed copy was not changed.")

        report(_CHECK, 88)
        if (os.path.getsize(staged) != os.path.getsize(source)
                or _sha256(staged) != _sha256(source)):
            raise RuntimeError(
                "The new file didn't match the download. "
                "Nebula was not changed.")
        try:
            os.replace(staged, target)
        except OSError as exc:
            raise RuntimeError(
                "Couldn't replace Nebula.exe (%s). "
                "The installed copy was not changed." % exc) from exc
        replaced = True

        report(_START, 100)
        _log(target, "replaced %s with %s (%s bytes)" % (
            target, source, os.path.getsize(target)))
        if launch:
            _spawn(target)
        try:
            os.remove(source)
        except OSError:
            pass
        return target
    except Exception as exc:
        if not replaced:
            try:
                os.remove(staged)
            except OSError:
                pass
        if launch and os.path.isfile(target):
            try:
                _spawn(target)
            except OSError:
                pass
            else:
                raise RuntimeError(
                    "%s Nebula is opening again." % exc) from exc
        raise


def _parse_apply_argv(argv):
    args = list(argv or [])
    if APPLY_FLAG not in args:
        return None
    out = {"target": "", "source": "", "pid": 0}
    i = 0
    while i < len(args):
        if args[i] == "--target" and i + 1 < len(args):
            out["target"] = args[i + 1]
            i += 2
            continue
        if args[i] == "--source" and i + 1 < len(args):
            out["source"] = args[i + 1]
            i += 2
            continue
        if args[i] == "--pid" and i + 1 < len(args):
            try:
                out["pid"] = int(args[i + 1])
            except ValueError:
                out["pid"] = 0
            i += 2
            continue
        i += 1
    return out


def cleanup_updater_copy():
    """Remove a leftover ``_nebula_updater.exe`` once this copy is the real app.

    The updater cannot delete itself while it is running. The next normal
    launch does. A failure (still in use, missing) is ignored.
    """
    if os.path.basename(sys.executable).lower() == UPDATER_NAME.lower():
        return
    path = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                        UPDATER_NAME)
    try:
        os.remove(path)
    except OSError:
        pass


def run_from_argv(argv):
    """Entry for ``Nebula.exe --apply-update``. Returns a process exit code."""
    parsed = _parse_apply_argv(argv)
    if not parsed or not parsed["target"] or not parsed["source"]:
        return 0
    try:
        run_apply_window(parsed["target"], parsed["source"], parsed["pid"])
    except Exception as exc:
        _log(parsed["target"], "updater failed: %s" % exc)
        return 1
    return 0


def stage_for_status(text):
    """Map a swap status line onto the dialog's stages.

    The bar in the design is waiting, replacing, then starting. The hash
    check is part of replacing: it happens before the new exe is started,
    and the design has no fourth segment and no percent.
    """
    text = text or ""
    lowered = text.lower()
    if "cancelled" in lowered:
        return "cancelled"
    if (text.startswith("Couldn't") or text.startswith("Nebula didn't")
            or "not changed" in text or "didn't match" in text
            or "wrong size" in text or text.startswith("Update file missing")):
        return "failed"
    if text == _START or text.startswith("Starting"):
        return "starting"
    if (text == _REPLACE or text == _CHECK or text.startswith("Replacing")
            or text.startswith("Verifying")):
        return "replacing"
    return "waiting"


def _update_page():
    """The dialog page, from the bundle when frozen and the checkout otherwise."""
    from obsauto.paths import RESOURCE_DIR
    return os.path.join(RESOURCE_DIR, "spike", "web", "update.html")


def _dpi_aware():
    """Per-monitor v2 so 440×188 is the design's size, not a stretched bitmap."""
    try:
        import ctypes
        fn = ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_bool
        if fn(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


# How long the design holds "Updated" before the window leaves, and the
# leave itself. Neither delays the file swap.
_DONE_HOLD_S = 1.8
_GONE_S = 0.7
_WIN_W, _WIN_H = 440, 188


def run_apply_window(target, source, pid, launch=True):
    """The design's update dialog, then :func:`apply_downloaded_exe`."""
    if os.name != "nt":
        apply_downloaded_exe(target, source, pid, launch=launch)
        return
    _dpi_aware()
    window = _UpdateWindow()
    window.run(target, source, pid, launch=launch)


class _UpdateApi:
    """JS bridge. The window object stays private so pywebview will not walk it."""

    def __init__(self, host):
        self._host = host

    def ready(self):
        self._host.on_ready()

    def request_cancel(self):
        self._host.request_cancel()

    def request_close(self):
        self._host.request_close()


class _UpdateWindow:
    """Frameless WebView2 dialog. Its own surface, same idea as the toast.

    Locked 2026-10-03. Do not restyle this window. See
    design/update-window/LOCKED.txt.
    """

    def __init__(self):
        self._window = None
        self._api = _UpdateApi(self)
        self.cancel = threading.Event()
        self.phase = "waiting"
        self.allow_close = False
        self._ready = threading.Event()
        self._pending = None
        self._target = ""

    def report(self, text, _pct):
        # ``_pct`` is the swap's internal fraction. The dialog does not show it.
        if self.cancel.is_set() or self.phase in (
                "done", "gone", "failed", "cancelled"):
            return
        self._push(stage_for_status(text))

    def on_ready(self):
        self._ready.set()
        try:
            print("WINDOW_READY", flush=True)
        except (OSError, AttributeError):
            pass
        pending = self._pending
        if pending:
            self._push(pending)

    def request_cancel(self):
        if self.phase != "waiting":
            return
        self.cancel.set()
        self.phase = "cancelled"

    def request_close(self):
        if self.phase not in ("failed", "cancelled"):
            return
        self._close()

    def _push(self, stage):
        self.phase = stage
        win = self._window
        if not win or not self._ready.is_set():
            self._pending = stage
            return
        self._pending = None
        try:
            win.evaluate_js(
                "window.nebulaUpdate&&window.nebulaUpdate.setStage(%s)"
                % json.dumps(stage))
        except Exception:
            self._pending = stage

    def _close(self):
        self.allow_close = True
        win = self._window
        if not win:
            return
        try:
            win.destroy()
        except Exception as exc:
            error = str(exc)
            _log(self._target, "update window close: %s" % error)

    def _on_closing(self):
        if self.allow_close or self.phase in ("failed", "cancelled", "gone"):
            return True
        if self.phase == "waiting":
            self.cancel.set()
            threading.Thread(
                target=lambda: self._push("cancelled"), daemon=True).start()
        return False

    def _clip(self):
        """22px corner, in physical pixels. CSS radius cannot round the HWND."""
        win = self._window
        if win is None:
            return
        try:
            import ctypes
            hwnd = int(win.native.Handle.ToInt64())
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            dwmapi = ctypes.windll.dwmapi
            user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            user32.GetWindowRect.restype = ctypes.c_int
            user32.SetWindowRgn.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
            user32.SetWindowRgn.restype = ctypes.c_int
            gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p
            gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
            dwmapi.DwmSetWindowAttribute.argtypes = [
                ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
            rect = ctypes.wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width < 8 or height < 8:
                return
            radius = int(round(22 * height / float(_WIN_H)))
            donot = ctypes.c_int(1)  # DWMWCP_DONOTROUND
            dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(donot), ctypes.sizeof(donot))
            no_border = ctypes.c_int(0xFFFFFFFE)  # DWMWA_COLOR_NONE
            dwmapi.DwmSetWindowAttribute(
                hwnd, 34, ctypes.byref(no_border), ctypes.sizeof(no_border))
            no_backdrop = ctypes.c_int(1)  # DWMSBT_NONE
            dwmapi.DwmSetWindowAttribute(
                hwnd, 38, ctypes.byref(no_backdrop), ctypes.sizeof(no_backdrop))
            region = gdi32.CreateRoundRectRgn(
                0, 0, width + 1, height + 1, radius * 2, radius * 2)
            if not region:
                return
            if not user32.SetWindowRgn(hwnd, region, True):
                gdi32.DeleteObject(region)
        except Exception as exc:
            error = str(exc)
            _log(self._target, "update window clip: %s" % error)

    def run(self, target, source, pid, launch=True):
        import webview
        self._target = target
        page = _update_page()
        if not os.path.isfile(page):
            raise RuntimeError("Update window page missing: %s" % page)
        self._window = webview.create_window(
            "Nebula",
            page,
            js_api=self._api,
            width=_WIN_W,
            height=_WIN_H,
            min_size=(_WIN_W, _WIN_H),
            frameless=True,
            easy_drag=False,
            on_top=True,
            resizable=False,
            shadow=True,
            focus=True,
            text_select=False,
            zoomable=False,
            background_color="#0A0812",
        )
        if self._window is None:
            raise RuntimeError("Couldn't open the update window")
        self._window.events.closing += self._on_closing
        self._window.events.shown += lambda: self._clip()

        def work():
            self._ready.wait(15)
            error = ""
            try:
                apply_downloaded_exe(
                    target, source, pid,
                    on_status=self.report, cancel=self.cancel, launch=launch)
            except Exception as exc:
                error = str(exc)
                _log(target, "updater window: %s" % error)
            if error:
                if "cancelled" in error.lower():
                    self._push("cancelled")
                else:
                    self._push("failed")
                return
            self._push("done")
            time.sleep(_DONE_HOLD_S)
            self._push("gone")
            time.sleep(_GONE_S)
            self._close()

        threading.Thread(target=work, daemon=True).start()
        webview.start()
