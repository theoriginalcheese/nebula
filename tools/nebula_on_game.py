"""Start Nebula when a known game process appears. Meant to run all the time.

Nebula itself is the heavy part (WebView, OBS, the monitor). This process
only keeps a set of exe names from games.json and a process snapshot every
couple of seconds. When one of those names is running and Nebula is not,
it starts one hidden copy. A second launch is a no-op: Nebula holds
Nebula.SingleInstance, and a live copy is left alone so a game does not
lose focus.

    pythonw tools/nebula_on_game.py

Install the logon task with tools/install_nebula_on_game_task.ps1 so it
comes back after a reboot. It has to be a user logon task: a game, and
Nebula's window, only exist in a desktop session.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes

POLL_S = 2.0
LAUNCH_COOLDOWN_S = 20.0
MUTEX_NAME = "Nebula.SingleInstance"
# Checked before every other exe. CS2 must wake Nebula even if games.json
# has not been saved yet, and it wins the log line when several games are open.
PRIORITY_EXES = ("cs2.exe",)
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
SYNCHRONIZE = 0x00100000
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE = wintypes.HANDLE(-1).value

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_kernel32.Process32NextW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.OpenMutexW.restype = wintypes.HANDLE


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def games_json_path(repo, home=None):
    """Same resolution as spike's sync folder: relative paths hang off ~."""
    home = home or os.path.expanduser("~")
    cfg_path = os.path.join(repo, "config.json")
    sync = ""
    try:
        with open(cfg_path, "r", encoding="utf-8") as handle:
            sync = (json.load(handle).get("sync_folder") or "").strip()
    except (OSError, json.JSONDecodeError, AttributeError):
        sync = ""
    if sync:
        if not os.path.isabs(sync):
            sync = os.path.join(home, sync)
        return os.path.join(sync, "games.json")
    return os.path.join(repo, "games.json")


def game_exes(data):
    """Basenames Nebula already calls games. non_games never wake it.

    Priority exes are always included, so Counter-Strike still starts Nebula
    if the list on disk is missing or stale.
    """
    games = data.get("games") if isinstance(data, dict) else None
    names = set(PRIORITY_EXES)
    if isinstance(games, dict):
        names.update(str(name).lower() for name in games if str(name).strip())
    return names


def load_game_exes(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return game_exes(json.load(handle))
    except (OSError, json.JSONDecodeError):
        return set(PRIORITY_EXES)


def running_exes():
    """Exe basenames, lowercased. Empty if the snapshot cannot be taken."""
    snap = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE:
        return set()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        names = set()
        ok = _kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            name = entry.szExeFile
            if name:
                names.add(name.lower())
            ok = _kernel32.Process32NextW(snap, ctypes.byref(entry))
        return names
    finally:
        _kernel32.CloseHandle(snap)


def nebula_running(name=MUTEX_NAME):
    """True while a live Nebula holds its single-instance mutex.

    Open, don't create. Creating it here would make this process the owner
    and the real app would think it was already running.
    """
    handle = _kernel32.OpenMutexW(SYNCHRONIZE, False, name)
    if not handle:
        return False
    _kernel32.CloseHandle(handle)
    return True


def should_launch(game_hit, nebula_up, now, next_launch_at):
    """One hidden start per game arrival, not a start on every poll."""
    if not game_hit or nebula_up:
        return False
    return now >= next_launch_at


def matching_game(running, games):
    """Priority exes first. A set walk would otherwise report whichever
    other game happened to come out of the process snapshot."""
    for name in PRIORITY_EXES:
        if name in running:
            return name
    if not games:
        return ""
    for name in running:
        if name in games:
            return name
    return ""


def pythonw_for(executable):
    """Prefer pythonw so the launch does not flash a console over the game."""
    folder = os.path.dirname(executable)
    candidate = os.path.join(folder, "pythonw.exe")
    if os.path.isfile(candidate):
        return candidate
    return executable


def launch_nebula(repo, pythonw):
    """Hidden tray start. No --show: that would pull the game out of focus."""
    main_py = os.path.join(repo, "main.py")
    flags = CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB
    try:
        subprocess.Popen(
            [pythonw, main_py],
            cwd=repo,
            close_fds=True,
            creationflags=flags,
        )
    except OSError:
        subprocess.Popen(
            [pythonw, main_py],
            cwd=repo,
            close_fds=True,
            creationflags=CREATE_NO_WINDOW,
        )


def _log(repo, message):
    path = os.path.join(repo, "logs", "nebula-on-game.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.isfile(path) and os.path.getsize(path) > 200_000:
            os.replace(path, path + ".1")
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("%s %s\n" % (stamp, message))
    except OSError:
        pass


def main():
    repo = repo_root()
    pythonw = pythonw_for(sys.executable)
    games_path = games_json_path(repo)
    games = load_game_exes(games_path)
    try:
        games_mtime = os.path.getmtime(games_path)
    except OSError:
        games_mtime = 0
    next_launch_at = 0.0
    _log(repo, "watching %d game exe(s) from %s" % (len(games), games_path))
    while True:
        path = games_json_path(repo)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0
        if mtime != games_mtime or path != games_path:
            games = load_game_exes(path)
            games_mtime = mtime
            games_path = path
        hit = matching_game(running_exes(), games)
        now = time.monotonic()
        if should_launch(hit, nebula_running(), now, next_launch_at):
            try:
                launch_nebula(repo, pythonw)
            except OSError as exc:
                _log(repo, "launch failed for %s: %s" % (hit, exc))
            else:
                _log(repo, "launched Nebula for %s" % hit)
            # Mutex is claimed a moment after process start. Without this
            # gap the next poll would start a second copy.
            next_launch_at = now + LAUNCH_COOLDOWN_S
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
