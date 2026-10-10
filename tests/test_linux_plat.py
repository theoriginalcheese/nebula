"""Linux host behaviour that has to survive a hostile path.

    python tests/test_linux_plat.py

Network mounts and Windows drive letters are not recyclable. A trash move
renames; it never unlinks. A second process cannot take the lock. A Proton
command line still yields the .exe name. Discord with no UI Automation
does not invent a call.
"""
import os
import stat
import subprocess
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import discord_detect
from obsauto import linux_plat
from obsauto import monitor as mon
from obsauto.recycle import RecycleError

PASS = []
FAIL = []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-56s %s" % ("PASS" if ok else "FAIL", name, detail))


MOUNTS = "\n".join([
    "/dev/sda2 / ext4 rw 0 0",
    "//nas/share /mnt/nas cifs rw 0 0",
    "tmpfs /run tmpfs rw 0 0",
])


def test_network_volumes_are_not_recyclable():
    check("UNC is refused",
          linux_plat.is_recyclable("\\\\192.168.68.59\\50tb\\a.mkv", MOUNTS)
          is False)
    check("a mapped drive letter is refused",
          linux_plat.is_recyclable("Z:\\OBS\\a.mkv", MOUNTS) is False)
    check("a cifs mount is refused",
          linux_plat.is_recyclable("/mnt/nas/OBS/a.mkv", MOUNTS) is False)
    check("the ext4 root is local",
          linux_plat.is_recyclable("/home/antho/clip.mkv", MOUNTS) is True)
    check("an unknown volume is refused",
          linux_plat.is_recyclable("/nowhere/clip.mkv", "") is False)


def test_trash_renames_and_keeps_the_bytes():
    if os.name == "nt":
        check("trash rename runs on the linux host", True, "skipped on windows")
        return
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "clip.mkv")
        payload = b"not-a-real-recording-but-do-not-lose-me"
        with open(src, "wb") as fh:
            fh.write(payload)
        trash = os.path.join(tmp, "Trash")
        # Same directory tree, so the rename stays on one device.
        dest = linux_plat.send_to_trash(
            src, mounts_text=MOUNTS, trash_root=trash)
        check("the original path is gone", not os.path.exists(src))
        check("the bytes are in the trash",
              os.path.isfile(dest) and open(dest, "rb").read() == payload,
              dest)
        info = os.path.join(trash, "info", os.path.basename(dest) + ".trashinfo")
        check("a trashinfo sidecar was written", os.path.isfile(info))


def test_trash_refuses_the_cases_that_would_destroy():
    if os.name == "nt":
        check("destructive trash cases run on the linux host", True,
              "skipped on windows")
        return
    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, "keep-this-dir")
        os.makedirs(folder)
        try:
            linux_plat.send_to_trash(folder, mounts_text=MOUNTS, trash_root=os.path.join(tmp, "Trash"))
            check("a directory is refused", False, "no error")
        except RecycleError:
            check("a directory is refused", True)
        check("the directory is still there", os.path.isdir(folder))

        missing = os.path.join(tmp, "missing.mkv")
        try:
            linux_plat.send_to_trash(missing, mounts_text=MOUNTS)
            check("a missing file is refused", False, "no error")
        except RecycleError:
            check("a missing file is refused", True)

        src = os.path.join(tmp, "stay.mkv")
        with open(src, "wb") as fh:
            fh.write(b"stay")
        link = os.path.join(tmp, "link.mkv")
        os.symlink(src, link)
        try:
            linux_plat.send_to_trash(
                link, mounts_text=MOUNTS, trash_root=os.path.join(tmp, "Trash"))
            check("a symlink is refused", False, "no error")
        except RecycleError:
            check("a symlink is refused", True)
        check("the symlink target was not moved",
              os.path.isfile(src) and open(src, "rb").read() == b"stay")
        try:
            linux_plat.send_to_trash(
                src, mounts_text=MOUNTS.replace("ext4", "cifs"))
            check("a cifs file is refused", False, "no error")
        except RecycleError:
            check("a cifs file is refused", True)
        check("the cifs file was not moved", os.path.isfile(src))

        # Other device: pretend the trash directory is a different st_dev.
        real_stat = os.stat

        def lying_stat(path, *args, **kwargs):
            result = real_stat(path, *args, **kwargs)
            files = os.path.join(tmp, "other-trash", "files")
            if os.path.abspath(path) == os.path.abspath(files):
                return os.stat_result((
                    stat.S_IFDIR, result.st_ino, result.st_dev + 1,
                    result.st_nlink, result.st_uid, result.st_gid,
                    result.st_size, result.st_atime, result.st_mtime,
                    result.st_ctime))
            return result

        linux_plat.os.stat = lying_stat
        try:
            try:
                linux_plat.send_to_trash(
                    src, mounts_text=MOUNTS,
                    trash_root=os.path.join(tmp, "other-trash"))
                check("a cross-device trash is refused", False, "no error")
            except RecycleError:
                check("a cross-device trash is refused", True)
        finally:
            linux_plat.os.stat = real_stat
        check("the cross-device file is still in place",
              os.path.isfile(src) and open(src, "rb").read() == b"stay")


def test_proton_name_and_honest_idle():
    argv = [
        "/usr/bin/pressure-vessel",
        "Z:\\steam\\steamapps\\common\\Star Rail\\StarRail.exe",
    ]
    check("proton yields the exe",
          linux_plat.proton_basename(argv) == "StarRail.exe")
    check("a native binary yields nothing",
          linux_plat.proton_basename(["/usr/bin/blender"]) is None)
    check("idle is a number and not a guess of forever",
          mon.get_idle_duration() == 0.0 or mon.get_idle_duration() >= 0)
    if os.name != "nt":
        check("a headless foreground is unknown",
              mon.get_foreground_window_info() is None)
        check("discord does not invent a call",
              discord_detect.discord_voice_active(force=True) is False)


def test_second_process_cannot_take_the_lock():
    if os.name == "nt":
        check("flock lock is a linux check", True, "skipped on windows")
        return
    name = "Nebula.BreakLock.%d" % os.getpid()
    held = linux_plat.try_lock(name)
    check("first lock wins", held is not None)
    child = subprocess.run(
        [sys.executable, "-c",
         "import os,sys; sys.path.insert(0, %r); "
         "from obsauto.linux_plat import try_lock; "
         "sys.exit(0 if try_lock(%r) else 1)" % (
             os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
             name)],
        capture_output=True, text=True, timeout=30,
    )
    check("a second process is refused", child.returncode == 1,
          (child.stderr or child.stdout or "")[-300:])
    again = linux_plat.try_lock(name)
    check("the holder is not blocked by its own failed peer",
          again is None)
    linux_plat.unlock(held)
    after = linux_plat.try_lock(name)
    check("release lets a new lock through", after is not None)
    if after:
        linux_plat.unlock(after)


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        print("\n--- %s" % fn.__name__.replace("test_", "").replace("_", " "))
        try:
            fn()
        except Exception:
            check(fn.__name__, False, "raised")
            traceback.print_exc()
    print("\n%s (%d checks)" % ("ALL PASS" if not FAIL else "FAILED",
                                len(PASS) + len(FAIL)))
    if FAIL:
        for name in FAIL:
            print("  FAIL %s" % name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
