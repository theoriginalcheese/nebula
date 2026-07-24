"""Tests for the NAS offloader - the safety-critical path.

The one invariant that must never break: a local recording is NOT deleted until
a byte-verified copy exists on the destination. These tests use temp dirs as a
stand-in NAS, including simulating the NAS being offline and a corrupt copy.

    python tests/test_offload.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import offload as offload_module
from obsauto import paths as paths_module
from obsauto.offload import Offloader

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def make_clip(path, size=1_500_000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(os.urandom(size))


def wait_until(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def run():
    work = tempfile.mkdtemp(prefix="nebula-offload-test-")
    original_app_dir = paths_module.APP_DIR

    local = os.path.join(work, "local")
    nas = os.path.join(work, "nas")
    os.makedirs(local)
    os.makedirs(nas)

    logs = []
    _seq = [0]

    def new_offloader(cfg):
        # Each offloader gets its own APP_DIR so their persisted queues don't
        # bleed into each other. The offloader reads APP_DIR at construction
        # (`from .paths import APP_DIR`), so patch it right before.
        _seq[0] += 1
        app_dir = os.path.join(work, f"appdir{_seq[0]}")
        os.makedirs(app_dir, exist_ok=True)
        paths_module.APP_DIR = app_dir
        return Offloader(cfg, on_log=logs.append), app_dir

    # ---- move mode: copy, verify, delete local ----
    off, _ = new_offloader({"nas_offload_root": nas, "nas_offload_mode": "move"})
    off.start()

    clip = os.path.join(local, "Zenless Zone Zero", "clip1.mkv")
    make_clip(clip)
    src_bytes = open(clip, "rb").read()
    off.queue(clip, "Zenless Zone Zero")

    dest = os.path.join(nas, "Zenless Zone Zero", "clip1.mkv")
    ok = wait_until(lambda: os.path.exists(dest) and not os.path.exists(clip))
    check("move: file arrived on NAS", os.path.exists(dest), dest)
    check("move: local deleted only after copy", not os.path.exists(clip))
    check("move: bytes identical", os.path.exists(dest) and open(dest, "rb").read() == src_bytes)
    check("move: no .part left behind", not os.path.exists(dest + ".part"))
    check("move: queue drained", off.pending_count() == 0, off.pending_count())
    off.stop()

    # ---- copy mode: keep both ----
    off2, _ = new_offloader({"nas_offload_root": nas, "nas_offload_mode": "copy"})
    off2.start()
    clip2 = os.path.join(local, "Halo", "clip2.mkv")
    make_clip(clip2)
    off2.queue(clip2, "Halo")
    dest2 = os.path.join(nas, "Halo", "clip2.mkv")
    wait_until(lambda: os.path.exists(dest2))
    check("copy: file on NAS", os.path.exists(dest2))
    check("copy: local ALSO kept", os.path.exists(clip2))
    off2.stop()

    # ---- NAS offline: local must be untouched, item retained + persisted ----
    missing_nas = os.path.join(work, "nas-that-isnt-mounted")
    off3, app_dir3 = new_offloader({"nas_offload_root": missing_nas, "nas_offload_mode": "move"})
    off3.start()
    clip3 = os.path.join(local, "Doom", "clip3.mkv")
    make_clip(clip3)
    off3.queue(clip3, "Doom")
    time.sleep(1.2)
    check("offline NAS: local untouched", os.path.exists(clip3))
    check("offline NAS: item still queued", off3.pending_count() == 1, off3.pending_count())
    check("offline NAS: queue persisted",
          os.path.exists(os.path.join(app_dir3, "offload_queue.json")))
    off3.stop()

    # ---- restart persistence: a new offloader on the same APP_DIR, now with a
    # reachable NAS, finishes the job left over from the offline run ----
    paths_module.APP_DIR = app_dir3
    off3b = Offloader({"nas_offload_root": nas, "nas_offload_mode": "move"},
                      on_log=logs.append)
    off3b.start()
    dest3 = os.path.join(nas, "Doom", "clip3.mkv")
    wait_until(lambda: os.path.exists(dest3) and not os.path.exists(clip3))
    check("restart: queued clip finished after NAS returned", os.path.exists(dest3))
    check("restart: local removed after verified copy", not os.path.exists(clip3))
    off3b.stop()

    # ---- corrupt destination copy: mismatch must NOT delete local ----
    off4, _ = new_offloader({"nas_offload_root": nas, "nas_offload_mode": "move"})
    real_hash = off4._hash
    clip4 = os.path.join(local, "Portal", "clip4.mkv")
    make_clip(clip4)
    dest4 = os.path.join(nas, "Portal", "clip4.mkv")

    def poisoned_hash(path):
        # Real hash for the source, deliberately wrong for the copied .part -
        # i.e. the bytes that landed on the NAS don't match what we sent.
        if path.endswith(".part"):
            return "0" * 64
        return real_hash(path)

    off4._hash = poisoned_hash
    off4.start()
    off4.queue(clip4, "Portal")
    time.sleep(1.5)
    check("corrupt copy: local NOT deleted", os.path.exists(clip4))
    check("corrupt copy: bad dest not published", not os.path.exists(dest4))
    check("corrupt copy: item still queued", off4.pending_count() == 1, off4.pending_count())
    off4.stop()

    paths_module.APP_DIR = original_app_dir


run()
passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<42} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
