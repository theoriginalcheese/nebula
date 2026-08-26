"""Detect whether Discord currently has an *active voice/video call*.

Used by the monitor to hold a recording across game switches while Anthony is
in a call with friends — not merely because Discord.exe is open in the
background (the common case).

Signal (preferred → fallback):
  1. UI Automation names on Discord's HWNDs that only appear in a live call
     ("Voice Connected", "Return to Call", "Leave Call", …).
  2. Discord window titles that explicitly mention a call / voice connected.

No Discord developer app, no OAuth, no new dependencies. comtypes is already
pulled in by pycaw for AudioKeepAlive.

Honesty rule: return False when Discord is not running, when UIA/title probes
fail, or when nothing matches. Never invent a call from "Discord is open" or
from WASAPI peaks alone (YouTube-in-Discord would false-positive).
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

# Deferred, not module-level: comtypes + psutil cost ~27 ms together and
# Discord detection first runs from the monitor's poll loop - long after the
# window exists (same pattern as steam_scanner/gamesync). Tri-state globals:
# None = not probed yet, module = ok, False = tried and unavailable.
comtypes = None
_COMTYPES = None
psutil = None
_PSUTIL = None


def _comtypes_mod():
    global comtypes, _COMTYPES
    if _COMTYPES is None:
        try:
            import comtypes as _ct
            import comtypes.client  # noqa: F401 - GetModule needs it wired
            comtypes = _ct
            _COMTYPES = True
        except Exception:  # pragma: no cover - optional at runtime
            comtypes = False
            _COMTYPES = False
    return comtypes or None


def _psutil_mod():
    global psutil, _PSUTIL
    if _PSUTIL is None:
        try:
            import psutil as _p
            psutil = _p
            _PSUTIL = True
        except Exception:  # pragma: no cover - optional at runtime
            psutil = False
            _PSUTIL = False
    return psutil or None

# Names Discord exposes in its a11y tree / titles only while a call is live.
# Kept lowercase; matching is substring on the lowered name.
_VOICE_NAME_HINTS = (
    "voice connected",
    "return to call",
    "leave call",
    "end call",
    "disconnect from voice",
    "you are still in the voice channel",
)

# Title-only hints (main Chrome_WidgetWin_1 title is usually "Server - Discord"
# even in a call; these catch PiP / legacy / overlay chrome when present).
_VOICE_TITLE_HINTS = (
    "voice connected",
    "discord call",
    "in a call",
)

# Walking Discord's Electron tree every poll is expensive (~100ms+). Cache.
_CACHE_TTL_S = 2.0
_cache_until = 0.0
_cache_value = False

# Depth/breadth caps so a hung a11y tree can't stall the monitor loop.
_MAX_DEPTH = 18
_MAX_NODES = 2500
_MAX_HITS_SHORTCIRCUIT = 1


def _discord_pids():
    psutil_mod = _psutil_mod()
    if psutil_mod is None:
        return set()
    out = set()
    try:
        for proc in psutil_mod.process_iter(["name", "pid"]):
            name = (proc.info.get("name") or "").lower()
            if name == "discord.exe":
                out.add(proc.info["pid"])
    except Exception:
        return set()
    return out


def _discord_hwnds(pids):
    """Visible top-level Discord HWNDs with their titles."""
    if not pids:
        return []
    user32 = ctypes.windll.user32
    found = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        found.append((int(hwnd), buf.value or ""))
        return True

    try:
        user32.EnumWindows(EnumWindowsProc(cb), 0)
    except Exception:
        return []
    return found


def _title_says_call(title):
    low = (title or "").lower()
    return any(h in low for h in _VOICE_TITLE_HINTS)


def _name_says_call(name):
    low = (name or "").lower()
    return any(h in low for h in _VOICE_NAME_HINTS)


def _uia_discord_in_call(hwnds):
    """Walk Discord HWND a11y trees for voice-call chrome. False on any failure."""
    ct = _comtypes_mod()
    if ct is None or not hwnds:
        return False
    try:
        ct.CoInitialize()
    except Exception:
        pass
    try:
        uia_mod = ct.client.GetModule("UIAutomationCore.dll")
        uia = ct.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=uia_mod.IUIAutomation,
        )
        walker = uia.ControlViewWalker
    except Exception:
        return False

    nodes = 0

    def walk(element, depth):
        nonlocal nodes
        if depth > _MAX_DEPTH or nodes >= _MAX_NODES:
            return False
        nodes += 1
        try:
            name = element.CurrentName or ""
        except Exception:
            name = ""
        if _name_says_call(name):
            return True
        try:
            child = walker.GetFirstChildElement(element)
        except Exception:
            return False
        while child is not None:
            if walk(child, depth + 1):
                return True
            if nodes >= _MAX_NODES:
                return False
            try:
                child = walker.GetNextSiblingElement(child)
            except Exception:
                break
        return False

    for hwnd, _title in hwnds:
        try:
            el = uia.ElementFromHandle(hwnd)
        except Exception:
            continue
        if el is None:
            continue
        try:
            if walk(el, 0):
                return True
        except Exception:
            continue
    return False


def discord_voice_active(force=False):
    """True only when Discord shows an active voice/video call.

    Returns False when unknown / Discord absent / probe failed. Callers must
    not treat False as "definitely not in a call" for destructive actions —
    only as "do not enable the hold-across-switch behaviour".
    """
    global _cache_until, _cache_value
    now = time.time()
    if not force and now < _cache_until:
        return _cache_value

    value = False
    try:
        pids = _discord_pids()
        if pids:
            hwnds = _discord_hwnds(pids)
            if any(_title_says_call(t) for _, t in hwnds):
                value = True
            elif _uia_discord_in_call(hwnds):
                value = True
    except Exception:
        value = False

    _cache_value = value
    _cache_until = now + _CACHE_TTL_S
    return value


def _reset_cache_for_tests():
    """Test helper — clear the TTL cache between cases."""
    global _cache_until, _cache_value
    _cache_until = 0.0
    _cache_value = False
