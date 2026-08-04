"""Icons for the Games pane: the real one where we can get it, an honest
generated tile where we can't.

Why this is not just "read the icon"
------------------------------------
The classifier keys everything by **exe basename** (`starrail.exe`), because
that is what the Monitor can see for certain and what stays true across
machines. An icon needs the *executable*, which is a path - and a path is
machine-specific, so it deliberately does not live in `games.json`
(that file syncs to GitHub and merges across devices; see the sync invariants
in CLAUDE.md). It lives here instead, in a local sidecar next to the config.

The consequence, stated plainly: **an app gets its real icon the first time it
runs while Nebula is watching**, not retroactively. Anything not yet seen -
including every entry classified before this existed - gets a monogram tile.
That is why the tile is designed to be good rather than to be a placeholder:
for most rows, most of the time, it *is* the icon.

Three layers, cheapest first:

1. ``APP_DIR/icons/<basename>.png``  - already extracted, just read it
2. the executable, if a path was ever recorded  - extract and cache it
3. a monogram tile derived from the display name - deterministic, so a game
   keeps the same colour forever, and drawn from ``design_v3.ACCENTS`` so it
   cannot introduce a hue the design system does not already own
"""

import hashlib
import json
import os
import threading

from PIL import Image, ImageDraw

from . import design_v3 as dv
from .app_log import log_to_file
from .paths import APP_DIR

# Machine-local, never synced. See the module docstring.
PATHS_FILE = os.path.join(APP_DIR, "app_paths.json")
ICON_DIR = os.path.join(APP_DIR, "icons")

SIZE = 64                     # stored size; the pane draws it at 22-28 CSS px

_lock = threading.Lock()
_paths = None                 # basename -> exe path, lazily loaded
_memo = {}                    # basename -> PNG bytes, bounded by MEMO_MAX

# The image caches that ran the process out of GDI handles in v3 were the
# unbounded ones. There are tens of apps here, not thousands, but the bound is
# the point: a cache with no ceiling is a leak that has not happened yet.
MEMO_MAX = 128


# --- the local path sidecar ------------------------------------------------

def _load_paths():
    global _paths
    if _paths is not None:
        return _paths
    try:
        with open(PATHS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        _paths = {str(k).lower(): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        _paths = {}
    return _paths


def remember(exe_path):
    """Record where an executable lives, keyed by its basename.

    Called from the Monitor, which already resolves a full path for every
    foreground process it inspects. Cheap and idempotent: it only writes when
    the path is new or has moved (a Steam library move, a reinstall).
    """
    if not exe_path:
        return
    basename = os.path.basename(exe_path).lower()
    if not basename:
        return
    with _lock:
        paths = _load_paths()
        if paths.get(basename) == exe_path:
            return
        paths[basename] = exe_path
        # A moved executable invalidates whatever we extracted from the old one.
        _memo.pop(basename, None)
        cached = os.path.join(ICON_DIR, basename + ".png")
        try:
            if os.path.exists(cached):
                os.remove(cached)
        except OSError:
            pass
        try:
            os.makedirs(APP_DIR, exist_ok=True)
            tmp = PATHS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(paths, fh, indent=2, sort_keys=True)
            os.replace(tmp, PATHS_FILE)
        except OSError as exc:
            log_to_file("[Icons] Couldn't record %s: %s" % (basename, exc))


def known_path(basename):
    with _lock:
        return _load_paths().get((basename or "").lower())


def backfill_from_running(basenames):
    """Learn paths for anything already running, once, at startup.

    Without this the pane only fills in as you happen to launch things, and
    every app classified before this existed would show a monogram until its
    next run. Anything running right now is free to resolve, which in practice
    covers most of the Not-games list immediately.

    Returns the number of new paths learned. Best-effort throughout: a process
    that exits mid-scan, or one owned by another user, is ordinary.
    """
    import psutil
    wanted = {b.lower() for b in basenames if b}
    if not wanted:
        return 0
    learned = 0
    for proc in psutil.process_iter(["name", "exe"]):
        try:
            name = (proc.info["name"] or "").lower()
            if name not in wanted or known_path(name):
                continue
            path = proc.info["exe"]
            if path and os.path.exists(path):
                remember(path)
                learned += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return learned


# --- layer 3: the monogram -------------------------------------------------

def _hue_for(name):
    """Pick one of design_v3's accents, stably, from the name.

    A hash rather than an index, so adding or removing a game never re-colours
    the others - the colour is a property of the name, not of its position in
    a list.
    """
    accents = list(dv.ACCENTS.values())
    digest = hashlib.sha1((name or "?").lower().encode("utf-8")).digest()
    return accents[digest[0] % len(accents)][0]


def _initials(name):
    words = [w for w in (name or "").replace("_", " ").replace("-", " ").split() if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


# Segoe UI Semibold, then Bold, then whatever Pillow has. The pane draws these
# at ~24px, so the glyph has to be a real font at a real size - Pillow's
# built-in bitmap font is ~11px and would put a speck in the middle of the tile.
_FONT_CANDIDATES = ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf")
_font_cache = {}


def _font(px):
    if px in _font_cache:
        return _font_cache[px]
    from PIL import ImageFont
    font = None
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in _FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(os.path.join(fonts_dir, name), px)
            break
        except OSError:
            continue
    if font is None:
        try:
            font = ImageFont.load_default(size=px)     # Pillow >= 10
        except TypeError:
            font = ImageFont.load_default()
    _font_cache[px] = font
    return font


def monogram(name, size=SIZE):
    """A rounded tile with the name's initials, in one of the system's hues."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r, g, b = dv._hex_to_rgb(_hue_for(name))
    radius = max(2, round(size * dv.RADIUS_TILE / 64.0))
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius,
                           fill=(r, g, b, 56), outline=(r, g, b, 130), width=1)
    text = _initials(name)
    font = _font(round(size * 0.44))
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((size - (right - left)) / 2 - left,
               (size - (bottom - top)) / 2 - top),
              text, fill=dv._hex_to_rgb(dv.ACCENT_TEXT) + (255,), font=font)
    return img


# --- layer 2: the real icon ------------------------------------------------

def extract(exe_path, size=SIZE):
    """The executable's own icon, as a PIL image, or None.

    Windows-only and deliberately soft: a missing pywin32, a path that has
    since been uninstalled, or an executable with no icon resource are all
    ordinary outcomes here, not errors worth surfacing.
    """
    if not exe_path or not os.path.exists(exe_path):
        return None
    try:
        import win32api
        import win32con
        import win32gui
        import win32ui
    except ImportError:
        return None

    large, small = [], []
    try:
        large, small = win32gui.ExtractIconEx(exe_path, 0)
    except Exception:
        return None
    handles = large + small
    if not handles:
        return None

    hicon = handles[0]
    hdc = bitmap = None
    try:
        # GetSystemMetrics is win32api's, not win32gui's. Getting that wrong
        # raised an AttributeError straight into the `except Exception` below,
        # so every extraction silently produced a monogram and the feature
        # looked like it had simply decided not to find any icons.
        w = win32api.GetSystemMetrics(win32con.SM_CXICON)
        h = win32api.GetSystemMetrics(win32con.SM_CYICON)
        screen = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
        hdc = screen.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(screen, w, h)
        hdc.SelectObject(bitmap)
        hdc.DrawIcon((0, 0), hicon)
        info = bitmap.GetInfo()
        img = Image.frombuffer("RGBA", (info["bmWidth"], info["bmHeight"]),
                               bitmap.GetBitmapBits(True), "raw", "BGRA", 0, 1)
        # DrawIcon composites onto an uninitialised DC, so the alpha channel
        # comes back as zeros for icons without one. A fully transparent image
        # would render as nothing at all - treat it as opaque instead.
        if not img.getchannel("A").getbbox():
            img.putalpha(255)
        return img.resize((size, size), Image.LANCZOS)
    except Exception:
        return None
    finally:
        for handle in handles:
            try:
                win32gui.DestroyIcon(handle)
            except Exception:
                pass
        try:
            if bitmap is not None:
                win32gui.DeleteObject(bitmap.GetHandle())
            if hdc is not None:
                hdc.DeleteDC()
        except Exception:
            pass


# --- the thing callers actually want ---------------------------------------

def png_bytes(basename, display_name):
    """PNG for one row, cheapest layer first. Never raises, never returns None."""
    key = (basename or display_name or "?").lower()
    with _lock:
        hit = _memo.get(key)
    if hit is not None:
        return hit

    cached = os.path.join(ICON_DIR, key + ".png") if basename else None
    data = None
    if cached and os.path.exists(cached):
        try:
            with open(cached, "rb") as fh:
                data = fh.read()
        except OSError:
            data = None

    if data is None:
        img = extract(known_path(basename)) if basename else None
        generated = img is None
        if img is None:
            img = monogram(display_name or basename)
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        # Only a real extraction is worth keeping on disk. A monogram is pure
        # arithmetic on the name, so caching it would just be a file to
        # invalidate the day the executable finally shows up.
        if not generated and cached:
            try:
                os.makedirs(ICON_DIR, exist_ok=True)
                with open(cached, "wb") as fh:
                    fh.write(data)
            except OSError:
                pass

    with _lock:
        if len(_memo) >= MEMO_MAX:
            _memo.clear()
        _memo[key] = data
    return data


def data_url(basename, display_name):
    import base64
    return "data:image/png;base64," + base64.b64encode(
        png_bytes(basename, display_name)).decode("ascii")
