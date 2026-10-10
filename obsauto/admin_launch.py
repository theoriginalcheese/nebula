"""Optional administrator relaunch for the dial hook.

HoYoPlay and the games it starts run elevated. A low-level keyboard hook
in a normal process is not called for keys aimed at an admin window, so
the knob does nothing until Nebula is admin too. That is opt-in: a new
install leaves ``run_as_administrator`` off and never shows a UAC prompt.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from ctypes import wintypes

_SKIP = ("--dev", "--allow-multi", "--toast-demo", "--apply-update")


def is_elevated():
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def should_elevate(flag, elevated, argv):
    """True when this process should hand off to an admin copy and leave.

    Already-admin, and the dev / update flags, never prompt.
    """
    if elevated or not flag:
        return False
    return not any(item in argv for item in _SKIP)


def config_wants_admin():
    """The saved switch, read before the rest of the app starts.

    A missing or unreadable config means off. A new user is not asked.
    """
    try:
        from obsauto.paths import APP_DIR
        path = os.path.join(APP_DIR, "config.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return False
    return bool(data.get("run_as_administrator"))


def _command():
    """Executable plus arguments for a relaunch of this same entry point."""
    if getattr(sys, "frozen", False):
        return sys.executable, subprocess.list2cmdline(sys.argv[1:])
    script = os.path.abspath(sys.argv[0])
    return sys.executable, subprocess.list2cmdline([script, *sys.argv[1:]])


def relaunch_elevated():
    """Show the UAC prompt and start an admin copy. True if it started."""
    if os.name != "nt" or is_elevated():
        return False
    target, params = _command()
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", target, params or None, os.getcwd(), 1)
    except Exception:
        return False
    return rc > 32


def relaunch_unelevated():
    """Start a normal copy from an admin process.

    A child of an admin process stays admin. Explorer's token is a normal
    one, so turning the setting off can actually drop back down.
    """
    if os.name != "nt" or not is_elevated():
        return False
    target, params = _command()
    cmdline = subprocess.list2cmdline([target]) if not params else (
        subprocess.list2cmdline([target]) + " " + params)
    try:
        return _create_as_shell(cmdline)
    except Exception:
        return False


def maybe_relaunch_elevated():
    """Leave this process when the setting asks for admin and we are not.

    Call this before the single-instance mutex. A cancelled prompt returns
    False and the normal process carries on.
    """
    if not should_elevate(config_wants_admin(), is_elevated(), sys.argv):
        return False
    return relaunch_elevated()


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _create_as_shell(cmdline):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32
    shell = user32.GetShellWindow()
    if not shell:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(shell, ctypes.byref(pid))
    proc = kernel32.OpenProcess(0x0400, False, pid.value)  # PROCESS_QUERY_INFORMATION
    if not proc:
        return False
    try:
        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(proc, 0x0002 | 0x0008, ctypes.byref(token)):
            return False
        try:
            primary = wintypes.HANDLE()
            if not advapi32.DuplicateTokenEx(
                    token, 0x0002 | 0x0008 | 0x0001, None, 2, 1,
                    ctypes.byref(primary)):
                return False
            try:
                si = _StartupInfo()
                si.cb = ctypes.sizeof(si)
                pi = _ProcessInfo()
                buf = ctypes.create_unicode_buffer(cmdline)
                ok = advapi32.CreateProcessWithTokenW(
                    primary, 0, None, buf, 0, None, None,
                    ctypes.byref(si), ctypes.byref(pi))
                if not ok:
                    return False
                if pi.hProcess:
                    kernel32.CloseHandle(pi.hProcess)
                if pi.hThread:
                    kernel32.CloseHandle(pi.hThread)
                return True
            finally:
                kernel32.CloseHandle(primary)
        finally:
            kernel32.CloseHandle(token)
    finally:
        kernel32.CloseHandle(proc)
