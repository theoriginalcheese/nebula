"""Clip thumbnails and durations - spec 7f.

    "Four frames extracted when a clip finishes. The row thumbnail shows frame
     3; moving the pointer across it steps through all four with a progress
     line underneath."

ffmpeg is an **optional** dependency. Everything here degrades to "no thumbnail,
no length" when it isn't on PATH, and the Clips pane keeps working - the spec is
explicit that a missing ffmpeg gets "one dismissible row in Settings → Storage
offering the download - not a modal, not a toast per clip".

Two rules from the spec govern the worker, and both exist to keep extraction off
the critical path: it runs at below-normal priority, and **never during a
recording**. Four seeks through a multi-gigabyte file while OBS is writing to
the same disk is exactly the wrong moment.
"""

import glob
import json
import os
import queue
import shutil
import subprocess
import threading

CACHE_DIR = os.path.join(".nebula", "thumbs")
FRAME_OFFSETS = (0.10, 0.35, 0.60, 0.85)   # "10 / 35 / 60 / 85% of duration"
FRAME_COUNT = len(FRAME_OFFSETS)
DEFAULT_FRAME = 2                          # "the row thumbnail shows frame 3" (0-based)
THUMB_W, THUMB_H = 336, 189
WEBP_QUALITY = 70

# Windows: keep every child process silent and out of the way.
_CREATE_NO_WINDOW = 0x08000000
_BELOW_NORMAL = 0x00004000
_FLAGS = (_CREATE_NO_WINDOW | _BELOW_NORMAL) if os.name == "nt" else 0


# winget puts ffmpeg here and edits the *user* PATH, which only reaches
# processes started afterwards - so a freshly installed ffmpeg is invisible to
# anything already running, including Nebula. Look in the known locations too
# rather than telling someone to reboot.
_FALLBACK_GLOBS = (
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\{name}.exe"),
    os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\**\bin\{name}.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\ffmpeg\bin\{name}.exe"),
    r"C:\ffmpeg\bin\{name}.exe",
)
_tool_cache = {}


def _tool(name):
    """Locate ffmpeg/ffprobe, PATH first.

    The fallbacks matter because winget edits the *user* PATH, and that only
    reaches processes started afterwards - so a freshly installed ffmpeg is
    invisible to anything already running. Looking in the place it was just
    installed beats telling someone to reboot.
    """
    if name in _tool_cache:
        return _tool_cache[name]
    found = shutil.which(name)
    if not found:
        for pattern in _FALLBACK_GLOBS:
            matches = glob.glob(pattern.format(name=name), recursive=True)
            if matches:
                found = matches[0]
                break
    _tool_cache[name] = found
    return found


def available():
    """Both binaries present? Thumbnails need ffmpeg, Length needs ffprobe."""
    return bool(_tool("ffmpeg")) and bool(_tool("ffprobe"))


def _run(args, timeout=30):
    try:
        return subprocess.run(
            args, capture_output=True, timeout=timeout,
            creationflags=_FLAGS, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def duration_of(path):
    """Clip length in seconds, or None. Used for the Clips pane's Length column.

    Reads the container rather than decoding, so it costs a few milliseconds
    even on a multi-gigabyte file.
    """
    exe = _tool("ffprobe")
    if not exe or not os.path.exists(path):
        return None
    result = _run([exe, "-v", "error", "-show_entries", "format=duration",
                   "-of", "json", path], timeout=15)
    if not result or result.returncode != 0:
        return None
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        return None


def cache_dir(recording_root):
    return os.path.join(recording_root, CACHE_DIR)


def frame_paths(recording_root, clip_path):
    """The four cache paths for a clip: <stem>-{1..4}.webp."""
    stem = os.path.splitext(os.path.basename(clip_path))[0]
    folder = cache_dir(recording_root)
    return [os.path.join(folder, f"{stem}-{i + 1}.webp") for i in range(FRAME_COUNT)]


def have_frames(recording_root, clip_path):
    return all(os.path.exists(p) for p in frame_paths(recording_root, clip_path))


def extract(recording_root, clip_path, duration=None):
    """Pull the four frames. Returns the paths that now exist.

    One ffmpeg invocation per frame, each seeking with -ss *before* -i so the
    seek is a container jump rather than a decode from zero - that is the whole
    difference between ~200ms for the set and half a minute.
    """
    exe = _tool("ffmpeg")
    if not exe or not os.path.exists(clip_path):
        return []
    if duration is None:
        duration = duration_of(clip_path)
    if not duration or duration <= 0:
        return []
    targets = frame_paths(recording_root, clip_path)
    try:
        os.makedirs(os.path.dirname(targets[0]), exist_ok=True)
    except OSError:
        return []
    made = []
    for offset, target in zip(FRAME_OFFSETS, targets):
        if os.path.exists(target):
            made.append(target)
            continue
        result = _run([
            exe, "-y", "-loglevel", "error",
            "-ss", f"{duration * offset:.3f}", "-i", clip_path,
            "-frames:v", "1", "-vf", f"scale={THUMB_W}:-1",
            "-quality", str(WEBP_QUALITY), target,
        ])
        if result and result.returncode == 0 and os.path.exists(target):
            made.append(target)
    return made


def purge(recording_root, clip_path):
    """Drop a clip's frames - called when the clip itself is deleted."""
    for path in frame_paths(recording_root, clip_path):
        try:
            os.remove(path)
        except OSError:
            pass


# ---- APP_DIR posters for NAS / remote rows (on-demand, one frame) --------
POSTER_DIRNAME = "clip_posters"


def _poster_safe_name(rel: str) -> str:
    rel = (rel or "").replace("\\", "/").strip("/")
    safe = []
    for ch in rel:
        if ch.isalnum() or ch in "._-":
            safe.append(ch)
        elif ch == "/":
            safe.append("__")
        else:
            safe.append("_")
    name = "".join(safe) or "clip"
    return name[:180]


def poster_path(app_dir, rel):
    """Single list-row poster under ``APP_DIR/clip_posters``."""
    if not app_dir or not rel:
        return ""
    return os.path.join(app_dir, POSTER_DIRNAME, _poster_safe_name(rel) + ".webp")


def have_poster(app_dir, rel):
    path = poster_path(app_dir, rel)
    return bool(path) and os.path.isfile(path)


def extract_poster(app_dir, rel, clip_path, duration=None):
    """Pull one mid-clip frame from ``clip_path`` (local or mounted NAS).

    Does not download the whole file into the clip cache — ffmpeg seeks on the
    source path. Returns the poster path on success, else ``""``.
    """
    exe = _tool("ffmpeg")
    dest = poster_path(app_dir, rel)
    if not exe or not dest or not clip_path or not os.path.exists(clip_path):
        return ""
    if os.path.isfile(dest):
        return dest
    if duration is None:
        duration = duration_of(clip_path)
    if not duration or duration <= 0:
        return ""
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
    except OSError:
        return ""
    offset = duration * FRAME_OFFSETS[DEFAULT_FRAME]
    result = _run([
        exe, "-y", "-loglevel", "error",
        "-ss", f"{offset:.3f}", "-i", clip_path,
        "-frames:v", "1", "-vf", f"scale={THUMB_W}:-1",
        "-quality", str(WEBP_QUALITY), dest,
    ], timeout=60)
    if result and result.returncode == 0 and os.path.isfile(dest):
        return dest
    try:
        if os.path.isfile(dest):
            os.remove(dest)
    except OSError:
        pass
    return ""


def purge_poster(app_dir, rel):
    path = poster_path(app_dir, rel)
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


class ThumbWorker:
    """One background worker, one clip at a time.

    "Cost ~200 ms per clip, 4 seeks, one worker. Priority below normal - never
    during recording. Backfill idle only, oldest last, 1 clip at a time."

    `is_busy()` is asked before every clip and is how "never during recording"
    is enforced; the queue simply waits rather than dropping work.
    """

    def __init__(self, recording_root, on_log=None, is_busy=None, on_done=None):
        self.recording_root = recording_root
        self.log = on_log or (lambda msg: None)
        self.is_busy = is_busy or (lambda: False)
        self.on_done = on_done or (lambda clip, frames: None)
        self._queue = queue.Queue()
        self._thread = None
        self._stop = threading.Event()
        self._seen = set()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._queue.put(None)

    def submit(self, clip_path, duration=None):
        """Queue one clip. Silently ignores duplicates and a missing ffmpeg."""
        if not available() or not clip_path:
            return False
        key = os.path.normcase(os.path.abspath(clip_path))
        if key in self._seen:
            return False
        self._seen.add(key)
        self._queue.put((clip_path, duration))
        self.start()
        return True

    def backfill(self, clip_paths):
        """Queue clips that have no frames yet, newest first.

        "Backfill idle only, oldest last" - so the clips you are most likely to
        be looking at are done first, and the archive trickles in behind.
        """
        queued = 0
        for path in clip_paths:
            if not have_frames(self.recording_root, path):
                if self.submit(path):
                    queued += 1
        return queued

    def _run(self):
        while not self._stop.is_set():
            item = self._queue.get()
            if item is None:
                break
            clip_path, duration = item
            # Never while OBS is writing: four seeks through a large file on
            # the same disk is the worst possible moment.
            while self.is_busy() and not self._stop.is_set():
                if self._stop.wait(2.0):
                    return
            if self._stop.is_set():
                return
            try:
                frames = extract(self.recording_root, clip_path, duration)
            except Exception as exc:
                self.log(f"[Thumbs] {os.path.basename(clip_path)}: {exc}")
                continue
            if frames:
                self.on_done(clip_path, frames)
