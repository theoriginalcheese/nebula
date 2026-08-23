"""Nebula version — one release number, an honest display label.

``__version__`` is what you bump when you cut a GitHub Release / tag ``vX.Y.Z``.
The titlebar badge and Updates pane read :func:`display_version` so a source
checkout that is *ahead* of the tag shows ``4.0.0+8`` (commits since tag)
instead of lying that it is a clean release build. Uncommitted work adds a
trailing ``*`` so two machines can tell they are not on the same snapshot.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time

from .silent_proc import resolve_git, run_kwargs

# ---------------------------------------------------------------------------
# Bump this when you ship. Tag the same number as vX.Y.Z on GitHub.
# ---------------------------------------------------------------------------
__version__ = "4.0.1"

_GIT_CACHE = {"at": 0.0, "describe": "", "branch": "", "subject": ""}
_GIT_TTL_S = 60.0
_GIT_LOCK = threading.Lock()


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def _repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    if os.path.isdir(os.path.join(root, ".git")):
        return root
    return None


def _git_out(args, root, timeout=5):
    try:
        proc = subprocess.run(
            [resolve_git(), *args],
            cwd=root, capture_output=True, text=True, timeout=timeout,
            **run_kwargs(),
        )
        return (proc.stdout or "").strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


def _git_snapshot(root=None, force=False):
    empty = {"describe": "", "branch": "", "subject": ""}
    if is_frozen():
        return dict(empty)
    with _GIT_LOCK:
        now = time.monotonic()
        if not force and (now - _GIT_CACHE["at"]) < _GIT_TTL_S:
            return {
                "describe": _GIT_CACHE["describe"],
                "branch": _GIT_CACHE["branch"],
                "subject": _GIT_CACHE["subject"],
            }
        root = root or _repo_root()
        if not root:
            _GIT_CACHE.update(at=now, **empty)
            return dict(empty)
        describe = _git_out(["describe", "--tags", "--always", "--dirty"], root)
        branch = _git_out(["rev-parse", "--abbrev-ref", "HEAD"], root)
        subject = _git_out(["log", "-1", "--format=%s"], root)
        _GIT_CACHE.update(
            at=now, describe=describe, branch=branch, subject=subject,
        )
        return {"describe": describe, "branch": branch, "subject": subject}


def git_describe(root=None, force=False):
    """Raw ``git describe --tags --always --dirty`` or ``\"\"`` if unavailable."""
    return _git_snapshot(root=root, force=force)["describe"]


def git_branch(root=None, force=False):
    return _git_snapshot(root=root, force=force)["branch"]


def _parse_describe(desc):
    if not desc:
        return None, 0, False
    dirty = desc.endswith("-dirty")
    core = desc[:-6] if dirty else desc
    m = re.match(
        r"^v?(?P<ver>\d+(?:\.\d+)*)(?:-(?P<n>\d+)-g[0-9a-f]+)?$",
        core, re.I)
    if not m:
        return None, 0, dirty
    n = int(m.group("n") or 0)
    return m.group("ver"), n, dirty


def version_info():
    release = __version__
    if is_frozen():
        return {
            "release": release,
            "display": release,
            "detail": "Nebula %s (packaged)" % release,
            "channel": "release",
            "git": "",
            "branch": "",
            "frozen": True,
            "dirty": False,
        }

    snap = _git_snapshot()
    desc = snap["describe"]
    branch = snap["branch"]
    subject = snap["subject"]
    tag_ver, ahead, dirty = _parse_describe(desc)

    display = release
    bits = []
    if branch:
        bits.append(branch)
    if tag_ver and tag_ver != release:
        bits.append("tag %s" % tag_ver)
    if ahead:
        display = "%s+%d" % (release, ahead)
        bits.append("%d commit%s ahead" % (ahead, "" if ahead == 1 else "s"))
    if dirty:
        display = "%s*" % display
        bits.append("uncommitted changes")
    if not desc:
        display = "%s·dev" % release
        bits.append("no git metadata")
    if subject and subject.startswith("nebula: save "):
        bits.append(subject)

    detail = "Nebula %s (source)" % display
    if bits:
        detail = "%s — %s" % (detail, ", ".join(bits))
    if desc:
        detail = "%s [%s]" % (detail, desc)

    return {
        "release": release,
        "display": display,
        "detail": detail,
        "channel": "source",
        "git": desc,
        "branch": branch,
        "frozen": False,
        "dirty": dirty,
    }


def display_version():
    return version_info()["display"]
