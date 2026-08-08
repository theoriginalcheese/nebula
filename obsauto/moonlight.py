"""Launch and control Moonlight from Nebula — soft optional, like ffmpeg.

Moonlight has no embed API. This module drives the official CLI:

    Moonlight.exe stream <host> "<app>" [--display-mode …]
    Moonlight.exe quit <host>
    Moonlight.exe   (no args — open the UI for pairing)

Never invents a host. Blank ``moonlight_host`` means Connect stays disabled.
Also reads the newest ``%TEMP%\\Moonlight-*.log`` for honest client facts
(version, last seen host/address) — same source ``session_detect`` uses.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tempfile
import time

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_FALLBACKS = (
    r"C:\Program Files\Moonlight Game Streaming\Moonlight.exe",
    r"C:\Program Files (x86)\Moonlight Game Streaming\Moonlight.exe",
    os.path.expandvars(
        r"%LOCALAPPDATA%\Programs\Moonlight Game Streaming\Moonlight.exe"),
)

_LOG_GLOB = os.path.join(tempfile.gettempdir(), "Moonlight-*.log")
_RE_VERSION = re.compile(r'Current Moonlight version:\s*"([^"]+)"')
_RE_ONLINE_AT = re.compile(r'"([^"]+)" is now online at "([^"]+)"')
_RE_NOW_AT = re.compile(r'"([^"]+)" is now at "([^"]+)"')
_RE_TS_ADDR = re.compile(r'QHostAddress\("(100\.\d+\.\d+\.\d+)"\)')
_START_MARKER = "Starting video stream"
_STOP_MARKER = "Stopping video stream"

_which_cache = None
_path_cache = None


def _reset_cache():
    global _which_cache, _path_cache
    _which_cache = None
    _path_cache = None


def find_exe(configured=""):
    """Resolve Moonlight.exe: config path, then PATH, then known installs."""
    global _path_cache
    configured = (configured or "").strip()
    if configured and os.path.isfile(configured):
        return configured
    if _path_cache is not None:
        return _path_cache or None
    found = shutil.which("Moonlight") or shutil.which("moonlight")
    if not found:
        for path in _FALLBACKS:
            if os.path.isfile(path):
                found = path
                break
    _path_cache = found or False
    return found or None


def available(configured=""):
    return bool(find_exe(configured))


def _newest_log():
    logs = glob.glob(_LOG_GLOB)
    if not logs:
        return None
    try:
        return max(logs, key=os.path.getmtime)
    except OSError:
        return None


def _age_label(seconds):
    """Short relative age for UI — only when we have a real mtime."""
    if seconds is None or seconds < 0:
        return ""
    sec = int(seconds)
    if sec < 60:
        return "just now" if sec < 5 else "%ds ago" % sec
    mins = sec // 60
    if mins < 60:
        return "%dm ago" % mins
    hours = mins // 60
    if hours < 48:
        return "%dh ago" % hours
    return "%dd ago" % (hours // 24)


def log_details():
    """Facts from the newest Moonlight log. Empty dict if none / unreadable.

    Never invents a host — only what the log literally wrote.
    """
    path = _newest_log()
    if not path:
        return {}
    try:
        mtime = os.path.getmtime(path)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return {}

    version = ""
    vers = _RE_VERSION.findall(text)
    if vers:
        version = vers[-1].strip()

    host = ""
    address = ""
    # Prefer the most recent "is now at" (Tailscale/LAN move); else "online at".
    at = _RE_NOW_AT.findall(text)
    online = _RE_ONLINE_AT.findall(text)
    if at:
        host, address = at[-1][0].strip(), at[-1][1].strip()
    elif online:
        host, address = online[-1][0].strip(), online[-1][1].strip()

    ts_ips = []
    for ip in _RE_TS_ADDR.findall(text):
        if ip not in ts_ips:
            ts_ips.append(ip)

    last_start = text.rfind(_START_MARKER)
    last_stop = text.rfind(_STOP_MARKER)
    if last_start == -1 and last_stop == -1:
        stream = "none"
    elif last_start > last_stop:
        stream = "live"
    else:
        stream = "stopped"

    age_s = max(0.0, time.time() - mtime)
    out = {
        "log_path": path,
        "log_age_s": age_s,
        "log_age": _age_label(age_s),
        "stream": stream,
    }
    if version:
        out["version"] = version
    if host:
        out["last_host"] = host
    if address:
        out["last_address"] = address
    if ts_ips:
        out["tailscale_ips"] = ts_ips
    return out


def stream_args(host, app, display_mode="borderless", resolution=None,
                fps=None, bitrate=None):
    """Build argv after the executable for ``stream``."""
    host = (host or "").strip()
    app = (app or "").strip() or "Desktop"
    if not host:
        raise ValueError("moonlight_host is blank")
    args = ["stream", host, app]
    mode = (display_mode or "borderless").strip().lower()
    if mode in ("borderless", "fullscreen", "windowed"):
        args.extend(["--display-mode", mode])
    if resolution:
        args.append(resolution if resolution.startswith("--")
                    else "--%s" % resolution.lstrip("-"))
    if fps:
        args.extend(["--fps", str(int(fps))])
    if bitrate:
        args.extend(["--bitrate", str(int(bitrate))])
    return args


def start_stream(host, app, configured_path="", display_mode="borderless",
                 resolution=None, fps=None, bitrate=None):
    """Spawn Moonlight streaming. Returns (Popen, None) or (None, error)."""
    exe = find_exe(configured_path)
    if not exe:
        return None, "Moonlight.exe not found"
    try:
        args = [exe] + stream_args(
            host, app, display_mode=display_mode,
            resolution=resolution, fps=fps, bitrate=bitrate)
    except ValueError as exc:
        return None, str(exc)
    try:
        # Stream needs a real window — do not CREATE_NO_WINDOW.
        proc = subprocess.Popen(
            args,
            cwd=os.path.dirname(exe) or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc, None
    except OSError as exc:
        return None, str(exc)


def _hidden_startupinfo():
    """STARTUPINFO that keeps a brief Moonlight helper from flashing a window."""
    if os.name != "nt":
        return None
    try:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0  # SW_HIDE
        return info
    except (AttributeError, OSError):
        return None


def quit_host_app(host, configured_path=""):
    """Ask the host (Sunshine) to quit the running app. Returns error or None."""
    exe = find_exe(configured_path)
    host = (host or "").strip()
    if not exe:
        return "Moonlight.exe not found"
    if not host:
        return "moonlight_host is blank"
    try:
        # ``quit`` is a one-shot helper — hide it hard. CREATE_NO_WINDOW alone
        # is not enough for Qt; without SW_HIDE the Moonlight chrome flashes.
        kwargs = {
            "cwd": os.path.dirname(exe) or None,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "creationflags": _CREATE_NO_WINDOW,
        }
        startup = _hidden_startupinfo()
        if startup is not None:
            kwargs["startupinfo"] = startup
        subprocess.Popen([exe, "quit", host], **kwargs)
        return None
    except OSError as exc:
        return str(exc)


def open_ui(configured_path=""):
    """Open Moonlight's own UI (pairing / host list). Returns (Popen, err)."""
    exe = find_exe(configured_path)
    if not exe:
        return None, "Moonlight.exe not found"
    try:
        proc = subprocess.Popen(
            [exe],
            cwd=os.path.dirname(exe) or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc, None
    except OSError as exc:
        return None, str(exc)


def _hide_pid_windows(pid):
    """SW_HIDE every top-level window owned by ``pid`` (best-effort, Windows)."""
    if os.name != "nt" or not pid:
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        SW_HIDE = 0
        handles = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum(hwnd, _lp):
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value == int(pid) and user32.IsWindowVisible(hwnd):
                handles.append(hwnd)
            return True

        user32.EnumWindows(_enum, 0)
        for hwnd in handles:
            user32.ShowWindow(hwnd, SW_HIDE)
    except (AttributeError, OSError, ValueError, TypeError):
        pass


def disconnect_client(proc=None):
    """End the local Moonlight process we started, if still running.

    Hide first, then kill — ``terminate()`` posts WM_CLOSE and Moonlight's
    home UI often flashes for a beat before exit.
    """
    if proc is None:
        return False
    try:
        if proc.poll() is not None:
            return False
        pid = getattr(proc, "pid", None)
        _hide_pid_windows(pid)
        try:
            proc.kill()
        except OSError:
            proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
        return True
    except OSError:
        pass
    return False


def _moonlight_pids(configured_path=""):
    """PIDs whose image is Moonlight.exe (best-effort)."""
    exe = (find_exe(configured_path) or "").lower()
    want = {"moonlight.exe"}
    if exe:
        want.add(os.path.basename(exe))
    pids = []
    try:
        import psutil
    except ImportError:
        return pids
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            path = (proc.info.get("exe") or "").lower()
            if name in want or (exe and path == exe):
                pids.append(int(proc.info["pid"]))
        except (psutil.Error, TypeError, ValueError):
            continue
    return pids


def kill_all_clients(configured_path=""):
    """Hide every Moonlight window, then force-kill all Moonlight.exe.

    Nebula-started sessions often respawn the host-list UI after the stream
    process dies — one more flash. Ending *all* Moonlight processes is the
    quiet path Disconnect wants.
    """
    pids = _moonlight_pids(configured_path)
    for pid in pids:
        _hide_pid_windows(pid)
    killed = False
    try:
        import psutil
    except ImportError:
        psutil = None
    for pid in pids:
        if psutil is None:
            break
        try:
            p = psutil.Process(pid)
            p.kill()
            killed = True
        except (psutil.Error, OSError):
            continue
    if os.name == "nt":
        # Belt-and-braces: anything we missed (short-lived quit helper, etc.).
        try:
            kwargs = {
                "capture_output": True,
                "timeout": 5,
                "creationflags": _CREATE_NO_WINDOW,
            }
            startup = _hidden_startupinfo()
            if startup is not None:
                kwargs["startupinfo"] = startup
            result = subprocess.run(
                ["taskkill", "/F", "/IM", "Moonlight.exe", "/T"], **kwargs)
            if result.returncode == 0:
                killed = True
        except (OSError, subprocess.SubprocessError):
            pass
    return killed


def wait_until_streaming(proc=None, timeout=60.0, abort_event=None,
                         hide=True, poll=0.05, baseline_len=None):
    """Hold Moonlight back until the video stream is actually live.

    While waiting, optionally keep every Moonlight window hidden so it never
    steals the foreground before the stream is ready. Returns one of
    ``\"live\"``, ``\"timeout\"``, ``\"dead\"``, ``\"aborted\"``.

    ``baseline_len`` should be the Moonlight log size *before* ``start_stream``
    so a fast start still counts as new.
    """
    from . import session_detect as sd

    deadline = time.monotonic() + max(1.0, float(timeout))
    log_path = sd._newest_moonlight_log()
    if baseline_len is None:
        start_len = 0
        if log_path:
            try:
                start_len = os.path.getsize(log_path)
            except OSError:
                start_len = 0
    else:
        start_len = max(0, int(baseline_len))

    while time.monotonic() < deadline:
        if abort_event is not None and abort_event.is_set():
            return "aborted"
        if proc is not None and proc.poll() is not None:
            return "dead"
        if hide:
            hide_client_windows()
        # Fresh "Starting video stream" after we connected?
        if _stream_started_since(log_path, start_len):
            return "live"
        # Fallback: session_detect says live and the log moved.
        if sd.moonlight_session_active() is True and _log_grew(log_path, start_len):
            return "live"
        time.sleep(max(0.02, float(poll)))
    return "timeout"


def _log_grew(path, start_len):
    if not path:
        return False
    try:
        return os.path.getsize(path) > int(start_len)
    except OSError:
        return False


def _stream_started_since(path, start_len):
    """True if a Starting marker appears after ``start_len`` bytes."""
    if not path:
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(max(0, int(start_len)))
            chunk = f.read()
    except OSError:
        return False
    return "Starting video stream" in chunk


def hide_client_windows(configured_path=""):
    """SW_HIDE every visible Moonlight top-level window."""
    for pid in _moonlight_pids(configured_path):
        _hide_pid_windows(pid)


def reveal_client_windows(configured_path=""):
    """Show Moonlight windows and try to bring the stream to the front.

    Called only after ``wait_until_streaming`` reports live, so the user sees
    the remote desktop rather than Moonlight's host list.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        SW_SHOW = 5
        SW_RESTORE = 9
        pids = set(_moonlight_pids(configured_path))
        if not pids:
            return False
        shown = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def _enum(hwnd, _lp):
            proc_id = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
            if proc_id.value in pids and user32.IsWindow(hwnd):
                shown.append(hwnd)
            return True

        user32.EnumWindows(_enum, 0)
        target = None
        for hwnd in shown:
            # Prefer a visible-or-restorable window with a title (the stream).
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                continue
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.ShowWindow(hwnd, SW_SHOW)
            target = hwnd
        if target is None and shown:
            target = shown[0]
            user32.ShowWindow(target, SW_SHOW)
        if target is not None:
            try:
                user32.SetForegroundWindow(target)
            except Exception:
                pass
            return True
    except (AttributeError, OSError, ValueError, TypeError):
        pass
    return False


def end_session(proc=None, host="", configured_path=""):
    """Quiet teardown: hide → kill client(s) → ask Sunshine to quit the app.

    Returns ``{"client_closed": bool, "host_quit_error": str|None}``.
    """
    closed = disconnect_client(proc)
    # Stream process may have already exited, or Moonlight may have respawned
    # its chrome — sweep either way.
    if kill_all_clients(configured_path):
        closed = True
    quit_err = None
    if (host or "").strip():
        quit_err = quit_host_app(host, configured_path=configured_path)
    return {"client_closed": closed, "host_quit_error": quit_err}
