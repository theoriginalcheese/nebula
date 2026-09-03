"""Send a file to the Recycle Bin, or say honestly that it can't.

Culling is the one place Nebula removes a recording, and the settings text
has always promised "moves files to the Recycle Bin - never a hard delete".
The short-clip cull did not keep that promise: it called ``os.remove``.

Two things make this its own module rather than three lines in monitor.py:

* **Network paths have no Recycle Bin.** Windows recycles on the volume that
  holds the file, and a mapped drive or a UNC share has nowhere to put it -
  ``SHFileOperation`` silently falls back to a permanent delete. Given how
  much of the NAS library is single-copy, "recycle" quietly meaning "destroy"
  is exactly the failure that must not happen, so ``recyclable()`` is a
  separate question every caller has to ask first.
* The sweep tool needs the same guarantee the live cull does.

No new dependency: this is pywin32, which is already required.
"""

import os

try:  # pragma: no cover - present on every machine that runs Nebula
    import win32file
    from win32com.shell import shell, shellcon
except ImportError:  # pragma: no cover - non-Windows dev box
    win32file = None
    shell = None
    shellcon = None


class RecycleError(Exception):
    """The file could not be sent to the Recycle Bin. It is still on disk."""


def recyclable(path):
    """True when this path lives on a volume that has a Recycle Bin.

    Fixed and removable drives do; network drives, UNC shares and unknown
    volumes do not, and are reported as such rather than being deleted a
    different way. Answering "no" on an unreadable drive type is deliberate:
    the caller then leaves the file alone.
    """
    if win32file is None:
        return False
    path = os.path.abspath(path)
    if path.startswith("\\\\"):        # UNC - never has a bin
        return False
    drive = os.path.splitdrive(path)[0]
    if not drive:
        return False
    try:
        kind = win32file.GetDriveType(drive + "\\")
    except Exception:
        return False
    return kind in (win32file.DRIVE_FIXED, win32file.DRIVE_REMOVABLE)


def to_recycle_bin(path):
    """Move one existing file to the Recycle Bin.

    Raises RecycleError if the volume has no bin, or if the shell refuses -
    never falls back to unlinking. A caller that wants a hard delete has to
    say so itself, in its own code, where it can be read.
    """
    path = os.path.abspath(path)
    if shell is None:
        raise RecycleError("pywin32 is not available")
    if not os.path.exists(path):
        raise RecycleError("no such file: %s" % path)
    if not recyclable(path):
        raise RecycleError(
            "%s is not on a volume with a Recycle Bin - refusing to delete"
            % path)
    flags = (shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION
             | shellcon.FOF_SILENT | shellcon.FOF_NOERRORUI)
    try:
        result, aborted = shell.SHFileOperation(
            (0, shellcon.FO_DELETE, path, None, flags, None, None))
    except Exception as exc:
        raise RecycleError("shell refused %s: %s" % (path, exc)) from exc
    if aborted or result:
        raise RecycleError("shell returned %s for %s" % (result, path))
    return True
