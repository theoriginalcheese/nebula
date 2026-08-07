"""Nebula version — one release number, an honest display label.



``__version__`` is what you bump when you cut a GitHub Release / tag ``vX.Y.Z``.

The titlebar badge and Updates pane read :func:`display_version` so a source

checkout that is *ahead* of the tag shows ``4.0.0+8`` (commits since tag)

instead of lying that it is a clean release build.

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

__version__ = "4.0.0"



# git describe is shelled out — cache it so a 5s snapshot poll does not flash

# a console window under pythonw on every beat.

_DESCRIBE_CACHE = {"at": 0.0, "value": ""}

_DESCRIBE_TTL_S = 60.0

_DESCRIBE_LOCK = threading.Lock()





def is_frozen():

    return bool(getattr(sys, "frozen", False))





def _repo_root():

    here = os.path.dirname(os.path.abspath(__file__))

    root = os.path.dirname(here)

    if os.path.isdir(os.path.join(root, ".git")):

        return root

    return None





def git_describe(root=None, force=False):

    """Raw ``git describe --tags --always --dirty`` or ``\"\"`` if unavailable."""

    if is_frozen():

        return ""

    with _DESCRIBE_LOCK:

        now = time.monotonic()

        if not force and (now - _DESCRIBE_CACHE["at"]) < _DESCRIBE_TTL_S:

            return _DESCRIBE_CACHE["value"]

        root = root or _repo_root()

        if not root:

            _DESCRIBE_CACHE.update(at=now, value="")

            return ""

        try:

            proc = subprocess.run(

                [resolve_git(), "describe", "--tags", "--always", "--dirty"],

                cwd=root, capture_output=True, text=True, timeout=5,

                **run_kwargs(),

            )

            value = (proc.stdout or "").strip() if proc.returncode == 0 else ""

        except Exception:

            value = ""

        _DESCRIBE_CACHE.update(at=now, value=value)

        return value





def _parse_describe(desc):

    """Return (tag_version, commits_ahead, dirty) from a describe string."""

    if not desc:

        return None, 0, False

    dirty = desc.endswith("-dirty")

    core = desc[:-6] if dirty else desc

    # v4.0.0-8-g2af435c  OR  v4.0.0  OR  2af435c

    m = re.match(

        r"^v?(?P<ver>\d+(?:\.\d+)*)(?:-(?P<n>\d+)-g[0-9a-f]+)?$",

        core, re.I)

    if not m:

        return None, 0, dirty

    n = int(m.group("n") or 0)

    return m.group("ver"), n, dirty





def version_info():

    """Structured version for the UI and Updates pane."""

    release = __version__

    if is_frozen():

        return {

            "release": release,

            "display": release,

            "detail": "Nebula %s (packaged)" % release,

            "channel": "release",

            "git": "",

            "frozen": True,

        }



    desc = git_describe()

    tag_ver, ahead, dirty = _parse_describe(desc)

    display = release

    bits = []

    if tag_ver and tag_ver != release:

        # Working tree tagged differently than __version__ — prefer the file

        # (source of truth) but surface the mismatch in detail.

        bits.append("tag %s" % tag_ver)

    if ahead:

        display = "%s+%d" % (release, ahead)

        bits.append("%d commit%s ahead" % (ahead, "" if ahead == 1 else "s"))

    if dirty:

        bits.append("uncommitted changes")

    if not desc:

        display = "%s·dev" % release

        bits.append("no git metadata")



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

        "frozen": False,

    }





def display_version():

    """Short badge text for the titlebar."""

    return version_info()["display"]


