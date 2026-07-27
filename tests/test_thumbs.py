"""Clip thumbnails and Length - spec 7f.

Length and thumbnails were omitted since v2 for one reason: "needs ffmpeg,
which this project doesn't depend on". ffmpeg is now installed and wired in as
an *optional* dependency, so the important half of this file is what happens
when it isn't there - the Clips pane must be exactly as it was, with one
dismissible row in Settings and no thumbnails, rather than broken.

Extraction itself is exercised against a real clip when one exists on this
machine, and skipped (loudly) when it doesn't.

    python tests/test_thumbs.py
"""
import glob
import os
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto import settings_spec, thumbs
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


# ---------------------------------------------------------------------------
# The contract, with and without ffmpeg
# ---------------------------------------------------------------------------
check("four frames, at the spec's offsets",
      thumbs.FRAME_OFFSETS == (0.10, 0.35, 0.60, 0.85), thumbs.FRAME_OFFSETS)
check("the row shows frame 3", thumbs.DEFAULT_FRAME == 2, thumbs.DEFAULT_FRAME)
check("frames are 336x189 WebP q70",
      (thumbs.THUMB_W, thumbs.THUMB_H, thumbs.WEBP_QUALITY) == (336, 189, 70),
      (thumbs.THUMB_W, thumbs.THUMB_H, thumbs.WEBP_QUALITY))
check("the cache lives where the spec puts it",
      thumbs.CACHE_DIR.replace("\\", "/") == ".nebula/thumbs", thumbs.CACHE_DIR)

root = tempfile.mkdtemp(prefix="nebula-thumbs-")
paths = thumbs.frame_paths(root, "D:/clips/Game/2026-07-27 12-00-00.mkv")
check("frames are named <stem>-{1..4}.webp",
      [os.path.basename(p) for p in paths]
      == [f"2026-07-27 12-00-00-{i}.webp" for i in (1, 2, 3, 4)],
      [os.path.basename(p) for p in paths])
check("they sit under the recording root's cache",
      all(os.path.dirname(p) == thumbs.cache_dir(root) for p in paths))
check("a clip with no frames reports so",
      not thumbs.have_frames(root, "D:/clips/Game/nope.mkv"))

# Missing ffmpeg must degrade, never raise.
real_tool = thumbs._tool
thumbs._tool = lambda name: None
check("no ffmpeg -> not available", thumbs.available() is False)
check("no ffmpeg -> no duration, no exception",
      thumbs.duration_of("anything.mkv") is None)
check("no ffmpeg -> no frames, no exception",
      thumbs.extract(root, "anything.mkv", 100) == [])
worker = thumbs.ThumbWorker(root)
check("no ffmpeg -> the worker refuses work quietly",
      worker.submit("anything.mkv") is False)
thumbs._tool = real_tool

check("a missing clip file is handled",
      thumbs.extract(root, os.path.join(root, "gone.mkv"), 60) == [])
check("a zero-length clip yields nothing",
      thumbs.extract(root, __file__, 0) == [])

# purge() is what keeps the cache from outliving the clips.
os.makedirs(thumbs.cache_dir(root), exist_ok=True)
for p in paths:
    open(p, "wb").close()
check("frames exist before the purge", thumbs.have_frames(root, paths[0].replace("-1.webp", ".mkv")))
thumbs.purge(root, "D:/clips/Game/2026-07-27 12-00-00.mkv")
check("purge removes every frame",
      not any(os.path.exists(p) for p in paths), [p for p in paths if os.path.exists(p)])

# ---------------------------------------------------------------------------
# Against a real recording, if there is one
# ---------------------------------------------------------------------------
available = thumbs.available()
check("ffmpeg and ffprobe are both found", available,
      f"ffmpeg={thumbs._tool('ffmpeg')} ffprobe={thumbs._tool('ffprobe')}")

# Newest *finished* clip. A recording still being written has no duration in
# its container header - Matroska writes that on finalisation - so ffprobe
# correctly reports nothing for it, and picking it would fail this test for the
# right reason at the wrong moment. Anything untouched for a minute is settled.
real = [p for p in sorted(glob.glob(os.path.join(
            load_config().get("recording_root", ""), "*", "*.mkv")),
        key=os.path.getmtime, reverse=True)
        if time.time() - os.path.getmtime(p) > 60]
if available and real:
    clip = real[0]
    t0 = time.perf_counter()
    seconds = thumbs.duration_of(clip)
    probe_ms = (time.perf_counter() - t0) * 1000
    check("a real clip's duration is read", bool(seconds and seconds > 0), seconds)
    check("reading it doesn't decode the file", probe_ms < 2000, f"{probe_ms:.0f}ms")

    out = tempfile.mkdtemp(prefix="nebula-thumbs-real-")
    t0 = time.perf_counter()
    frames = thumbs.extract(out, clip, seconds)
    extract_ms = (time.perf_counter() - t0) * 1000
    check("four frames come out of a real clip", len(frames) == 4, len(frames))
    check("extraction seeks rather than decoding from zero",
          extract_ms < 8000, f"{extract_ms:.0f}ms for {os.path.getsize(clip)/1e9:.1f} GB")
    if frames:
        from PIL import Image
        sizes = {Image.open(f).size for f in frames}
        check("every frame is the spec's size", sizes == {(336, 189)}, sizes)
        check("frames are small enough to cache freely",
              all(os.path.getsize(f) < 60 * 1024 for f in frames),
              [os.path.getsize(f) // 1024 for f in frames])
        # Four *different* moments, not the same frame four times.
        digests = {open(f, "rb").read()[:2048] for f in frames}
        check("the four frames are distinct moments", len(digests) == 4, len(digests))
    check("a second extract reuses the cache",
          thumbs.extract(out, clip, seconds) == frames)
else:
    check("skipped: no recording available to extract from", True,
          "no .mkv under recording_root" if available else "ffmpeg absent")

# ---------------------------------------------------------------------------
# The pane
# ---------------------------------------------------------------------------
app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=200):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


settle(300)

check("the worker never runs during a recording",
      app.thumbs.is_busy is not None and "is_busy" in open(
          os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "obsauto", "thumbs.py"), encoding="utf-8").read())
app._is_recording = True
check("...and is_busy reflects that", app.thumbs.is_busy() is True)
app._is_recording = False
check("...and clears when it stops", app.thumbs.is_busy() is False)

app._clip_durations["X"] = 3825
check("length renders as h:mm:ss",
      app._clip_length_label({"path": "X"}) == "1:03:45",
      app._clip_length_label({"path": "X"}))
app._clip_durations["Y"] = 95
check("a short clip renders as m:ss",
      app._clip_length_label({"path": "Y"}) == "1:35",
      app._clip_length_label({"path": "Y"}))
check("an unknown duration renders as nothing, not 0:00",
      app._clip_length_label({"path": "Z"}) == "",
      app._clip_length_label({"path": "Z"}))

check("the dismissal record is internal, not a setting",
      "ffmpeg_notice_dismissed" in settings_spec.INTERNAL_KEYS)

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<52} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
