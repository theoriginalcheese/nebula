"""TeraCopy CLI helper — soft optional, like ffmpeg / Moonlight.

Used by the NAS offloader for the bulk transfer. Nebula still SHA-256 verifies
both ends afterwards; TeraCopy never becomes the delete authority.

    TeraCopy.exe Copy <source-file> <dest-folder> /OverwriteAll /Close

Target is always a folder (TeraCopy's rule). We stage into a temp subfolder,
verify, then atomically promote into place.

TeraCopy has **no** official silent/headless switch — ``/Close`` only exits
after the copy, and the UI still opens during the transfer. We therefore:
  1. start it with CREATE_NO_WINDOW + SW_HIDE, and
  2. keep hammering ShowWindow(SW_HIDE) on every top-level HWND owned by that
     PID until it exits, so the window never settles on screen.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time

from .silent_proc import run_kwargs

_FALLBACKS = (
    r"C:\Program Files\TeraCopy\TeraCopy.exe",
    r"C:\Program Files (x86)\TeraCopy\TeraCopy.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\TeraCopy\TeraCopy.exe"),
)

_which_cache = None

# Win32 ShowWindow nCmdShow
_SW_HIDE = 0


def _reset_cache():
    global _which_cache
    _which_cache = None


def find_exe(configured=""):
    """Absolute path to TeraCopy.exe, or \"\" if not installed."""
    global _which_cache
    configured = (configured or "").strip()
    if configured and os.path.isfile(configured):
        return configured
    if _which_cache is not None:
        return _which_cache or ""
    found = shutil.which("TeraCopy") or shutil.which("TeraCopy.exe") or ""
    if found and os.path.isfile(found):
        _which_cache = found
        return found
    for path in _FALLBACKS:
        if os.path.isfile(path):
            _which_cache = path
            return path
    _which_cache = False
    return ""


def available(configured=""):
    return bool(find_exe(configured))


def _timeout_for(src):
    """Generous wall clock — TeraCopy is fast, but a huge clip over Tailscale
    still needs headroom. Floor 120s, ~30 MiB/s worst-case estimate."""
    try:
        size = os.path.getsize(src)
    except OSError:
        size = 0
    return max(120, int(size / (30 * 1024 * 1024)) + 120)


def _hide_pid_windows(pid):
    """Hide every top-level window owned by ``pid`` (best-effort, Windows)."""
    if os.name != "nt" or not pid:
        return 0
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return 0

    user32 = ctypes.windll.user32
    hidden = 0

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        nonlocal hidden
        proc = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
        if proc.value != pid:
            return True
        # Hide even if not yet "visible" — TeraCopy often creates then shows.
        if user32.IsWindow(hwnd):
            user32.ShowWindow(hwnd, _SW_HIDE)
            hidden += 1
        return True

    try:
        user32.EnumWindows(_enum, 0)
    except Exception:
        return 0
    return hidden


def _window_suppressor(pid, stop_event, interval=0.05):
    """Tight loop: TeraCopy can recreate/show its main window mid-transfer."""
    while not stop_event.wait(interval):
        try:
            _hide_pid_windows(pid)
        except Exception:
            pass


def copy_into(src, dest_dir, configured="", log=None):
    """Copy ``src`` into ``dest_dir`` via TeraCopy (same basename).

    Returns the resulting file path. Raises ``OSError`` / ``RuntimeError`` on
    failure so callers can fall back to the built-in copier.
    """
    log = log or (lambda msg: None)
    exe = find_exe(configured)
    if not exe:
        raise RuntimeError("TeraCopy not found")
    src = os.path.abspath(src)
    dest_dir = os.path.abspath(dest_dir)
    if not os.path.isfile(src):
        raise OSError("Source missing: %s" % src)
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, os.path.basename(src))

    cmd = [exe, "Copy", src, dest_dir, "/OverwriteAll", "/Close"]
    log("[Offload] TeraCopy → %s (background)" % dest_dir)
    kwargs = run_kwargs()
    kwargs.update({
        "cwd": os.path.dirname(exe),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    })
    # Prefer Popen so we can suppress windows for the whole lifetime.
    stop = threading.Event()
    suppressor = None
    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except OSError as exc:
        raise RuntimeError("TeraCopy failed to start: %s" % exc) from exc

    try:
        # Hide immediately, then keep suppressing until exit.
        _hide_pid_windows(proc.pid)
        suppressor = threading.Thread(
            target=_window_suppressor,
            args=(proc.pid, stop),
            name="teracopy-hide",
            daemon=True,
        )
        suppressor.start()
        try:
            proc.wait(timeout=_timeout_for(src))
        except subprocess.TimeoutExpired as exc:
            try:
                proc.kill()
            except OSError:
                pass
            raise RuntimeError("TeraCopy timed out") from exc
    finally:
        stop.set()
        if suppressor is not None:
            suppressor.join(timeout=1.0)

    # Give the filesystem a beat after /Close before we inspect the result.
    deadline = time.time() + 8
    while time.time() < deadline:
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            break
        time.sleep(0.15)
    else:
        raise RuntimeError(
            "TeraCopy finished without a destination file (exit %s)"
            % getattr(proc, "returncode", "?"))

    try:
        if os.path.getsize(out) != os.path.getsize(src):
            raise RuntimeError(
                "TeraCopy size mismatch (%s vs %s)" % (
                    os.path.getsize(out), os.path.getsize(src)))
    except OSError as exc:
        raise RuntimeError("TeraCopy output unreadable: %s" % exc) from exc
    return out
