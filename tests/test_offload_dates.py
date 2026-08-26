"""NAS month folders (nas_offload_date_folders).

The one invariant: _dest_present (the scan's dedup) must agree with
_dest_dir_for (what the worker creates). If they ever disagree, the scan
re-queues clips that are already on the NAS - wasted bandwidth at best,
duplicate copies at worst. The month tier comes from the source's mtime, so
a backlog scanned in August files June clips under June and stays
deterministic across days.

    python tests/test_offload_dates.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import paths as paths_module
from obsauto import offload as offload_module
from obsauto.offload import Offloader, _month_for

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def make_clip(path, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(os.urandom(200_000))
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def run():
    work = tempfile.mkdtemp(prefix="nebula-offload-dates-")
    original_app_dir = paths_module.APP_DIR
    real_diagnose = offload_module.ts.diagnose
    offload_module.ts.diagnose = lambda p: "lan"

    app_dir = os.path.join(work, "appdir")
    os.makedirs(app_dir)
    paths_module.APP_DIR = app_dir

    local = os.path.join(work, "local")
    nas = os.path.join(work, "nas")
    root = os.path.join(local, "Elden Ring")

    # 2026-06-15 12:00 local time.
    june = time.mktime(time.strptime("2026-06-15", "%Y-%m-%d"))
    clip_june = os.path.join(root, "margit.mkv")
    make_clip(clip_june, mtime=june)

    try:
        base_cfg = {"nas_offload_root": nas, "nas_offload_mode": "copy"}

        # ---- off by default: layout unchanged ----
        off = Offloader(dict(base_cfg))
        dest_dir, game = off._dest_dir_for(clip_june, "Elden Ring")
        check("default: no month tier",
              dest_dir == os.path.join(nas, "Elden Ring"), dest_dir)
        check("default: game label unchanged", game == "Elden Ring", game)

        # ---- on: month tier from the source's own mtime ----
        cfg_dates = dict(base_cfg)
        cfg_dates["nas_offload_date_folders"] = True
        off2 = Offloader(cfg_dates)
        dest_dir2, _ = off2._dest_dir_for(clip_june, "Elden Ring")
        expected = os.path.join(nas, "Elden Ring",
                                time.strftime("%Y-%m", time.localtime(june)))
        check("dates on: June clip lands in June", dest_dir2 == expected,
              "got " + dest_dir2)

        # Dedup agrees with the worker, before and after the copy exists.
        check("dedup: absent -> not present", off2._dest_present(clip_june, "Elden Ring") is False)
        os.makedirs(dest_dir2, exist_ok=True)
        with open(os.path.join(dest_dir2, "margit.mkv"), "wb") as f:
            f.write(open(clip_june, "rb").read())
        check("dedup: same-size copy found after month move",
              off2._dest_present(clip_june, "Elden Ring") is True)

        # A different-sized file at the old flat location must NOT satisfy
        # dedup when months are on - that's the re-queue bug this pins.
        os.makedirs(os.path.join(nas, "Elden Ring"), exist_ok=True)
        with open(os.path.join(nas, "Elden Ring", "flat.mkv"), "wb") as f:
            f.write(os.urandom(1))
        clip_flat = os.path.join(root, "flat.mkv")
        make_clip(clip_flat, mtime=june)
        check("flat leftover doesn't count as the dated dest",
              off2._dest_present(clip_flat, "Elden Ring") is False)

        # Unreadable mtime degrades to no month rather than crashing or
        # inventing today.
        ghost = os.path.join(root, "ghost.mkv")
        check("unreadable mtime: no month invented",
              _month_for(ghost) == "", repr(_month_for(ghost)))

        # Worker end-to-end: _process honours the tier and finalize reports
        # the game folder (not the month) for session bookkeeping.
        real_isdir = offload_module.isdir_within
        offload_module.isdir_within = lambda p, timeout=2.0: True
        try:
            clip_new = os.path.join(root, "godrick.mkv")
            make_clip(clip_new, mtime=time.time() - 3600)
            ok = off2._process({"path": clip_new, "game": "Elden Ring"})
            month_dir = os.path.join(nas, "Elden Ring", time.strftime("%Y-%m"))
            landed = os.path.join(month_dir, "godrick.mkv")
            check("worker: dated copy verified",
                  ok is True and os.path.isfile(landed), landed)
            check("worker: copy mode keeps local", os.path.exists(clip_new))
        finally:
            offload_module.isdir_within = real_isdir

        # Toggling off mid-life returns to the flat path for new copies;
        # existing dated copies simply stay where they are (never moved).
        off3 = Offloader(dict(base_cfg))
        back = off3._dest_dir_for(clip_june, "Elden Ring")[0]
        check("toggle off: back to flat for new copies",
              back == os.path.join(nas, "Elden Ring"), back)
    finally:
        paths_module.APP_DIR = original_app_dir
        offload_module.ts.diagnose = real_diagnose

    passed_all = all(p for _, p, _ in results)
    for name, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name:<46} {detail}")
    print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} "
          f"({len(results)} checks)")
    return 0 if passed_all else 1


if __name__ == "__main__":
    sys.exit(run())
