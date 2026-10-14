"""Footage-safety hunt: offload.py, recycle.py, atomic_json.py, fsprobe.py,
teracopy.py, tailscale.py, clip_catalog.py.

Each bug gets a check that fails against the bug and passes once fixed.
Temp directories only - never touches real footage, never points at a real
drive letter beyond confirming one does *not* exist.

    python tests/test_hunt_footage.py
"""
import os
import shutil
import string
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import fsprobe
from obsauto import tailscale as ts
from obsauto.clip_catalog import ClipCatalog
from obsauto.offload import Offloader
import obsauto.paths as paths_mod

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def new_app_dir():
    work = tempfile.mkdtemp(prefix="nebula-hunt-")
    app_dir = os.path.join(work, "appdir")
    os.makedirs(app_dir, exist_ok=True)
    return work, app_dir


def unused_drive_letter():
    """A drive letter guaranteed not to exist on this machine - so a path
    built from it can never resolve to anything real."""
    for d in string.ascii_uppercase:
        if not os.path.isdir(d + ":" + os.sep):
            return d
    return None


# ---------------------------------------------------------------------------
# Bug 1: ts.diagnose() calls os.path.isdir() directly, with no bound. A dead
# mapped drive / SMB UNC can hold that call for 20-60s (Windows waiting on
# the redirector) - and Offloader.status_snapshot(), which calls diagnose()
# whenever the reachability cache is empty, is polled straight from the
# WebView JS-bridge snapshot (spike/app.py Api.snapshot -> host.offload_
# status -> Offloader.status_snapshot). That is exactly the freeze the
# codebase already fixed once for Offloader.reachability(probe=False) - the
# same bound was never applied to status_snapshot()'s own diagnose() call.
# ---------------------------------------------------------------------------
def _slow_isdir_for(dead_path):
    """Only the simulated dead NAS path hangs; every other isdir() call
    (e.g. shutil.which()'s internal check of a real tailscale.exe on this
    machine) goes to the real implementation so the test isolates the bug
    instead of also tripping over unrelated stdlib isdir() calls."""
    real_isdir = os.path.isdir
    dead_norm = os.path.normcase(os.path.normpath(dead_path))

    def slow_isdir(p):
        try:
            norm = os.path.normcase(os.path.normpath(p))
        except (TypeError, ValueError):
            norm = None
        if norm == dead_norm:
            time.sleep(3.0)
            return False
        return real_isdir(p)

    return real_isdir, slow_isdir


def test_diagnose_bounded():
    dead_root = r"Z:\dead_mapped_drive_sim"
    real_isdir, slow_isdir = _slow_isdir_for(dead_root)

    os.path.isdir = slow_isdir
    try:
        t0 = time.monotonic()
        ts._reset_cache()
        code = ts.diagnose(dead_root)
        dt = time.monotonic() - t0
        check("diagnose() returns within the fsprobe timeout, not after a "
              "full slow isdir()", dt < 2.5,
              "took %.2fs (code=%s)" % (dt, code))
    finally:
        os.path.isdir = real_isdir
        ts._reset_cache()


def test_status_snapshot_bounded():
    work, app_dir = new_app_dir()
    try:
        paths_mod.APP_DIR = app_dir
        dead_root = r"Z:\dead_mapped_drive_sim"
        config = {"nas_offload_root": dead_root,
                  "nas_offload_mode": "move"}
        off = Offloader(config)

        real_isdir, slow_isdir = _slow_isdir_for(dead_root)

        os.path.isdir = slow_isdir
        try:
            ts._reset_cache()
            t0 = time.monotonic()
            snap = off.status_snapshot()
            dt = time.monotonic() - t0
            check("Offloader.status_snapshot() (polled from the JS-bridge "
                  "snapshot) is bounded even on a dead NAS path", dt < 2.5,
                  "took %.2fs (reachability=%s)" % (dt, snap.get("reachability")))
        finally:
            os.path.isdir = real_isdir
            ts._reset_cache()
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# Bug 2: ClipCatalog._safe_rel() only rejects ".." path segments. It lets a
# segment through that *looks like a drive letter* ("Q:"). cache_path() then
# builds the cache location via os.path.join(cache_root, *rel.split("/")) -
# and on Windows, os.path.join discards every earlier component once it
# meets a component shaped like "X:" for a drive other than cache_root's
# own, per ntpath's join rules. So a crafted ``rel`` resolves to a path that
# is not under the cache directory at all - which evict()/_prune_cache()
# then happily operate on (remove, in evict()'s case). local_path() in the
# same file already guards its join with an explicit containment check;
# cache_path() never got the same guard. Proven with a drive letter that is
# confirmed absent on this machine, so nothing real is ever touched.
# ---------------------------------------------------------------------------
def test_cache_path_rejects_drive_escape():
    work, app_dir = new_app_dir()
    try:
        drive = unused_drive_letter()
        if drive is None:
            check("cache_path() stays under the cache directory for a "
                  "drive-letter-shaped rel (skipped: no free drive letter "
                  "to prove it safely)", True, "skipped")
            return
        cat = ClipCatalog({}, app_dir=app_dir)
        rel = "%s:/evil/clip.mkv" % drive
        safe = cat.cache_path(rel)
        cache_root_norm = os.path.normcase(os.path.normpath(cat._cache_root))
        # None (refuse) is the safe outcome; only a path that computed to
        # somewhere outside cache_root counts as the escape.
        escaped = (safe is not None) and not os.path.normcase(
            os.path.normpath(safe)).startswith(cache_root_norm)
        check("cache_path() keeps a drive-letter-shaped rel confined to "
              "the cache directory", not escaped,
              "cache_root=%r cache_path(%r)=%r" % (cat._cache_root, rel, safe))
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# Bug 3: fsprobe.filesize_within()'s own docstring says "Same shape as
# isdir_within and for the same reason" - but unlike isdir_within, it never
# memoises a negative verdict. Every call against a dead path pays the full
# probe timeout again, forever, instead of the ~10s memo isdir_within gives.
# Proven by timing two back-to-back calls against a path whose probe is
# made artificially slow: the second call should be near-instant (served
# from the memo) once fixed, but currently costs a full timeout again.
# ---------------------------------------------------------------------------
def test_filesize_within_memoises_negative():
    work = tempfile.mkdtemp(prefix="nebula-hunt-fsprobe-")
    try:
        dead_path = os.path.join(work, "dead_mapped_drive_sim", "clip.mkv")
        real_isfile = os.path.isfile

        def slow_isfile(p):
            time.sleep(0.4)
            return False

        os.path.isfile = slow_isfile
        try:
            t0 = time.monotonic()
            first = fsprobe.filesize_within(dead_path, timeout=0.3)
            dt_first = time.monotonic() - t0

            t0 = time.monotonic()
            second = fsprobe.filesize_within(dead_path, timeout=0.3)
            dt_second = time.monotonic() - t0

            check("filesize_within() memoises a negative verdict so a "
                  "second probe of the same dead path doesn't pay the "
                  "full timeout again", dt_second < dt_first / 2,
                  "first=%.3fs second=%.3fs (first=%r second=%r)" % (
                      dt_first, dt_second, first, second))

            # A directory miss must not make the next size check lie, or
            # the other way round. The two memos are different questions.
            fsprobe.forget(dead_path)
            fsprobe._neg_until[fsprobe._key(dead_path)] = time.monotonic() + 30
            t0 = time.monotonic()
            poisoned = fsprobe.filesize_within(dead_path, timeout=0.3)
            dt_poison = time.monotonic() - t0
            check("an isdir miss does not skip the filesize probe",
                  dt_poison >= 0.2 and poisoned is None,
                  "took %.3fs -> %r" % (dt_poison, poisoned))
        finally:
            os.path.isfile = real_isfile
    finally:
        fsprobe.forget(dead_path)
        shutil.rmtree(work, ignore_errors=True)


def run():
    test_diagnose_bounded()
    test_status_snapshot_bounded()
    test_cache_path_rejects_drive_escape()
    test_filesize_within_memoises_negative()


run()
passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<70} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
