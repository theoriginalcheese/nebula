"""Send a file to the Recycle Bin, or say honestly that it can't.

Culling is the one place Nebula removes a recording, and the settings text
has always promised "moves files to the Recycle Bin - never a hard delete".
The short-clip cull did not keep that promise: it called ``os.remove``.

Two things make this its own module rather than three lines in monitor.py:

* **Network paths have no Recycle Bin.** Windows recycles on the volume that
  holds the file, and a mapped drive or a UNC share has nowhere to put it -
  ``SHFileOperation`` silently falls back to a permanent delete. Removable
  volumes (USB sticks, SD cards) do the same. Given how much of the NAS
  library is single-copy, "recycle" quietly meaning "destroy" is exactly the
  failure that must not happen, so ``recyclable()`` is a separate question
  every caller has to ask first. A file bigger than the bin's cap, or a
  volume set to never recycle, is refused the same way — no shell dialog,
  because the cull runs on the monitor thread.
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

    Fixed drives do. Removable drives, network drives, UNC shares and
    unknown volumes do not: Windows deletes those outright and still reports
    success. Answering "no" on an unreadable drive type is deliberate:
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
    return kind == win32file.DRIVE_FIXED


def _bin_would_destroy(path):
    """True when the shell would permanently delete instead of recycling.

    ``NukeOnDelete`` and a file larger than ``MaxCapacity`` both do that,
    and ``FOF_NOCONFIRMATION`` means there is no warning. Unknown settings
    return False so a missing registry key does not block a normal cull.
    """
    if win32file is None:
        return False
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    drive = os.path.splitdrive(os.path.abspath(path))[0]
    if not drive:
        return False
    try:
        vol = win32file.GetVolumeNameForVolumeMountPoint(drive + "\\")
    except Exception:
        return False
    start = vol.find("{")
    end = vol.find("}")
    if start < 0 or end < start:
        return False
    guid = vol[start:end + 1]
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer"
            "\\BitBucket\\Volume\\%s" % guid)
        try:
            nuke, _typ = winreg.QueryValueEx(key, "NukeOnDelete")
        except OSError:
            nuke = 0
        try:
            max_mb, _typ = winreg.QueryValueEx(key, "MaxCapacity")
        except OSError:
            max_mb = 0
    except OSError:
        return False
    if int(nuke or 0):
        return True
    cap = int(max_mb or 0)
    if cap > 0 and size > cap * 1024 * 1024:
        return True
    return False


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
    if _bin_would_destroy(path):
        raise RecycleError(
            "%s would be permanently deleted (Recycle Bin cap or "
            "NukeOnDelete) - refusing" % path)
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
