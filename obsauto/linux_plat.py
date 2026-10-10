"""Headless Linux stand-ins for the Win32 calls.

Windows keeps its own mutex, idle timer, and Recycle Bin. These functions
are what a machine without a desktop session can still do honestly: an
exclusive lock, a Freedesktop trash that never unlinks, and a volume check
that treats a network mount as having no bin.
"""

from __future__ import annotations

import os
import tempfile
import time

_LOCAL_FSTYPES = {
    "ext2", "ext3", "ext4", "btrfs", "xfs", "zfs", "tmpfs",
    "bcachefs", "f2fs", "overlay", "squashfs",
}


def parse_mounts(text):
    """``(mountpoint, fstype)`` rows from ``/proc/mounts`` text."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        mount = parts[1].replace("\\040", " ")
        rows.append((mount, parts[2]))
    return rows


def fstype_of(path, rows):
    """Filesystem type of the longest mount covering ``path``, or None."""
    # A POSIX absolute path must stay POSIX. abspath() on Windows would
    # turn /mnt/nas into C:\mnt\nas and the cifs row would never match.
    if not (path.startswith("/") or path.startswith("//")):
        path = os.path.abspath(path)
    best = None
    best_len = -1
    for mount, fstype in rows:
        if mount == "/":
            matched = True
            length = 1
        else:
            prefix = mount.rstrip("/")
            matched = path == prefix or path.startswith(prefix + "/")
            length = len(prefix)
        if matched and length > best_len:
            best = fstype
            best_len = length
    return best


def _windows_style(path):
    if path.startswith("\\\\") or path.startswith("//"):
        return True
    return len(path) >= 2 and path[1] == ":"


def _remote(fstype):
    if not fstype or fstype not in _LOCAL_FSTYPES:
        return True
    return False


def is_recyclable(path, mounts_text=None):
    """True only for a local disk. Unknown and network volumes are not.

    A missing mount table answers no. That is the same fail-closed rule as
    an unreadable Windows drive type: the caller leaves the file alone.
    """
    if not path or _windows_style(path):
        return False
    if mounts_text is None:
        try:
            with open("/proc/mounts", encoding="utf-8") as fh:
                mounts_text = fh.read()
        except OSError:
            return False
    return not _remote(fstype_of(path, parse_mounts(mounts_text)))


def _trash_dirs(trash_root=None):
    if trash_root:
        root = trash_root
    else:
        data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser(
            "~/.local/share")
        root = os.path.join(data, "Trash")
    files = os.path.join(root, "files")
    info = os.path.join(root, "info")
    os.makedirs(files, exist_ok=True)
    os.makedirs(info, exist_ok=True)
    return files, info


def send_to_trash(path, mounts_text=None, trash_root=None):
    """Rename one regular file into the Freedesktop trash.

    Raises RecycleError and leaves the file where it is when the volume
    has no bin, the path is a directory, or the trash lives on another
    device. There is no copy-then-unlink fallback.
    """
    from .recycle import RecycleError

    if not path or _windows_style(path):
        raise RecycleError(
            "%s is not on a volume with a Recycle Bin - refusing to delete"
            % path)
    if not os.path.lexists(path):
        raise RecycleError("no such file: %s" % path)
    if os.path.islink(path):
        raise RecycleError(
            "%s is a symlink - refusing to follow it" % path)
    if os.path.isdir(path) and not os.path.islink(path):
        raise RecycleError(
            "%s is a directory - refusing to delete" % path)
    real = os.path.realpath(path)
    if not is_recyclable(real, mounts_text):
        raise RecycleError(
            "%s is not on a volume with a Recycle Bin - refusing to delete"
            % path)
    files, info = _trash_dirs(trash_root)
    if os.stat(real).st_dev != os.stat(files).st_dev:
        raise RecycleError(
            "%s would have to be copied onto another disk to reach the "
            "trash - refusing to delete" % path)
    name = os.path.basename(real)
    dest = os.path.join(files, name)
    if os.path.exists(dest):
        root, ext = os.path.splitext(name)
        dest = os.path.join(
            files, "%s-%d%s" % (root, int(time.time()), ext))
    os.rename(real, dest)
    info_path = os.path.join(info, os.path.basename(dest) + ".trashinfo")
    try:
        with open(info_path, "w", encoding="utf-8") as fh:
            fh.write("[Trash Info]\nPath=%s\nDeletionDate=%s\n" % (
                real, time.strftime("%Y-%m-%dT%H:%M:%S")))
    except OSError:
        # The file is already in the trash directory. Leaving it there is
        # the bin, not a delete.
        pass
    return dest


def idle_seconds():
    """Seconds since input, or 0 when this machine has no session idle clock.

    0 matches the Windows call failing: the monitor must not pause a
    recording because it could not see a keyboard.
    """
    return 0.0


def foreground():
    """Focused window as ``(pid, exe, name, title, class)``, or None.

    A headless box has no focused window. Returning None is the fail-open
    the monitor already treats as "don't know", not as "no game".
    """
    return None


def proton_basename(argv):
    """The ``.exe`` a Proton command line is actually running, if it names one."""
    if not argv:
        return None
    for part in reversed(list(argv)):
        base = os.path.basename(str(part).replace("\\", "/"))
        if base.lower().endswith(".exe"):
            return base
    return None


def try_lock(name):
    """An exclusive flock, or None if another process holds ``name``."""
    import fcntl
    safe = "".join(ch if ch.isalnum() else "_" for ch in (name or "nebula"))
    safe = safe[:80] or "nebula"
    directory = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        directory = tempfile.gettempdir()
    path = os.path.join(directory, "nebula-%s.lock" % safe)
    fh = open(path, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def unlock(fh):
    import fcntl
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        fh.close()
    except OSError:
        pass


def arm_wake(name):
    """A wake file the running process can watch. Returns the path."""
    directory = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    safe = "".join(ch if ch.isalnum() else "_" for ch in (name or "wake"))
    path = os.path.join(directory, "nebula-%s.wake" % safe[:80])
    try:
        open(path, "a").close()
    except OSError:
        return None
    return path


def pulse_wake(name):
    """Tell the holder of ``name`` to show itself. False if nobody is there."""
    directory = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    safe = "".join(ch if ch.isalnum() else "_" for ch in (name or "wake"))
    lock_path = os.path.join(directory, "nebula-%s.lock" % safe[:80])
    if not os.path.exists(lock_path):
        return False
    wake = arm_wake(name)
    if not wake:
        return False
    try:
        with open(wake, "a", encoding="utf-8") as fh:
            fh.write("show\n")
    except OSError:
        return False
    return True
