"""Windows helpers so CLI probes never flash a console under pythonw.

Git for Windows' ``cmd\\git.exe`` re-execs into ``mingw64\\bin\\git.exe`` and
that second process often gets its own conhost — visible as a brief black
flash even when the parent was started with ``CREATE_NO_WINDOW``. Prefer the
real binary, and always hide the window.
"""
from __future__ import annotations

import os
import shutil
import subprocess


def run_kwargs():
    """Kwargs for ``subprocess.run`` / ``Popen`` that suppress a console."""
    if os.name != "nt":
        return {}
    kwargs = {}
    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    if flags:
        kwargs["creationflags"] = flags
    # Belt-and-braces: some wrappers ignore CREATE_NO_WINDOW on the re-exec.
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si
    except Exception:
        pass
    return kwargs


def resolve_git():
    """Absolute path to a git binary that won't flash a console on Windows."""
    which = shutil.which("git")
    if not which:
        return "git"
    norm = os.path.normcase(os.path.normpath(which))
    # …\Git\cmd\git.exe → prefer mingw64\bin or bin beside the install root.
    if norm.endswith(os.path.normcase(os.path.join("cmd", "git.exe"))):
        root = os.path.dirname(os.path.dirname(which))
        for parts in (("mingw64", "bin", "git.exe"), ("bin", "git.exe")):
            cand = os.path.join(root, *parts)
            if os.path.isfile(cand):
                return cand
    return which
