"""Find recordings too short to be worth keeping, across every library root.

The live cull in ``Monitor._stop_current_recording`` only ever sees a clip at
the moment it stops. Anything already on disk from before that cull existed -
or from while it was measuring wall clock and therefore never firing - is
still there. This is the one-off sweep for those.

    python tools/cull_short_clips.py                 # report only, touches nothing
    python tools/cull_short_clips.py --seconds 10    # a different threshold
    python tools/cull_short_clips.py --csv out.csv   # write the full candidate list
    python tools/cull_short_clips.py --apply         # actually remove them

**It deletes nothing without --apply.** Read the list first; that is the
point of the tool.

What it will not do, ever:

* Touch a file it could not measure. No ffprobe, an unreadable container, a
  duration of zero - all mean "unknown", and unknown is kept. A sweep that
  guessed would eventually guess wrong about footage there is one copy of.
* Hard-delete. On a local volume a candidate goes to the Recycle Bin. The
  NAS has no Recycle Bin, so there a candidate is *moved* into a quarantine
  folder at the root of that library and left for you to look at. Nothing is
  unlinked by this script, on any drive.
* Touch a replay, a marked clip, or anything under `Z:\\dad 4tb`.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import session_log, thumbs
from obsauto.config import load_config
from obsauto.recycle import RecycleError, recyclable, to_recycle_bin

VIDEO_EXTS = (".mkv", ".mp4", ".mov", ".flv", ".ts", ".m4v")

#: Where a NAS candidate is parked, since a network drive has no bin.
QUARANTINE_DIRNAME = "_culled short clips"

#: Never descend into these, wherever they appear.
SKIP_DIRS = {
    "dad 4tb",                 # someone else's data; out of bounds
    QUARANTINE_DIRNAME.lower(),
    ".nebula-thumbs", "clip_cache", "_video_frames",
}

#: A replay is deliberate - it is saved *because* it was worth keeping, and
#: it is short by design. Culling those would be exactly backwards.
REPLAY_HINTS = ("replay", "/replays/", "\\replays\\")


def _skip_dir(name: str) -> bool:
    low = name.lower()
    return low in SKIP_DIRS or low.startswith(".")


def _looks_like_replay(path: str) -> bool:
    low = path.lower()
    return any(hint in low for hint in REPLAY_HINTS)


def walk_videos(root: str):
    """Every video file under root, skipping the directories above."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _skip_dir(d)]
        for name in filenames:
            if name.lower().endswith(VIDEO_EXTS) and not name.endswith(".part"):
                yield os.path.join(dirpath, name)


def marked_paths() -> set:
    """Clips with a mark on them, from the session log. Never candidates."""
    out = set()
    try:
        for span in session_log.spans():
            if span.get("marks") and span.get("path"):
                out.add(os.path.normcase(os.path.abspath(span["path"])))
    except Exception:
        pass
    return out


def scan(roots, threshold, marked, verbose=False):
    """Measure everything and sort it into candidates / kept / unmeasurable."""
    candidates, unmeasured = [], []
    scanned = 0
    for root in roots:
        if not os.path.isdir(root):
            print("  (skipped, not reachable: %s)" % root)
            continue
        print("  scanning %s ..." % root)
        for path in walk_videos(root):
            scanned += 1
            if verbose and scanned % 250 == 0:
                print("    %d files measured" % scanned)
            if _looks_like_replay(path):
                continue
            if os.path.normcase(os.path.abspath(path)) in marked:
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            seconds = thumbs.duration_of(path)
            if not seconds:
                # Unknown length. Kept, and reported separately so a broken
                # ffprobe shows up as "I could not tell" rather than as a
                # library that happens to have no short clips in it.
                unmeasured.append((path, size))
                continue
            if seconds < threshold:
                candidates.append((path, size, seconds))
    return {"scanned": scanned, "candidates": candidates,
            "unmeasured": unmeasured}


def _human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0


def quarantine(path, root):
    """Move a NAS candidate aside instead of deleting it."""
    dest_dir = os.path.join(root, QUARANTINE_DIRNAME)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(path))
    stem, ext = os.path.splitext(dest)
    n = 1
    while os.path.exists(dest):
        dest = "%s (%d)%s" % (stem, n, ext)
        n += 1
    os.replace(path, dest)
    return dest


def root_for(path, roots):
    best = ""
    norm = os.path.normcase(os.path.abspath(path))
    for root in roots:
        r = os.path.normcase(os.path.abspath(root))
        if norm.startswith(r) and len(r) > len(best):
            best = root
    return best or os.path.dirname(path)


def apply(candidates, roots):
    done = failed = 0
    for path, _size, _seconds in candidates:
        try:
            if recyclable(path):
                to_recycle_bin(path)
                print("  recycled  %s" % path)
            else:
                dest = quarantine(path, root_for(path, roots))
                print("  moved     %s -> %s" % (path, dest))
            done += 1
        except (RecycleError, OSError) as exc:
            print("  KEPT      %s (%s)" % (path, exc))
            failed += 1
    return done, failed


def main(argv=None):
    cfg = load_config()
    default_local = cfg.get("recording_root") or "D:/OBS Recordings"

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=10.0,
                    help="cull clips shorter than this (default 10)")
    ap.add_argument("--root", action="append", default=None,
                    help="a library root; repeatable. Defaults to the local "
                         "recording root plus Z:/OBS and Z:/OBS-recovered")
    ap.add_argument("--csv", default=None, help="write the candidate list here")
    ap.add_argument("--apply", action="store_true",
                    help="actually remove the candidates (Recycle Bin on a "
                         "local drive, quarantine folder on the NAS)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    roots = args.root or [default_local, "Z:/OBS", "Z:/OBS-recovered"]

    if not thumbs.available():
        print("ffprobe not found - every clip would be unmeasurable, so there "
              "is nothing this can safely do. Install ffmpeg and re-run.")
        return 2

    print("Threshold : under %.0fs" % args.seconds)
    print("Roots     :")
    result = scan(roots, args.seconds, marked_paths(), verbose=args.verbose)

    cands = sorted(result["candidates"], key=lambda c: c[2])
    total = sum(c[1] for c in cands)
    print("\n%d file%s measured." % (result["scanned"],
                                     "" if result["scanned"] == 1 else "s"))
    print("%d candidate%s under %.0fs, %s in total." % (
        len(cands), "" if len(cands) == 1 else "s", args.seconds, _human(total)))
    if result["unmeasured"]:
        print("%d file%s could not be measured and are being kept." % (
            len(result["unmeasured"]),
            "" if len(result["unmeasured"]) == 1 else "s"))

    for path, size, seconds in cands[:40]:
        print("  %6.1fs  %9s  %s" % (seconds, _human(size), path))
    if len(cands) > 40:
        print("  ... and %d more (use --csv to see them all)" % (len(cands) - 40))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["path", "bytes", "seconds"])
            for path, size, seconds in cands:
                w.writerow([path, size, "%.2f" % seconds])
            for path, size in result["unmeasured"]:
                w.writerow([path, size, "unmeasured"])
        print("\nFull list written to %s" % args.csv)

    if not args.apply:
        print("\nDry run - nothing was touched. Re-run with --apply to act on "
              "the list above.")
        return 0

    print("\nApplying at %s ..." % time.strftime("%H:%M:%S"))
    done, failed = apply(cands, roots)
    print("Removed %d, kept %d that could not be moved." % (done, failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
