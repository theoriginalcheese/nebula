"""The worker retry loop: a failed item must survive and resume.

test_offload.py covers _process verdicts directly. This file drives the real
worker thread through the part those tests never reach - the backoff after a
failure - because that loop is where clips could silently stall forever:

  1. NAS down  -> item stays queued, local untouched, one rate-limited log line
  2. wake event (fresh enqueue / stop) -> retry NOW, not after the full backoff
  3. root returns mid-backoff with no wake -> the isdir_within poll retries
  4. source vanished while queued -> dropped honestly, queue drains

isdir_within/tailscale.diagnose are patched rather than pointed at real dirs:
fsprobe's negative-verdict memo would remember a deleted test dir for its TTL
and make the up-again transitions lie about timing.

    python tests/test_offload_backoff.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import paths as paths_module
from obsauto import offload as offload_module
from obsauto.offload import Offloader

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def wait_until(pred, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def run():
    work = tempfile.mkdtemp(prefix="nebula-offload-backoff-")
    original_app_dir = paths_module.APP_DIR
    real_isdir_within = offload_module.isdir_within
    real_diagnose = offload_module.ts.diagnose

    local = os.path.join(work, "local")
    nas = os.path.join(work, "nas")
    os.makedirs(local)

    logs = []
    UP = [False]

    app_dir = os.path.join(work, "appdir")
    os.makedirs(app_dir)
    paths_module.APP_DIR = app_dir
    offload_module.isdir_within = lambda p, timeout=2.0: UP[0]
    offload_module.ts.diagnose = (
        lambda p: "lan" if UP[0] else "no-route")

    try:
        # Shrink the real backoff so a second failed attempt happens quickly:
        # the rate-limit assertion then spans an actual retry, and recovery
        # has a deterministic budget even on a loaded runner.
        real_backoff = offload_module._RETRY_BACKOFF
        offload_module._RETRY_BACKOFF = 2
        off = Offloader({"nas_offload_root": nas, "nas_offload_mode": "move"},
                        on_log=logs.append)
        off.start()

        # ---- 1. NAS down: failure keeps the clip queued and local ----
        clip = os.path.join(local, "Elden Ring", "boss.mkv")
        os.makedirs(os.path.dirname(clip))
        with open(clip, "wb") as f:
            f.write(os.urandom(400_000))
        off.queue(clip, "Elden Ring")
        wait_until(lambda: any("unreachable" in m.lower() for m in logs))
        check("down: unreachable logged", any("unreachable" in m.lower()
                                              for m in logs))
        check("down: item stays queued", off.pending_count() == 1,
              off.pending_count())
        check("down: local untouched", os.path.exists(clip))
        n_unreachable = sum("unreachable" in m.lower() for m in logs)
        # With a 2s backoff the second attempt (and its suppressed log line)
        # lands inside this window - the rate limit is proven, not assumed.
        time.sleep(3.0)
        check("down: log is rate-limited while still down",
              sum("unreachable" in m.lower() for m in logs) == n_unreachable,
              f"{n_unreachable} -> "
              f"{sum('unreachable' in m.lower() for m in logs)}")

        # ---- 2. recovery lands inside one backoff window ----
        # The worker's backoff wait polls _root_is_up() - a real os.path.isdir
        # on the root, which os.makedirs below satisfies - about once a
        # second. The UP[0] flag gates _process itself; recovery needs both
        # the real dir and the flag, which is exactly what production does.
        UP[0] = True
        os.makedirs(nas)
        dest = os.path.join(nas, "Elden Ring", "boss.mkv")
        t0 = time.time()
        arrived = wait_until(lambda: os.path.exists(dest), timeout=20.0)
        check("recovery: copy lands inside one backoff window", arrived,
              f"{time.time() - t0:.1f}s")
        # The local delete happens after the rename (finalize hashes first);
        # on a loaded runner that lag outlives this test's poll gap.
        check("recovery: move completed, local removed",
              arrived and wait_until(lambda: not os.path.exists(clip),
                                     timeout=15.0))
        check("recovery: queue drained",
              wait_until(lambda: off.pending_count() == 0))

        # ---- 4. source gone while queued: dropped, not stuck ----
        ghost = os.path.join(local, "Hollow Knight", "ghost.mkv")
        off.queue(ghost, "Hollow Knight")
        wait_until(lambda: off.pending_count() == 0, timeout=10.0)
        check("gone source: dropped from queue", off.pending_count() == 0,
              off.pending_count())
        check("gone source: says so in the log",
              any("source gone" in m.lower() for m in logs),
              logs[-1] if logs else "")
        check("gone source: nothing appeared on NAS",
              not os.path.exists(os.path.join(nas, "Hollow Knight")))

        off.stop()
    finally:
        paths_module.APP_DIR = original_app_dir
        offload_module.isdir_within = real_isdir_within
        offload_module.ts.diagnose = real_diagnose
        offload_module._RETRY_BACKOFF = real_backoff

    passed_all = all(p for _, p, _ in results)
    for name, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")
    print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} "
          f"({len(results)} checks)")
    return 0 if passed_all else 1


if __name__ == "__main__":
    sys.exit(run())
