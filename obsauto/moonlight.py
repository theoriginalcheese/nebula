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


def quit_host_app(host, configured_path=""):
    """Ask the host (Sunshine) to quit the running app. Returns error or None."""
    exe = find_exe(configured_path)
    host = (host or "").strip()
    if not exe:
        return "Moonlight.exe not found"
    if not host:
        return "moonlight_host is blank"
    try:
        subprocess.Popen(
            [exe, "quit", host],
            cwd=os.path.dirname(exe) or None,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
        )
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


def disconnect_client(proc=None):
    """End the local Moonlight process we started, if still running."""
    if proc is None:
        return False
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
            return True
    except OSError:
        pass
    return False
