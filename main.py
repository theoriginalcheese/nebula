"""Nebula entry point.

The shipping UI is **v4 WebView** (``spike/app.py``). The Tk shell in
``obsauto/gui.py`` is obsolete — kept in-tree so older GUI tests can still
import it, but ``python main.py`` no longer opens it.

    python main.py                 # same as: python spike/app.py
    python spike/app.py --show     # visible window (dev)
    pyinstaller nebula-v4.spec     # -> dist/Nebula-v4.exe

``nebula.spec`` (Tk onefile) is retired; use ``nebula-v4.spec``.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys


def _is_elevated():
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_elevated():
    """Start an admin copy and let this process leave.

    HoYoPlay and the games it launches run elevated. The dial hook is a
    low-level keyboard hook, and Windows does not call that hook for keys
    aimed at an admin window unless Nebula is admin too. Cancelling the
    prompt keeps the normal process, which is the right result for a test
    run or a declined UAC.
    """
    if _is_elevated():
        return False
    if any(flag in sys.argv for flag in ("--dev", "--allow-multi", "--toast-demo")):
        return False
    if getattr(sys, "frozen", False):
        target = sys.executable
        params = subprocess.list2cmdline(sys.argv[1:])
    else:
        target = sys.executable
        script = os.path.abspath(sys.argv[0])
        params = subprocess.list2cmdline([script, *sys.argv[1:]])
    try:
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", target, params or None, os.getcwd(), 1)
    except Exception:
        return False
    return rc > 32


def main(argv=None):
    # Preserve argv for spike flags (--show, --dev, --toast-demo, --url=…).
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    if _relaunch_elevated():
        return 0
    from spike.app import main as spike_main
    return spike_main() or 0


if __name__ == "__main__":
    raise SystemExit(main())
