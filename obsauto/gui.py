"""OBSOLETE — Tk / CustomTkinter shell.

Shipping UI is the v4 WebView in ``spike/``. ``python main.py`` launches
that path. This module remains so older GUI tests can import ``AppWindow``;
do not add product features here.
"""
import contextlib
import ctypes
import math
import os
import random
import re
import shutil
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import tkinter.messagebox
import traceback

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import classifier as classifier_module
from . import design_v3 as dv
from . import forecast
from . import palette
from . import profiles
from . import replay as replay_mod
from . import session_log
from . import thumbs
from . import settings_spec
from .obs_client import OBSClient, OBSError
from .monitor import Monitor, ensure_obs_running, is_obs_running, list_visible_windows
from .app_log import log_to_file
from .theme_art import (
    generate_backdrop_v3, make_glass_tile, make_solid_tile, to_photo,
)
from .icon_art import generate_animation_frames, render_frame
from . import hotkey
from .paths import RESOURCE_DIR

ICON_PATH = os.path.join(RESOURCE_DIR, "nebula_icon.ico")

# Inspired by BetterDiscord's ClearVision/Neutron: an atmospheric nebula
# backdrop (not a flat gradient, not real OS blur - that's broken on this
# Windows 11 build) with genuinely translucent, rounded "glass" panels
# floating on top. See theme_art.py for how the glass effect actually works.
#
# The styling language: one violet accent, semantic colors only where they
# mean something (green=go, red=recording/stop, amber=paused), and "tinted"
# fills - a dark wash of a color with the bright color as text - instead of
# loud solid fills, so the whole surface stays calm.
# ---- v3 palette ("Nebula Deep") ----
# Every value below now comes from design_v3, which is section 05 of the v3
# mockup as code; tests/test_design_v3.py checks it against the written spec.
# Several of these are unchanged from v2 - the Aurora build already drew on the
# same design language, so ACCENT, EMBER, TEXT, MUTED and SURFACE all survived
# the redesign intact. What changed is the ground, the card layering, and the
# extra hues.
#
# "No other hues exist in this app - log tag colours stay as LOG_TAG_COLORS in
# gui.py." So v2's GREEN / AMBER / TEAL / BLUE / PINK are gone from the chrome:
# connection state is accent-vs-ember now, not green-vs-red. The log tags below
# are the one sanctioned exception, named as such by the spec itself.
BASE_BG = dv.GROUND               # #100D1C window ground
PANEL = dv.PANEL                  # #12101F panel base
CARD_CORE = dv.CARD_CORE          # #181428 the darker *inner* of a card's two layers
CARD_TINT = dv.over(dv.ACCENT, 0.10, dv.CARD_CORE)   # the tinted *outer* shell
CARD_SURFACE = CARD_CORE   # what the glass card *looks* like once composited - used as widget bg_color so rounded widget corners blend in
CARD_BORDER = dv.ACCENT
SURFACE = dv.RAISED               # #241E44 raised surface, keycaps
SURFACE_HOVER = dv.over(dv.ACCENT, 0.16, dv.RAISED)
EDGE = dv.hairline(dv.PANEL)      # never a solid grey - see the spec's hairline rule
ACCENT = dv.ACCENT
ACCENT_HOVER = "#9D91F8"
ACCENT_TINT = dv.over(dv.ACCENT, 0.16, dv.GROUND)
ACCENT_LIGHT = dv.ACCENT_TEXT     # #B9AEF9 accent text / icons on dark
NAV_ACTIVE_TEXT = dv.TEXT
TEXT_SOFT = dv.TEXT_TERTIARY      # #8B84B8 tertiary / captions
EMBER = dv.EMBER                  # #FF5C7A live + errors ONLY
RED = EMBER                       # legacy alias - same hue, v3 name is ember
RED_LIGHT = "#FF7D96"
RED_TINT = dv.over(dv.EMBER, 0.16, dv.CARD_CORE)
RED_TINT_HOVER = dv.over(dv.EMBER, 0.22, dv.CARD_CORE)
RED_HOVER = RED_TINT_HOVER  # legacy alias
RED_DIM = dv.over(dv.EMBER, 0.40, dv.CARD_CORE)
MUTED = dv.TEXT_SECONDARY         # #9A93C4
FAINT = dv.TEXT_EYEBROW           # #736BA4 eyebrow labels, mono meta
TEXT = dv.TEXT                    # #F5F3FF
LOG_TINT = dv.over(dv.GROUND, 0.80, dv.PANEL)
LOG_BG = dv.PANEL

# v2's semantic hues collapse onto v3's two-hue system rather than being
# deleted, so every existing call site adopts the new palette in one move
# instead of being rewritten twice. The mapping follows the spec's own
# assignment ("start/stop -> ember, pause/resume -> accent, error -> ember"):
# anything that used to mean go/steady/informational becomes the accent, and
# only live-and-errors keeps the ember.
GREEN = ACCENT
GREEN_LIGHT = ACCENT_LIGHT
GREEN_TINT = dv.over(dv.ACCENT, 0.12, dv.CARD_CORE)
GREEN_TINT_HOVER = dv.over(dv.ACCENT, 0.18, dv.CARD_CORE)
GREEN_HOVER = GREEN_TINT_HOVER  # legacy alias
AMBER = ACCENT
AMBER_LIGHT = ACCENT_LIGHT
AMBER_TINT = GREEN_TINT
TEAL = ACCENT
BLUE = ACCENT
PINK = ACCENT

# Tag colors for the activity log - each subsystem gets its own hue so a
# glance at the log's left edge tells you who's talking.
#
# These are the ONE place extra hues survive v3, and the spec names them as the
# exception in the same breath as banning everything else: "No other hues exist
# in this app - log tag colours stay as LOG_TAG_COLORS in gui.py." So they are
# written as literals rather than through the aliases above, which all collapse
# to the accent - routing them through those would flatten the log to a single
# colour and lose exactly the affordance the tags exist for.
LOG_TAG_COLORS = {
    "OBS": "#8B7CF6",
    "Monitor": "#7FB7F0",
    "Steam": "#4FD1C5",
    "Manual": "#F5A623",
    "Classifier": "#F0A6CA",
    "Audio": "#3DDC84",
}

# ---- icons ----------------------------------------------------------------
# The v3 spec specifies Phosphor Light throughout. Phosphor is a webfont and
# isn't installed, so rather than bundle a TTF or hand-draw two dozen glyphs,
# these map the spec's icon *roles* onto Segoe Fluent Icons - Windows 11's own
# icon font, already present on every target machine, and a light single-weight
# line set that sits closely with what Phosphor Light looks like.
#
# Keyed by the Phosphor name so design_v3.ICONS stays the single source of
# truth for "which icon means what": look the role up there, then translate
# here. Swapping in a real Phosphor TTF later is a change to this table only.
#
# Every codepoint below was verified by rendering it, not taken from memory.
ICON_FONT = "Segoe Fluent Icons"
_ICON_CODEPOINTS = {
    "broadcast": 0xE704,            # Dashboard - signal waves
    "film-strip": 0xE714,           # Clips
    "game-controller": 0xE7FC,      # Games
    "keyboard": 0xE765,             # Macropad
    "sliders-horizontal": 0xE9E9,   # Settings
    "record": 0xE7C8,               # dot inside a ring - not a plain filled disc
    # Fluent has no dashed circle, so the ring carries the same meaning: not
    # filled, not live. Verified by rendering (tools/verify_glyph.py): its bbox
    # is identical to record's at 12, 16 and 24px, so watching -> recording reads
    # as the dot appearing inside a ring that never moves.
    "circle-dashed": 0xEA3A,        # watching
    "pause": 0xE769,
    "play": 0xE768,
    "scissors": 0xE8C6,             # mark clip
    "stack-simple": 0xE81E,         # scene
    "plugs": 0xEB55,                # disconnected
    "plugs-connected": 0xF384,      # connected
    "hard-drives": 0xEDA2,          # storage
    "timer": 0xE916,                # idle
    "moon": 0xE708,                 # idle pause
    "command": 0xE943,              # hotkey
    "steam-logo": 0xE72C,           # rescan - Fluent has no Steam mark; refresh reads right
    "folder-open": 0xE8DA,          # reveal
    "trash": 0xE74D,                # delete clip
    "arrows-out-simple": 0xE740,    # show window
    "arrows-in-simple": 0xE73F,     # collapse mini
    "sign-out": 0xE7E8,             # quit (tray only)
    "minus": 0xE738,                # hide to tray
    "x": 0xE711,                    # hide to tray
    "square": 0xE73B,               # stop - one of the two sanctioned Fill glyphs
}
ICON_GLYPHS = {name: chr(cp) for name, cp in _ICON_CODEPOINTS.items()}



def icon(role, size=16):
    """(glyph, font) for a v3 icon role, e.g. icon("dashboard")."""
    return ICON_GLYPHS[dv.ICONS[role]], (ICON_FONT, -int(round(size)))


ICON_FONT_FILE = r"C:\Windows\Fonts\SegoeIcons.ttf"


def pill_trailing_icon(glyph, tint, bg, size, scale=1.0):
    """The circle a primary pill's trailing icon sits in.

    "Trailing icons on primary pills live in their own 26-28px circle, flush to
    the right padding." A CTkButton can't hold a canvas item, and an embedded
    widget always paints above canvas art, so the circle can't be drawn behind
    it either. Rendering it as the button's own image (compound="right") is what
    puts a real circle inside the pill, flush right, at the correct size.
    """
    px = max(1, int(round(size * scale)))
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, px - 1, px - 1], fill=dv.over(tint, 0.20, bg))
    try:
        font = ImageFont.truetype(ICON_FONT_FILE, int(px * 0.46))
        draw.text((px / 2, px / 2), glyph, font=font, fill=tint, anchor="mm")
    except Exception:
        pass  # font missing - the tinted circle alone still reads as a chip
    return img

# v3 chassis. All base design units - self.scale multiplies them on high-DPI
# monitors, exactly as before (see nebula-dpi-scaling). Values come from
# design_v3, i.e. section 05 of the mockup.
#
# The structural change from the Aurora shell: the titlebar now spans the FULL
# window width and the nav rail hangs beneath it, where v2 had the rail running
# the full height with the topbar only over the content column. Frame 2a.
WIDTH, HEIGHT = dv.WIDTH, dv.HEIGHT          # 1280 x 808
SIDEBAR_W = dv.RAIL_W                        # 232
TITLEBAR_HEIGHT = dv.TITLEBAR_H              # 46, full width; also the drag region
TOPBAR_HEIGHT = dv.PANE_HEADER_H             # 62, the per-pane header inside the content column
MARGIN = dv.CONTENT_PAD                      # 26 gutter inside the content column
CONTENT_Y0 = TITLEBAR_HEIGHT                 # where the rail and content column start
# Timer pacing. The decorative canvas animation is gone entirely (see the long
# note above _glass in AppWindow); ICON_TICK_MS paces the one remaining
# window-level animation, and IDLE_TICK_MS is how often a parked timer checks
# whether the window has come back on screen.
ICON_TICK_MS = 400
IDLE_TICK_MS = 500

# The rail's five destinations (frame 2a). v3 has no standalone Activity page —
# the activity log is a dashboard block only — so RAIL_VIEWS is the full set of
# views, not a subset.
RAIL_VIEWS = list(dv.PANES)

VIEW_TITLES = {
    "dashboard": "Dashboard",
    "clips": "Clips",
    "games": "Games",
    "macropad": "Macropad",
    "settings": "Settings",
}
VIDEO_EXTS = (".mkv", ".mp4", ".mov", ".flv", ".ts", ".m4v")
LOG_HISTORY = 500  # lines kept for replay into the dashboard activity panel


def short_obs_version(raw):
    """Frame 2a draws ``OBS 30.2`` — keep major.minor when a patch is present."""
    if not raw:
        return ""
    parts = str(raw).strip().split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{parts[0]}.{parts[1]}"
    return str(raw).strip()


def format_video_label(settings):
    """``2560×1440 · 60 fps`` from GetVideoSettings — or ``""`` if incomplete."""
    if not settings:
        return ""
    w = settings.get("baseWidth") or settings.get("outputWidth")
    h = settings.get("baseHeight") or settings.get("outputHeight")
    num = settings.get("fpsNumerator")
    den = settings.get("fpsDenominator") or 1
    if not w or not h or not num or not den:
        return ""
    fps = float(num) / float(den)
    fps_s = (f"{fps:.0f}" if abs(fps - round(fps)) < 0.05
             else f"{fps:.2f}".rstrip("0").rstrip("."))
    return f"{int(w)}\u00d7{int(h)} \u00b7 {fps_s} fps"

# Rearrangeable dashboard blocks. Heights are fixed so reordering is a pure
# translation of each block - no rebuilding, nothing to resize.
DEFAULT_BLOCKS = ("hero", "stats", "replay", "activity")
BLOCK_LABELS = {"hero": "Live session", "stats": "Session stats",
                "replay": "Instant replay", "activity": "Activity"}
BLOCK_GAP = 18
GRID_COL_GAP = 18
HERO_H = 300
# Fixed footprint heights per (block, span). span 2 = full width; span 1 = half
# width (stats reflows to 2x2, so it's taller). Heights are fixed so laying the
# grid out is pure arithmetic - no measuring, nothing to resize. Activity's 246
# includes its 22px header.
# Keyed by column span: 12 = full width, 6 = the narrow form (stats reflows to
# 2x2, so it's taller). A 2/3 module uses the narrow height too.
BLOCK_HEIGHTS = {
    "hero": {12: HERO_H, 6: HERO_H},   # hero is full-width only; 6 is never used
    "stats": {12: 92, 6: 198},
    "replay": {12: 236, 6: 236},       # 7a: "486x236, half width"
    "activity": {12: 246, 6: 246},
}
# 6.8: "Persisted as dashboard_layout[] - {id, span}", span in grid columns.
# 7g: "Default layout puts replay beside the hero card" - the hero is full
# width, so beside it means the row directly under, sharing with the stats.
DEFAULT_GRID = [
    {"id": "hero", "span": 12},
    {"id": "stats", "span": 6},
    {"id": "replay", "span": 6},
    {"id": "activity", "span": 12},
]


# ---- DPI / UI scaling ----------------------------------------------------
# The whole UI is a fixed-pixel canvas design authored in these base units
# (WIDTH/HEIGHT/MARGIN and literal coordinates + font sizes). To render it
# larger *and* pixel-crisp on a high-DPI monitor instead of a tiny 1:1 window,
# we pick one uniform scale factor from the monitor's DPI and multiply
# everything by it: CTk widgets via ctk.set_widget_scaling(), and the raw
# tk.Canvas art via the ScaledCanvas proxy below (coordinates + sizes + font
# sizes) plus generating the background/glass images at the scaled resolution.
# On a 100%-scaling display the factor is 1.0, so nothing changes.
def _compute_ui_scale(window):
    try:
        from ctypes import windll, pointer, wintypes
        hwnd = wintypes.HWND(window.winfo_id())
        monitor = windll.user32.MonitorFromWindow(hwnd, 2)  # NEAREST
        x_dpi, y_dpi = wintypes.UINT(), wintypes.UINT()
        windll.shcore.GetDpiForMonitor(monitor, 0, pointer(x_dpi), pointer(y_dpi))
        factor = (x_dpi.value + y_dpi.value) / (2 * 96)
    except Exception:
        factor = 1.0
    # Snap to quarter steps (1.0/1.25/1.5/...) so we track Windows' own scaling
    # levels and avoid odd fractional rounding; never shrink below the 1.0
    # design size.
    return max(1.0, round(factor * 4) / 4)


def _scale_font(font, scale):
    """Scale the size element of a Tk font tuple, e.g. ("Segoe UI", 13) or
    ("Consolas", 12, "bold"). Leaves non-tuple fonts untouched."""
    if isinstance(font, (tuple, list)) and len(font) >= 2 and isinstance(font[1], (int, float)):
        size = int(round(font[1] * scale))
        size = size if size != 0 else (1 if font[1] >= 0 else -1)
        return (font[0], size) + tuple(font[2:])
    return font


class ScaledCanvas:
    """Thin proxy around a tk.Canvas that multiplies every coordinate, size
    and font by a uniform UI-scale factor. Lets the drawing code stay written
    in base (1.0) design units while the actual canvas renders scaled. Only
    the geometry-bearing arguments are touched; colors, text, images, anchors
    and everything else pass straight through, and any method not overridden
    here is delegated to the real canvas via __getattr__."""

    def __init__(self, canvas, scale):
        self._c = canvas
        self._scale = scale

    def _n(self, v):
        return int(round(v * self._scale)) if isinstance(v, (int, float)) else v

    def _coords(self, coords):
        return [self._n(v) for v in coords]

    def _kw(self, kw):
        for key in ("width", "height"):
            if key in kw and isinstance(kw[key], (int, float)):
                kw[key] = self._n(kw[key])
        if "font" in kw:
            kw["font"] = _scale_font(kw["font"], self._scale)
        return kw

    # position + size/font bearing
    def create_text(self, x, y, **kw):
        return self._c.create_text(self._n(x), self._n(y), **self._kw(kw))

    def create_image(self, x, y, **kw):
        return self._c.create_image(self._n(x), self._n(y), **kw)

    def create_window(self, x, y, **kw):
        return self._c.create_window(self._n(x), self._n(y), **self._kw(kw))

    # pure-coordinate shapes (kw here is outline color/fill, not geometry)
    def create_oval(self, *coords, **kw):
        return self._c.create_oval(*self._coords(coords), **kw)

    def create_rectangle(self, *coords, **kw):
        return self._c.create_rectangle(*self._coords(coords), **kw)

    def create_line(self, *coords, **kw):
        return self._c.create_line(*self._coords(coords), **kw)

    def coords(self, item, *args):
        if not args:
            return self._c.coords(item)
        return self._c.coords(item, *self._coords(args))

    def move(self, item, dx, dy):
        return self._c.move(item, self._n(dx), self._n(dy))

    def itemconfigure(self, item, **kw):
        if "font" in kw:
            kw["font"] = _scale_font(kw["font"], self._scale)
        return self._c.itemconfigure(item, **kw)
    itemconfig = itemconfigure

    def __getattr__(self, name):
        return getattr(self._c, name)


def apply_rounded_corners(window):
    """Windows 11's DWM will round a window's actual corners for us - the
    only reliable way to avoid the harsh rectangular edges a custom-chrome
    (overrideredirect) window gets by default. (Real acrylic blur-behind was
    also tried and confirmed broken on this Windows 11 build via the
    undocumented SetWindowCompositionAttribute API - this DWM attribute is
    the separate, officially supported one and does work.)"""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWC_ROUND = 2
        value = ctypes.c_int(DWMWC_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


def _format_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def suggest_display_name(basename):
    """Turn a raw exe name like 'genshinimpact.exe' or 'space_game-2.exe'
    into a reasonable guess at a real title ('Genshinimpact', 'Space Game 2')
    - strips the extension, splits camelCase/underscores/hyphens into words,
    and title-cases the result. Just a starting point in an editable field,
    not meant to be perfect (there's no reliable way to know "Genshin Impact"
    should have a space without a lookup) - the point is nothing ever
    defaults to a bare, ungrammatical '<name>.exe'."""
    name = os.path.splitext(basename)[0]
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.title() if name else basename


def _blend_hex(c0, c1, t):
    c0, c1 = c0.lstrip("#"), c1.lstrip("#")
    rgb0 = tuple(int(c0[i:i + 2], 16) for i in (0, 2, 4))
    rgb1 = tuple(int(c1[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(int(rgb0[i] + (rgb1[i] - rgb0[i]) * t) for i in range(3))


def _shift_lightness(hex_colour, amount):
    """Lighten (+) or darken (-) by a fraction, keeping the hue.

    7b: "Per-game shade: lightness ±8% only - never a new hue." Nudging each
    channel toward white or black preserves the hue exactly, which a hue
    rotation would not - and v3 is a two-hue system.
    """
    c = hex_colour.lstrip("#")
    rgb = [int(c[i:i + 2], 16) for i in (0, 2, 4)]
    if amount >= 0:
        rgb = [v + (255 - v) * amount for v in rgb]
    else:
        rgb = [v * (1 + amount) for v in rgb]
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def _vertical_gradient_tile(width, height, top_hex, bottom_hex, radius):
    """A rounded tile with a 180deg gradient - the ribbon's recording block."""
    width, height = max(1, int(width)), max(1, int(height))
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for row in range(height):
        colour = _blend_hex(top_hex, bottom_hex, row / max(1, height - 1))
        rgb = tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))
        draw.line([(0, row), (width, row)], fill=(*rgb, 255))
    mask = Image.new("L", (width, height), 0)
    # A radius wider than half the tile is a PIL error, and a 4px-minimum block
    # is narrower than the 3px radius once scaled down.
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, width - 1, height - 1],
        radius=min(radius, (width - 1) // 2, (height - 1) // 2), fill=255)
    img.putalpha(mask)
    return img


def _hatch_tile(width, height, rgb, alpha, period):
    """135-degree hatching - the ribbon's idle gaps."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    value = (*rgb, int(round(alpha * 255)))
    for offset in range(-height, width + height, max(2, period)):
        draw.line([(offset, height), (offset + height, 0)], fill=value, width=1)
    return img


# Bright status color -> dark tinted background for badge-style rendering.
STATUS_TINTS = {
    GREEN: GREEN_TINT,
    RED: RED_TINT,
    AMBER: AMBER_TINT,
    ACCENT: ACCENT_TINT,
}


def _tint_for(color):
    return STATUS_TINTS.get(color, _blend_hex(color, BASE_BG, 0.78))


class AppWindow:
    def __init__(self, config, classifier, on_close_to_tray, offloader=None, gamesync=None):
        self.config = config
        self.classifier = classifier
        self.on_close_to_tray = on_close_to_tray
        self.offloader = offloader
        self.gamesync = gamesync

        self.obs = OBSClient(
            config["obs_host"], config["obs_port"], config["obs_password"],
            on_log=self._log,
        )
        self.monitor = Monitor(
            self.obs, classifier, config, on_log=self._log, on_state=self._on_state,
            on_notify=self._show_notification, on_connection_change=self._on_connection_change,
            offloader=offloader, on_record_prompt=self._on_record_prompt,
        )
        # Instant replay (7a). OBS holds the video; this arms the buffer and
        # files what comes out. The event hook is how the saved path arrives -
        # SaveReplayBuffer's own response doesn't carry it.
        self.replay = replay_mod.ReplayBuffer(
            self.obs, config, on_log=self._log,
            on_saved=self._on_replay_saved, on_state=self._on_replay_state)
        self.obs.on_event = self.replay.handle_event
        self._last_bitrate_mbps = None   # measured, for the RAM estimate

        # Thumbnails and clip lengths (7f). ffmpeg is optional: with it absent
        # every one of these stays empty and the Clips pane is unchanged.
        self._clip_thumb_cache = {}      # clip path -> [CTkImage x4]
        self._clip_durations = {}        # clip path -> seconds, from ffprobe
        self._clip_length_labels = {}
        self.thumbs = thumbs.ThumbWorker(
            config.get("recording_root", ""), on_log=self._log,
            is_busy=lambda: self._is_recording,
            on_done=self._on_thumbs_ready)
        # The v3 toast is a SINGLE SLOT: at most one window, ever, reused in
        # place. See _show_notification / _toast_replace.
        self._toast = None
        self._mini = None    # the 2k overlay; never exists while idle
        self.tray_icon = None  # set by main.py after the tray icon is built
        self._tray_game = None
        self._tray_idle = False
        self._tray_elapsed = ""       # mirrors the hero timer for the tray tooltip
        self._tray_icon_state = None  # last icon pushed, so we only swap on change
        self._is_recording = False  # tracked from OBS's own GetRecordStatus, not a client-side timestamp
        self._is_paused = False
        self._pause_reason = None   # "idle" | "session" | None — from monitor auto-pause
        self._offload_reachability = None  # last offloader diagnose() code
        # Defined before any builder runs: _set_hero_state consults it through
        # _hero_vis, and the dashboard's builder can reach it before
        # _build_views has finished assigning views.
        self._current_view = "dashboard"
        self._customising = False     # 6.8 edit mode; owns the handle strips and grid overlay
        self._drag_block = None
        self._poll_job = None         # the single _poll_obs_status timer, so it can be pulled forward
        self._transport_busy = False  # a start/stop/pause round-trip is in flight
        # Keeps PhotoImage refs alive - Tk garbage-collects them otherwise, and
        # the canvas item goes blank. Append-only was fine when the UI was built
        # once, but the dashboard and the ribbon are now rebuilt on every
        # relayout and every refresh, and each rebuild's images stayed pinned
        # here forever. The stress test found the end of that road: "Fail to
        # allocate bitmap" after 120 relayouts, i.e. Windows out of GDI handles.
        #
        # So anything that redraws itself opens a scope first (_image_scope),
        # and its previous generation is released when the next one starts.
        self._images = []
        self._image_sink = None
        self._glass_cache = {}  # (size, tint, alpha, radius, border...) -> PhotoImage
        self._dragging = False
        self._scanning = False
        self._connecting = False      # a connect attempt is in flight on a worker
        self._abort_connect = False   # set when monitoring is stopped mid-connect
        self._monitoring_on = False   # reflected in the sidebar toggle
        self._obs_connected = False   # reflected in the titlebar OBS readout
        self._obs_version = ""        # short form from GetVersion, e.g. "30.2"
        self._handshake_ms = None     # last Hello→Identified, for Settings footer
        self._video_label = ""        # "2560×1440 · 60 fps" from GetVideoSettings
        self._scene_name = ""         # current program scene from OBS
        self._hero_state = "disconnected"  # disconnected | watching | recording | paused
        self._bitrate_sample = None   # (duration_ms, bytes) from the previous poll
        self._current_game = None
        self._eq_bars = ()            # removed in 6.6 - see _build_hero's preview
        self._log_lines = []          # replayed into the dashboard activity panel
        self._log_pending = []        # buffered lines awaiting a coalesced flush
        self._log_flush_scheduled = False
        self._log_lock = threading.Lock()
        self.console = None           # set by _build_activity

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        # Turn OFF CustomTkinter's automatic DPI scaling and drive one uniform
        # factor ourselves instead. Left automatic, CTk multiplies the window
        # geometry + widgets by the monitor DPI (e.g. 1.5x at 150%) while the
        # raw tk.Canvas art stays at base size - everything misaligns ("wonky").
        # Here we compute the same factor and apply it consistently across BOTH
        # the CTk widgets (set_widget_scaling) and the canvas art (ScaledCanvas
        # + scaled image generation), so the whole design scales as one piece.
        # main.py marks the process per-monitor DPI-aware, so the result is
        # crisp at true device pixels rather than bitmap-stretched.
        ctk.deactivate_automatic_dpi_awareness()
        ctk.set_window_scaling(1.0)

        self.root = ctk.CTk()
        # Tk reports exceptions raised inside callbacks (timers, bindings, the
        # after() handlers everything here runs on) by printing to stderr - which
        # doesn't exist under pythonw, how this app actually runs day to day. So
        # a crash in any timer would be completely silent and invisible. Route
        # them into the app log instead.
        self.root.report_callback_exception = self._on_callback_exception
        self.root.title("Nebula")
        self.root.update_idletasks()
        self.scale = _compute_ui_scale(self.root)
        # Pin Tk's font scaling to the 96-DPI baseline (1.333 px/point). Tk
        # otherwise renders point-sized fonts at monitor-DPI/72 (e.g. 2.0 on a
        # 144-DPI/150% screen), which double-scales every font on top of our
        # own UI scale and makes text (and notifications) render far too large.
        # With this fixed, point fonts render consistently and self.scale is the
        # ONLY thing that sizes them - so text scales in lockstep with the
        # layout on every monitor.
        self.root.tk.call("tk", "scaling", 96.0 / 72.0)
        # Resolve the v3 type stacks against the families Tk can actually see.
        # "Segoe UI Variable" is three optical-size families, not one, and Tk
        # truncates family names at 31 chars - so the names have to be probed,
        # not assumed. Cascadia Mono may not be installed at all; the numeric
        # face falls back to Consolas so the timer keeps its tabular figures.
        dv.resolve_fonts(tkfont.families())
        # Root bg matched to the nebula's base tone: embedded CTk widgets
        # draw their rounded corners against their parent's color, so the
        # closer this is to the backdrop, the less their corners "fringe".
        self.root.configure(fg_color=BASE_BG)
        self.root.geometry(f"{self._S(WIDTH)}x{self._S(HEIGHT)}")
        # Apply CTk's widget scaling only AFTER the real geometry is set. CTk
        # pins minsize/maxsize to the window's current size whenever the scale
        # changes, so scaling while the window is still at CTk's default 600x500
        # would clamp it there and our larger geometry could never take effect.
        ctk.set_widget_scaling(self.scale)
        self.root.resizable(False, False)
        try:
            self.root.iconbitmap(ICON_PATH)  # taskbar icon - never set before, was falling back to Tk's default
        except Exception:
            pass
        # iconphoto (unlike iconbitmap) takes an in-memory image, so the
        # taskbar/Alt-Tab icon can animate the same way the tray icon does -
        # no need to write per-frame .ico files to disk.
        self._taskbar_icon_frames = [to_photo(f) for f in generate_animation_frames(size=32, n_frames=24)]
        self._taskbar_icon_index = 0
        self._animate_taskbar_icon()
        # Fully custom chrome: no native title bar. Since this app's whole
        # interaction model is already tray-based (hide/show, not taskbar
        # minimize-restore), the custom minimize/close buttons just reuse
        # that same hide-to-tray behavior rather than fighting Windows over
        # what overrideredirect + iconify should do together.
        self.root.overrideredirect(True)
        apply_rounded_corners(self.root)

        # ---- backdrop ----
        # The v3 "living background": three blurred aurora blobs, two star
        # layers and a vignette - generated ONCE here from a seed drawn at
        # launch, so no two sessions look alike (which is what the spec actually
        # requires) without a repaint loop, which on this window would cost a
        # full composite per frame. See CURSOR-HANDOFF.md 2.1.
        #
        # It also replaces v2's three separate layers (nebula image + a drifting
        # accent bloom + canvas star ovals) with one image. The bloom in
        # particular was the one layer NOT captured by self._composite, so every
        # unit of its alpha was a unit of mismatch around embedded widgets'
        # rounded corners; baking it in removes that error entirely.
        #
        # Two surfaces come back. `nebula` is the full stack and is what the
        # canvas paints; `aurora` is the same thing without the star dust, and
        # is what every panel is composited over. 6.1 calls stars appearing
        # inside the rail and over the cards the single biggest defect of the
        # last build, while still requiring the chrome to be translucent enough
        # for the aurora to read through it - and both are true at once only if
        # the chrome sits on a surface carrying the wash but not the specks.
        self.nebula, self.aurora = generate_backdrop_v3(
            self._S(WIDTH), self._S(HEIGHT))
        self.bg = ScaledCanvas(
            tk.Canvas(self.root, width=self._S(WIDTH), height=self._S(HEIGHT),
                      highlightthickness=0, bd=0),
            self.scale,
        )
        self.bg.pack(fill="both", expand=True)

        bg_photo = to_photo(self.nebula)
        self._keep_image(bg_photo)
        self._backdrop_id = self.bg.create_image(0, 0, anchor="nw", image=bg_photo)

        # Truth source for widget corner-blending. An embedded CTk widget paints
        # the area its rounded corners cut away with a single flat bg_color, so
        # that colour has to match the real pixels behind it or you get a square
        # fringe inside the rounded panel. Approximating it (nebula tint + alpha)
        # broke once the glass tiles gained their sheen gradient. Instead keep a
        # real composite - the backdrop exactly as it sits behind the window,
        # with each glass panel pasted in as it's drawn - and sample that.
        #
        # Seeded from the starless surface, so a widget that happens to land on
        # a star doesn't pick that star up as its corner-blend colour.
        self._composite = self.aurora.convert("RGB")

        self.bg.bind("<ButtonPress-1>", self._start_move)
        self.bg.bind("<B1-Motion>", self._on_move)

        # 6.8's keyboard parity: Space picks a module up, arrows move it, Space
        # drops it, Esc cancels. Bound on the root so the handles don't have to
        # be real focusable widgets - they are canvas items.
        self.root.bind("<Escape>", self._cancel_customise)
        for key in ("<space>", "<Up>", "<Down>", "<Left>", "<Right>"):
            self.root.bind(key, self._customise_key)

        self._build_titlebar()
        self._build_sidebar()
        self._build_topbar()
        self._build_views()

        self._poll_manual_review()
        self._poll_obs_status()
        self._poll_disk_stats()
        self._tick_ribbon()
        self._tick_forecast()
        self._register_hotkey()
        self._animate_taskbar_icon()

    @property
    def _visible(self):
        """Whether the window is actually on screen.

        Asked of Tk directly rather than tracked with a flag, because the window
        is hidden/shown from several places that don't all go through _hide()/
        show() - main.py withdraws it at startup, and the tray menu drives it
        too. winfo_viewable() is always right by construction."""
        try:
            return bool(self.root.winfo_viewable())
        except Exception:
            return False

    def _S(self, v):
        """Scale a base design-unit value to physical pixels by the UI scale."""
        return int(round(v * self.scale))

    def _on_callback_exception(self, exc_type, exc_value, exc_tb):
        """Tk's callback-error hook. Deliberately does NOT touch the console
        widget or any other UI - if the UI is what just failed, doing so would
        recurse. Writes straight to the log file, which works under pythonw."""
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            log_to_file("[Error] Unhandled exception in a UI callback:\n" + text)
        except Exception:
            pass
        try:
            print(text)
        except Exception:
            pass

    # ---- why the backdrop no longer animates -------------------------------
    # It used to drift the nebula, wander + breathe the violet bloom, and twinkle
    # the stars on an ~12fps timer. Measured on a mapped 1770x1140 window, that
    # was catastrophic: p50 frame pacing 110ms (~9fps) with a core pegged at 95%.
    #
    # The cost is NOT the drawing. Attribution runs showed it is flat regardless
    # of what changes: moving the full-window nebula image, swapping the 690px
    # glow, or recolouring a single 2px star all cost the same ~100ms, and
    # halving the canvas contents (141 items vs 187) barely moved it. That
    # signature means the expense is a *window-level* composite - any canvas
    # change makes DWM recomposite the whole layered, rounded-corner window - so
    # it scales with window size, not with damage or item count. The Aurora
    # redesign grew the window 1.6x in area, which is why this only bit now.
    #
    # Frequency is therefore the only lever, so the decorative animation is gone.
    # What remains mutates the canvas at most once a second, and only while
    # something is actually happening (the recording timer). The tray icon still
    # animates - it's a separate icon surface and never touches this window.
    # Don't reintroduce a repaint-per-frame timer here; measure first if tempted.

    # ---- glass panel helper ----
    # x/y/w/h/radius are base design units; the placement coordinate is scaled
    # by the ScaledCanvas proxy, so only the generated tile image itself needs
    # to be rendered at the scaled pixel size here to stay crisp.
    def _plate(self, x, y, w, h, tile, radius, source=None):
        """Flatten a glass tile onto the starless surface at (x, y).

        6.1 puts the whole background stack at z-index 0, "never inside
        [the chrome], never over it", and in the same breath keeps the chrome
        translucent so the aurora reads through. Both hold at once only if what
        shows through a card is the *aurora* surface rather than the painted
        one: a broad wash survives glass and reads as depth, a 1.9px star at
        .85 alpha punches through as a speck of dirt sitting on the card.

        So the tile is composited over `self._composite`, which starts from the
        starless render and accumulates every panel drawn so far - that second
        property is what makes a card inside a card (6.2's shell and core) come
        out right instead of erasing its own shell. Outside the rounded rect
        the plate stays transparent, so the corners still show the real
        backdrop, stars and all.

        `source` names what to flatten onto. It defaults to the accumulating
        composite, which is what a fresh panel wants. A *re*-generated panel
        passes the pristine shell instead: the composite already holds the
        previous version of that same panel, so compositing onto it would
        stack tint on tint and the hero card would darken a step on every
        state change.
        """
        source = self._composite if source is None else source
        sx, sy, sw, sh = self._S(x), self._S(y), self._S(w), self._S(h)
        base = source.crop((sx, sy, sx + sw, sy + sh)).convert("RGBA")
        base.alpha_composite(tile)
        mask = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, sw - 1, sh - 1], radius=self._S(radius), fill=255)
        base.putalpha(mask)
        return base

    def _glass(self, x, y, w, h, tint=CARD_TINT, radius=18, tint_alpha=150, border_hex=None, border_alpha=55):
        tile = make_glass_tile(
            self._S(w), self._S(h), tint, tint_alpha=tint_alpha, radius=self._S(radius),
            border_hex=border_hex or CARD_BORDER, border_alpha=border_alpha,
        )
        plate = self._plate(x, y, w, h, tile, radius)
        # Keep the sample source true: any widget placed on this panel afterwards
        # reads its bg_color from the composite, sheen and all.
        self._composite.paste(plate, (self._S(x), self._S(y)), plate)
        photo = to_photo(plate)
        self._keep_image(photo)
        return self.bg.create_image(x, y, anchor="nw", image=photo)

    def _card(self, x, y, w, h, kind="panel", core_tint=CARD_CORE,
              core_alpha=None, border_hex=None, border_alpha=None):
        """A card, which is always two layers (6.2).

        "A flat single-border card is a bug. Each card is a tinted outer shell
        with 4-6px of padding wrapping a darker inner core, and the inner
        radius equals the outer radius minus that padding."

        Every radius comes out of dv.CARD_LAYERS rather than being chosen at
        the call site, which is how the stat tiles ended up as a 12px shell
        around an 8px core when the spec asks for 16 around 12. Controls and
        fields are the one exception and stay single-layer - those call _glass
        directly.

        Returns (shell_item, core_item, (x, y, w, h) of the core) so callers
        lay their contents out against the core rather than the shell.
        """
        shell_r, pad, core_r = dv.CARD_LAYERS[kind]
        shell = self._glass(
            x, y, w, h, tint=dv.SHELL_HEX, radius=shell_r,
            tint_alpha=int(round(dv.SHELL_FILL_ALPHA * 255)),
            border_hex=border_hex or dv.SHELL_HEX,
            border_alpha=int(round(
                (dv.SHELL_BORDER_ALPHA if border_alpha is None else border_alpha) * 255)))
        inner = (x + pad, y + pad, w - pad * 2, h - pad * 2)
        core = self._glass(
            *inner, tint=core_tint, radius=core_r,
            tint_alpha=int(round((core_alpha or dv.CORE_ALPHA) * 255)),
            border_alpha=0)
        return shell, core, inner

    def _regen_hero_shell(self, x, y, w, h, border_hex, border_alpha):
        """Repaint the hero's outer shell with a state-tinted border.

        The fill stays 6.2's neutral rgba(245,243,255,.035); only the border
        carries the state hue. That is what 2f-2h mean by "accent tint" and
        "ember tint" - the card doesn't change colour, its edge does.
        """
        self._regen_glass(
            self._status_card_item, x, y, w, h,
            radius=dv.CARD_LAYERS["hero"][0], tint=dv.SHELL_HEX,
            tint_alpha=int(round(dv.SHELL_FILL_ALPHA * 255)),
            border_hex=border_hex, border_alpha=border_alpha)

    def _regen_glass(self, item_id, x, y, w, h, tint=CARD_TINT, radius=18, tint_alpha=150, border_hex=None, border_alpha=55):
        """Swap an existing glass panel's image (e.g. for a brief highlight
        flash, or a hero state change) without creating a duplicate canvas item.

        Results are cached by their visual parameters. Regenerating the hero
        panel costs ~35ms, and it's re-rendered on every state change plus five
        times per flash - so a game switch used to stall the UI for ~200ms and
        leak a PhotoImage per frame. The set of distinct tiles is tiny and
        fixed, so caching makes every repeat instant and bounds the memory.

        The key carries (x, y) now that a plate is flattened onto whatever sits
        behind it - the same tile at two positions is two different images."""
        key = (self._S(x), self._S(y), self._S(w), self._S(h), tint, tint_alpha,
               self._S(radius), border_hex or CARD_BORDER, border_alpha)
        photo = self._glass_cache.get(key)
        if photo is None:
            tile = make_glass_tile(
                key[2], key[3], tint, tint_alpha=tint_alpha, radius=key[6],
                border_hex=key[7], border_alpha=border_alpha,
            )
            photo = to_photo(self._plate(
                x, y, w, h, tile, radius,
                source=getattr(self, "_base_composite", self._composite)))
            self._glass_cache[key] = photo
        self.bg.itemconfigure(item_id, image=photo)

    def _bg_at(self, x, y, glass_tint=None, glass_alpha=0):
        """The real composited backdrop colour at a point. Embedded CTk widgets
        paint the area their rounded corners cut away with one flat bg_color, so
        it has to match what's genuinely behind them or the cut-away shows up as
        a square fringe inside the rounded panel.

        Read straight from `self._composite` (nebula + every glass panel drawn so
        far, including its sheen gradient). The old `glass_tint`/`glass_alpha`
        approximation is kept in the signature for call-site compatibility but is
        no longer needed - the composite already contains the panel."""
        comp_w, comp_h = self._composite.size
        px = self._composite.getpixel((
            int(min(max(self._S(x), 0), comp_w - 1)),
            int(min(max(self._S(y), 0), comp_h - 1)),
        ))
        return "#%02x%02x%02x" % px[:3]

    # ---- layout ----
    def _make_circle_button(self, cx, cy, radius, base_color, hover_color, symbol, command,
                            glyph_color=FAINT, hover_glyph=TEXT, font=None):
        """A genuinely circular button drawn straight on the canvas - the
        embedded CTkButton version left a visible square bounding box behind
        its rounded shape (same underlying issue as the "transparent frame"
        bug: a native widget's non-drawn corners don't blend with canvas art
        beneath them). A canvas oval has no such box - it's just a filled
        circle sitting on the backdrop."""
        circle_id = self.bg.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius, fill=base_color, outline="",
        )
        text_id = self.bg.create_text(cx, cy, text=symbol, fill=glyph_color,
                                      font=font or dv.type_font("meta"))

        def on_enter(_event):
            self.bg.itemconfigure(circle_id, fill=hover_color)
            self.bg.itemconfigure(text_id, fill=hover_glyph)

        def on_leave(_event):
            self.bg.itemconfigure(circle_id, fill=base_color)
            self.bg.itemconfigure(text_id, fill=glyph_color)

        def on_click(_event):
            command()

        for item in (circle_id, text_id):
            self.bg.tag_bind(item, "<Enter>", on_enter)
            self.bg.tag_bind(item, "<Leave>", on_leave)
            self.bg.tag_bind(item, "<Button-1>", on_click)

    # ---- brand mark ----
    def _draw_logo(self, cx, cy, size):
        """The Nebula mark: a tilted amber orbit ring around a violet sparkle.

        Rendered via icon_art.render_frame - the exact artwork already used for
        the tray and taskbar icons - rather than drawn with canvas primitives.
        A tk oval can't be rotated, so the canvas version lost the ring's tilt,
        which is the most recognisable part of the mark (and the design's SVG
        applies a -22 degree rotation to it). Going through icon_art also gets
        supersampled antialiasing and keeps every instance of the logo
        identical."""
        px = self._S(size)
        photo = to_photo(render_frame(size=px))
        self._keep_image(photo)
        self.bg.create_image(cx - size / 2, cy - size / 2, anchor="nw", image=photo)

    # ---- left nav rail (frame 2a) ----
    # The v3 rail hangs *below* the full-width titlebar rather than running the
    # whole window height, and its foot carries the storage card - the OBS
    # connection readout and the monitoring toggle both moved up into the
    # titlebar. Rail metrics: w 232, pad 16/12, item h 38, gap 3.
    def _build_sidebar(self):
        # Same as the titlebar: the rail is a .72 panel so the background stack
        # stays behind the chrome rather than showing up as specks inside it.
        self._glass(0, CONTENT_Y0, SIDEBAR_W, HEIGHT - CONTENT_Y0,
                    tint=dv.GROUND, radius=0, tint_alpha=dv.CHROME_ALPHA,
                    border_alpha=0)

        # Faint divider between rail and content. A hairline, never a solid
        # grey, and it fades at both ends like every other rule in the system.
        self._fading_rule(SIDEBAR_W, CONTENT_Y0, HEIGHT - CONTENT_Y0, vertical=True)

        # Section eyebrow.
        self.bg.create_text(dv.RAIL_PAD_X, CONTENT_Y0 + 22, anchor="w",
                            text=self._track("Session"), fill=FAINT,
                            font=dv.type_font("eyebrow"))

        nav = [
            ("dashboard", "Dashboard", None),
            ("clips", "Clips", None),
            ("games", "Games", self._game_count()),
            ("macropad", "Macropad", None),
            ("settings", "Settings", None),
        ]
        self._nav = {}
        y = CONTENT_Y0 + 38
        for view, label, badge in nav:
            self._nav[view] = self._nav_item(
                dv.RAIL_PAD_Y, y, SIDEBAR_W - dv.RAIL_PAD_Y * 2, dv.RAIL_ITEM_H,
                dv.ICONS[view], label, view, badge)
            y += dv.RAIL_ITEM_H + dv.RAIL_ITEM_GAP

        # ---- storage card at the foot of the rail ----
        self._build_sidebar_status()

    @staticmethod
    def _track(text):
        """Poor man's letter-spacing for eyebrow labels.

        The spec gives eyebrows 0.22em tracking. Tk has no letter-spacing at
        all, so the only way to express it is to space the characters out.
        Word gaps get widened too, otherwise a tracked-out two-word label reads
        as one run. Applied to eyebrows only - the one place the design leans
        on it.
        """
        return "   ".join(" ".join(word) for word in text.upper().split())

    def _fading_rule(self, a, b, length, vertical=False, fade=None):
        """A 1px rule that fades to nothing at both ends.

        "Rules and dividers fade at both ends over 32-48px. No hard-stopped 1px
        greys." A canvas line can't have a gradient, so this is a 1px PIL strip
        with an alpha ramp, drawn as an image.
        """
        fade = fade or dv.RULE_FADE[0]
        span = max(1, int(length))
        strip = Image.new("RGBA", (span, 1), (0, 0, 0, 0))
        px = strip.load()
        base_alpha = int(round(dv.HAIRLINE_ALPHA[1] * 255))
        for i in range(span):
            edge = min(i, span - 1 - i)
            alpha = base_alpha if edge >= fade else int(base_alpha * (edge / float(fade)))
            px[i, 0] = (*dv.HAIRLINE_RGB, alpha)
        if vertical:
            strip = strip.rotate(-90, expand=True)
        strip = strip.resize(
            (self._S(1), self._S(span)) if vertical else (self._S(span), self._S(1)),
            Image.NEAREST)
        photo = to_photo(strip)
        self._keep_image(photo)
        return self.bg.create_image(a, b, anchor="nw", image=photo)

    def _game_count(self):
        """How many distinct games the classifier knows about - shown as the
        Games nav badge. Counts display names, not executables, since one game
        can register several exes."""
        try:
            games = self.classifier._data.get("games", {})
            names = {
                (v.get("display_name") or k) if isinstance(v, dict) else k
                for k, v in games.items()
            }
            return str(len(names)) if names else None
        except Exception:
            return None

    def _nav_item(self, x, y, w, h, glyph, label, view, badge):
        """One nav-rail destination. The active highlight is drawn up front and
        toggled by visibility, so switching views never has to re-render it."""
        cy = y + h / 2
        tile = self._glass(x, y, w, h, tint=ACCENT, radius=dv.RADIUS_CONTROL, tint_alpha=36,
                           border_hex=ACCENT, border_alpha=0)
        bar = self.bg.create_rectangle(x, y + 9, x + 3, y + h - 9,
                                       fill=ACCENT, outline="")
        icon = self.bg.create_text(x + 18, cy, anchor="w", text=ICON_GLYPHS[glyph],
                                   fill=MUTED, font=(ICON_FONT, -16))
        text = self.bg.create_text(x + 42, cy, anchor="w", text=label,
                                   fill=MUTED, font=dv.type_font("body"))
        if badge:
            bx = x + w - 36
            self._glass(bx, cy - 9, 28, 18, tint=ACCENT, radius=7, tint_alpha=40,
                        border_hex=ACCENT, border_alpha=0)
            self.bg.create_text(bx + 14, cy, text=badge, fill=ACCENT_LIGHT,
                                font=dv.font(10, 500))

        parts = {"tile": tile, "bar": bar, "icon": icon, "text": text}
        hit = self.bg.create_rectangle(x, y, x + w, y + h, fill="", outline="")
        for item in (hit, icon, text):
            self.bg.tag_bind(item, "<Button-1>",
                             lambda _e, v=view: self._show_view(v))
            self.bg.tag_bind(item, "<Enter>",
                             lambda _e, p=parts: self._nav_hover(p, True))
            self.bg.tag_bind(item, "<Leave>",
                             lambda _e, p=parts: self._nav_hover(p, False))
        self._set_nav_active(parts, False)
        return parts

    def _set_nav_active(self, parts, active):
        parts["active"] = active
        state = "normal" if active else "hidden"
        self.bg.itemconfigure(parts["tile"], state=state)
        self.bg.itemconfigure(parts["bar"], state=state)
        self.bg.itemconfigure(parts["icon"], fill=ACCENT_LIGHT if active else MUTED)
        self.bg.itemconfigure(
            parts["text"], fill=NAV_ACTIVE_TEXT if active else MUTED,
            font=dv.font(13, 500) if active else dv.type_font("body"))

    def _nav_hover(self, parts, hovering):
        if parts.get("active"):
            return
        self.bg.itemconfigure(parts["text"], fill=TEXT_SOFT if hovering else MUTED)
        self.bg.itemconfigure(parts["icon"], fill=TEXT_SOFT if hovering else MUTED)
        self.bg.configure(cursor="hand2" if hovering else "")

    def _build_sidebar_status(self):
        """The storage card at the foot of the rail (frame 2a).

        The OBS connection readout and the monitoring toggle used to live here;
        in v3 both moved up into the full-width titlebar, and the rail foot
        carries the recording root, a fill bar and the free/total figure. Every
        number in it is real - see _apply_disk_stats. Until the first disk poll
        returns, the bar and figure are simply absent rather than showing zeros.
        """
        # 7c turned this from a percentage bar into a forecast, which needs a
        # fourth line for the "not enough history yet" note. Sized and placed
        # so the card ends exactly on the content margin rather than hanging
        # off the bottom of the window, which it did once the note was added.
        cx, cw = dv.RAIL_PAD_Y, SIDEBAR_W - dv.RAIL_PAD_Y * 2
        card_h = 96
        oy = HEIGHT - MARGIN - card_h
        self._card(cx, oy, cw, card_h, kind="tile")

        self.bg.create_text(cx + 14, oy + 18, anchor="w",
                            text=ICON_GLYPHS[dv.ICONS["storage"]],
                            fill=ACCENT_LIGHT, font=(ICON_FONT, -13))
        root_dir = self.config.get("recording_root", "") or "not set"
        self._store_path = self.bg.create_text(
            cx + 32, oy + 18, anchor="w", text=self._elide(root_dir, 22),
            fill=TEXT_SOFT, font=dv.type_font("meta"))
        self._store_pct = self.bg.create_text(
            cx + cw - 14, oy + 18, anchor="e", text="",
            fill=FAINT, font=dv.font(10.5, mono=True))

        # Fill bar. Drawn as two flat rectangles rather than a widget: it
        # changes at most once every five minutes, so it costs nothing.
        bar_y, bar_h = oy + 34, 3
        self.bg.create_rectangle(cx + 14, bar_y, cx + cw - 14, bar_y + bar_h,
                                 fill=dv.over(dv.TEXT, 0.08, dv.CARD_CORE), outline="")
        self._store_bar = self.bg.create_rectangle(
            cx + 14, bar_y, cx + 14, bar_y + bar_h, fill=ACCENT, outline="")
        self._store_bar_rect = (cx + 14, bar_y, cw - 28, bar_h)  # x0, y, full width, h

        self._store_free = self.bg.create_text(
            cx + 14, oy + 54, anchor="w", text="", fill=FAINT,
            font=dv.type_font("meta"))
        # 7c's "not enough history" line, empty once the forecast is real.
        self._store_note = self.bg.create_text(
            cx + 14, oy + 74, anchor="nw", text="", fill=dv.TEXT_EYEBROW,
            font=dv.type_font("meta"), width=cw - 28)

    # ---- themed interaction states (spec: "Motion & states") ----
    def _focus_ring(self, widget, resting_border=None):
        """"Focus ring 2px #8B7CF6, offset 2" - never the platform default.

        Tk has no :focus-visible, so keyboard focus is drawn as the widget's own
        border switching to the accent at the spec's width. Applied to anything
        focusable; the resting border is restored on the way out.

        The spec also asks for `offset 2`. A CTk widget's border is drawn on its
        own edge and has no outset, and these widgets are embedded in canvas
        windows, so there is nowhere to put a detached ring without laying a
        second widget behind every control. dv.FOCUS_RING_OFFSET is therefore
        recorded but not applied - the width and colour carry the affordance.
        """
        resting = resting_border if resting_border is not None else EDGE
        try:
            resting_w = int(widget.cget("border_width"))
        except Exception:
            resting_w = 1

        def enter(_event=None):
            try:
                widget.configure(border_color=ACCENT, border_width=dv.FOCUS_RING_W)
            except Exception:
                pass

        def leave(_event=None):
            try:
                widget.configure(border_color=resting, border_width=resting_w)
            except Exception:
                pass

        widget.bind("<FocusIn>", enter)
        widget.bind("<FocusOut>", leave)
        return widget

    @staticmethod
    def _disabled_color(color, bg=None):
        """"Disabled opacity .45" - composited, since a widget has no alpha."""
        return dv.over(color, dv.DISABLED_OPACITY, bg or dv.CARD_CORE)

    def _set_enabled(self, widget, enabled, text_color=MUTED):
        """Enable/disable with the spec's disabled treatment and no hover."""
        try:
            widget.configure(
                state="normal" if enabled else "disabled",
                text_color=text_color if enabled else self._disabled_color(text_color),
                hover=bool(enabled),
            )
        except Exception:
            pass

    def _text_w(self, text, font):
        """Width of `text` in **base design units** for a v3 font tuple.

        Measured with the unscaled font, which is what the drawing code works
        in - ScaledCanvas multiplies at draw time. Font objects are cached
        because constructing one per call is surprisingly expensive.
        """
        cache = getattr(self, "_font_cache", None)
        if cache is None:
            cache = self._font_cache = {}
        key = tuple(font)
        obj = cache.get(key)
        if obj is None:
            obj = cache[key] = tkfont.Font(root=self.root, family=font[0], size=font[1])
        return obj.measure(text)

    @staticmethod
    def _elide(text, limit):
        """Middle-elide a path so both the drive and the leaf stay readable."""
        if len(text) <= limit:
            return text
        keep = (limit - 1) // 2
        return text[:keep] + "…" + text[-keep:]

    # ---- full-width titlebar (frame 2a) ----
    def _build_titlebar(self):
        """h46, pad 18 left / 8 right, spanning the whole window.

        Left: the mark, the wordmark, the version badge, and the monitoring
        toggle with its bound key as a keycap. Right: the OBS connection
        readout, then minimise and close - which per the spec BOTH hide to
        tray; Quit exists only in the tray menu.
        """
        # The bar is a panel, not bare backdrop. Without it the star dust sat
        # inside the chrome - 6.1's single biggest defect - because there was
        # nothing between the wordmark and the sky. ".72 for the rail and
        # titlebar" keeps the aurora reading through it.
        self._glass(0, 0, WIDTH, TITLEBAR_HEIGHT, tint=dv.GROUND, radius=0,
                    tint_alpha=dv.CHROME_ALPHA, border_alpha=0)

        cy = TITLEBAR_HEIGHT / 2
        pad_l, pad_r = dv.TITLEBAR_PAD_LEFT, dv.TITLEBAR_PAD_RIGHT

        self._draw_logo(pad_l + 10, cy, 21)
        self.bg.create_text(pad_l + 27, cy, anchor="w", text="Nebula",
                            fill=TEXT, font=dv.font(14, 500))

        # Version badge - release number, plus +N when this source tree is
        # ahead of the last tag (display_version). Width follows the label.
        from .version import display_version, version_info
        ver = display_version()
        info = version_info()
        bx = pad_l + 27 + 48
        badge_w = max(34, 12 + len(ver) * 6.2)
        self._glass(bx, cy - 8, badge_w, 16, tint=ACCENT, radius=5, tint_alpha=34,
                    border_hex=ACCENT, border_alpha=0)
        self.bg.create_text(bx + badge_w / 2, cy, text=ver, fill=ACCENT_LIGHT,
                            font=dv.font(9.5, mono=True))
        # Detail (git describe) is only for humans debugging a source tree.
        if info.get("git"):
            self._log("[App] %s" % info["detail"])

        # Monitoring toggle - same action as the hotkey.
        mx = bx + badge_w + 16
        self._mon_icon = self.bg.create_text(
            mx, cy, anchor="w", text=ICON_GLYPHS[dv.ICONS["idle"]],
            fill=FAINT, font=(ICON_FONT, -13))
        self._mon_label = self.bg.create_text(
            mx + 19, cy, anchor="w", text="Monitoring off", fill=TEXT_SOFT,
            font=dv.type_font("meta"))
        binding = self.config.get("toggle_hotkey")
        if binding:
            self._draw_keycap(mx + 118, cy, binding.upper())
        hit = self.bg.create_rectangle(mx - 6, cy - 12, mx + 140, cy + 12,
                                       fill="", outline="")
        for item in (hit, self._mon_icon, self._mon_label):
            self.bg.tag_bind(item, "<Button-1>", lambda _e: self._toggle_monitoring())
            self.bg.tag_bind(item, "<Enter>", lambda _e: self.bg.configure(cursor="hand2"))
            self.bg.tag_bind(item, "<Leave>", lambda _e=None: self.bg.configure(cursor=""))

        # ---- right side: OBS connection, then the window controls ----
        # Hit target >= 30px (spec). Diameter 30 -> radius 15.
        self._make_circle_button(WIDTH - pad_r - 17, cy, 15, SURFACE, EMBER,
                                 ICON_GLYPHS["x"], self._hide, font=(ICON_FONT, -9))
        self._make_circle_button(WIDTH - pad_r - 53, cy, 15, SURFACE, SURFACE_HOVER,
                                 ICON_GLYPHS["minus"], self._hide, font=(ICON_FONT, -9))
        # There is no third window control. 6.5 lists the bar's contents as
        # exactly eight elements and says so twice: "The current build added a
        # globe icon, a Customise button and a third window control... Not in
        # the titlebar: Customise, globes, settings gears, maximise, help, or
        # anything else." Collapsing to the mini overlay moved to the dashboard
        # pane header, where pane-level actions belong.

        ox = WIDTH - pad_r - 84    # clears the two 30px circle buttons
        # Frame 2a: one readout `OBS 30.2 · localhost:4455`. Host:port stays
        # visible even while disconnected so you can see what we're aiming at.
        hostport = (f"{self.config.get('obs_host', 'localhost')}:"
                    f"{self.config.get('obs_port', 4455)}")
        self._obs_card_title = self.bg.create_text(
            ox, cy, anchor="e", text=f"OBS offline \u00b7 {hostport}",
            fill=MUTED, font=dv.type_font("meta"))
        # "dot 7px, one line" - a status dot, which is one of the two roles the
        # spec sanctions a Fill glyph for (ph-circle at 6-8px).
        self._obs_card_dot = self.bg.create_text(
            ox - 210, cy, anchor="e", text=ICON_GLYPHS["record"],
            fill=EMBER, font=(ICON_FONT, -7))

        # The rule under the titlebar, fading at both ends like every other.
        self._fading_rule(0, TITLEBAR_HEIGHT, WIDTH)

    # ---- content-column pane header (h62, pad-x 26 - frame 2a) ----
    def _build_topbar(self):
        x0 = SIDEBAR_W + dv.PANE_HEADER_PAD_X
        top = CONTENT_Y0
        self._pane_eyebrow = self.bg.create_text(
            x0, top + 22, anchor="w", text=self._track("Live session"),
            fill=FAINT, font=dv.type_font("eyebrow"))
        self._topbar_title = self.bg.create_text(
            x0, top + 42, anchor="w", text="Dashboard",
            fill=TEXT, font=dv.type_font("pane_title"))

        # Pane actions, right-aligned in the header.
        cy = top + 34
        # One label, remembered - the scanning animation and the finally-block
        # both restore it, and a button whose text silently changes after a scan
        # is its own small bug.
        self._rescan_label = "Rescan Steam"
        self.rescan_btn = ctk.CTkButton(
            self.root, text=self._rescan_label, command=self._rescan_steam,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(WIDTH - 150, cy), border_width=1, border_color=EDGE,
            corner_radius=dv.RADIUS_CONTROL, font=ctk.CTkFont(size=12),
        )
        self.bg.create_window(WIDTH - dv.PANE_HEADER_PAD_X - 118, cy - 15, anchor="nw",
                              window=self.rescan_btn, width=118, height=30)
        self.gamedata_btn = ctk.CTkButton(
            self.root, text="Open folder", command=self._open_recording_root,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(WIDTH - 270, cy), border_width=1, border_color=EDGE,
            corner_radius=dv.RADIUS_CONTROL, font=ctk.CTkFont(size=12),
        )
        self.bg.create_window(WIDTH - dv.PANE_HEADER_PAD_X - 244, cy - 15, anchor="nw",
                              window=self.gamedata_btn, width=114, height=30)
        self.customise_btn = ctk.CTkButton(
            self.root, text="Customise", command=self._toggle_customise,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(WIDTH - 390, cy), border_width=1, border_color=EDGE,
            corner_radius=dv.RADIUS_CONTROL, font=ctk.CTkFont(size=12),
        )
        self._customise_win = self.bg.create_window(
            WIDTH - dv.PANE_HEADER_PAD_X - 352, cy - 15, anchor="nw",
            window=self.customise_btn, width=100, height=30)

        # "Header swap: Done + Reset layout replace it in place." Reset shares
        # Customise's row and only appears while editing, so the header doesn't
        # grow a permanent button nobody needs.
        self.reset_btn = ctk.CTkButton(
            self.root, text="Reset layout", command=self._reset_dashboard,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(WIDTH - 620, cy), border_width=1, border_color=EDGE,
            corner_radius=dv.RADIUS_CONTROL, font=ctk.CTkFont(size=12),
        )
        self._reset_win = self.bg.create_window(
            WIDTH - dv.PANE_HEADER_PAD_X - 578, cy - 15, anchor="nw",
            window=self.reset_btn, width=108, height=30)
        self.bg.itemconfigure(self._reset_win, state="hidden")

        # Collapse to the mini overlay (2k). This was a third circle in the
        # titlebar, which 6.5 forbids - the bar is exactly eight elements. It
        # is a pane-level action, so it lives in the 62px pane header with the
        # rest of them. It refuses while idle rather than disappearing, because
        # a refusal that says why beats a control that silently isn't there.
        self.mini_btn = ctk.CTkButton(
            self.root, text="Mini overlay", command=self.show_mini,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(WIDTH - 500, cy), border_width=1, border_color=EDGE,
            corner_radius=dv.RADIUS_CONTROL, font=ctk.CTkFont(size=12),
        )
        self._mini_win = self.bg.create_window(
            WIDTH - dv.PANE_HEADER_PAD_X - 464, cy - 15, anchor="nw",
            window=self.mini_btn, width=104, height=30)

    def _draw_keycap(self, cx, cy, label):
        """A small rounded keycap chip on the canvas - the sampled-corner
        glass technique, drawn as a tinted rounded tile with the key text."""
        pad_x = 5 + len(label) * 4
        w, h = pad_x * 2, 18
        tile = make_glass_tile(self._S(w), self._S(h), SURFACE, tint_alpha=235,
                               radius=self._S(5), border_hex=EDGE, border_alpha=200)
        photo = to_photo(tile)
        self._keep_image(photo)
        self.bg.create_image(cx - w / 2, cy - h / 2, anchor="nw", image=photo)
        self.bg.create_text(cx, cy, text=label, fill=MUTED, font=dv.font(9.5, 500))

    def _start_move(self, event):
        # event.y is in real (scaled) canvas pixels; TITLEBAR_HEIGHT is a base
        # design unit, so compare against the scaled titlebar height.
        if event.y > self._S(TITLEBAR_HEIGHT):
            self._dragging = False
            return
        self._dragging = True
        self._drag_offset_x = event.x_root - self.root.winfo_x()
        self._drag_offset_y = event.y_root - self.root.winfo_y()

    def _on_move(self, event):
        if not self._dragging:
            return
        x = event.x_root - self._drag_offset_x
        y = event.y_root - self._drag_offset_y
        self.root.geometry(f"+{x}+{y}")

    # ---- view switching ----
    # Every view's canvas items (including the embedded-widget windows, which
    # are canvas items too) get tagged "view_<name>", so showing/hiding a whole
    # view is one itemconfigure on the tag. Items are identified by diffing
    # find_all() around each builder, which means the builders stay ordinary
    # drawing code with no bookkeeping of their own.
    def _build_views(self):
        # _bg_at() samples self._composite so embedded widgets can match the
        # pixels behind them. Views share the same screen area, so each one must
        # sample the shell *without* the other views paintedn on top - rewind to
        # a pristine snapshot before building each.
        self._base_composite = self._composite.copy()
        builders = [
            ("dashboard", self._build_dashboard),
            ("clips", self._build_clips),
            ("games", self._build_games),
            ("macropad", self._build_macropad),
            ("settings", self._build_settings),
        ]
        for name, builder in builders:
            self._composite = self._base_composite.copy()
            before = set(self.bg.find_all())
            builder()
            for item in set(self.bg.find_all()) - before:
                self.bg.addtag_withtag(f"view_{name}", item)
        self._composite = self._base_composite
        self._views = [name for name, _ in builders]
        self._current_view = None      # force the first _show_view to do its work
        self._show_view("dashboard")

    def _show_view(self, name):
        if name == self._current_view:
            return
        for view in self._views:
            self.bg.itemconfigure(f"view_{view}",
                                  state="normal" if view == name else "hidden")
        self._current_view = name
        self.bg.itemconfigure(self._topbar_title, text=VIEW_TITLES[name])
        # Customise only means anything on the dashboard; leaving it on while
        # navigating away would strand the grips over another view.
        for win in (self._customise_win, self._mini_win):
            self.bg.itemconfigure(win, state="normal" if name == "dashboard" else "hidden")
        if name != "dashboard":
            self.bg.itemconfigure(self._reset_win, state="hidden")
        if name != "dashboard" and getattr(self, "_customising", False):
            self._set_customise(False)
        for nav_name, parts in self._nav.items():
            self._set_nav_active(parts, nav_name == name)
        if name == "dashboard":
            # Showing the whole tag un-hides items the dashboard deliberately
            # keeps hidden (the timer/size readout and Pause button when nothing
            # is recording), so re-apply their own visibility rules on top. The
            # edit chrome no longer needs re-applying: it is built by
            # _render_dashboard only when editing, rather than built always and
            # hidden.
            self._set_hero_state(self._hero_state)
        elif name == "clips":
            self._refresh_clips()
        elif name == "games":
            self._refresh_games()

    # ---- content column: geometry ----
    # The main column lives to the right of the nav rail. Everything here is in
    # base design units; x0 is the left gutter of the content area.
    def _content_x0(self):
        return SIDEBAR_W + MARGIN

    def _content_y0(self):
        """Top of the pane content: below the full-width titlebar AND the
        pane header. v2 had a single 62px strip; v3 has 46 + 62."""
        return CONTENT_Y0 + TOPBAR_HEIGHT

    # ---- dashboard tile grid ----
    # The dashboard is a 2-column grid. Its layout is an ordered list of
    # {"name", "span"} (span 2 = full width, 1 = half); consecutive half blocks
    # pair left-to-right into one row. Changing the layout REBUILDS the affected
    # blocks at their new rects (they carry embedded widgets sized to their
    # width, so they can't just be slid around like the old full-width-only
    # reorder could). Heights are fixed per (block, span), so placement is pure
    # arithmetic - see _compute_grid.
    def _build_dashboard(self):
        self._grid_layout = self._saved_grid()
        self._render_dashboard()

    def _saved_grid(self):
        """The layout from config, defended against a hand-edited or older file.

        6.8: "Persisted as dashboard_layout[] - {id, span}", where span is a
        column count out of twelve. Two older shapes exist on disk here - a
        bare list of names, and {name, span} where span was 1 or 2 - so both
        are migrated rather than discarded. Unknown ids are dropped and any
        module missing from the file is appended full width, so no file, however
        mangled, can lose a panel.
        """
        legacy_span = {1: 6, 2: 12}

        def normalise(items):
            cleaned, seen = [], set()
            for it in items:
                if isinstance(it, str):
                    key, span = it, dv.GRID_COLS
                else:
                    it = it or {}
                    key = it.get("id") or it.get("name")
                    span = it.get("span", dv.GRID_COLS)
                    span = legacy_span.get(span, span)
                if key not in BLOCK_HEIGHTS or key in seen:
                    continue
                if span not in dv.SPANS:
                    span = dv.GRID_COLS
                cleaned.append({"id": key, "span": dv.GRID_COLS if key == "hero" else span})
                seen.add(key)
            for b in DEFAULT_BLOCKS:
                if b not in seen:
                    cleaned.append({"id": b, "span": dv.GRID_COLS})
            return cleaned

        for key in ("dashboard_layout", "dashboard_grid"):
            saved = self.config.get(key)
            if isinstance(saved, list) and saved:
                return normalise(saved)
        return [dict(it) for it in DEFAULT_GRID]

    def _compute_grid(self, layout, editing=False):
        """Map an ordered layout onto the twelve-column grid.

        Modules are packed left to right until the next one won't fit, then the
        row breaks. That is what makes overlap impossible (6.8: "Overlap:
        impossible - grid reflows, never free position") - a position is never
        stored, only an order and a width, so there is nowhere for a module to
        land on top of another one.

        While editing, every module grows by the handle strip's height: the
        strip lives *inside* the module and "pushes content down" rather than
        being an overlay across the top of it, which is why the old edit chrome
        covered the content it was meant to be moving.
        """
        x0 = self._content_x0()
        cw = WIDTH - MARGIN - x0
        col_w = (cw - dv.GRID_GAP * (dv.GRID_COLS - 1)) / dv.GRID_COLS
        strip = dv.HANDLE_STRIP_H if editing else 0

        def width_of(span):
            return col_w * span + dv.GRID_GAP * (span - 1)

        rows, row, used = [], [], 0
        for item in layout:
            key = item["id"]
            span = dv.GRID_COLS if key == "hero" else item.get("span", dv.GRID_COLS)
            if used + span > dv.GRID_COLS:
                rows.append(row)
                row, used = [], 0
            row.append((key, span))
            used += span
        if row:
            rows.append(row)

        heights = [max(BLOCK_HEIGHTS[k][12 if s == 12 else 6] for k, s in r) + strip
                   for r in rows]

        # The window is a fixed 808px and the modules' natural heights can
        # exceed it - four modules do, and so do three once edit mode adds a
        # handle strip to each. Rather than letting the last one fall off the
        # bottom, rows give up height from the bottom upwards until it fits.
        # The bottom rows are the flexible ones (a log panel just shows fewer
        # lines); a module you cannot see at all is worse than a shorter one.
        available = (HEIGHT - MARGIN) - self._content_y0()
        floor = dv.HANDLE_STRIP_H + 40
        overflow = sum(heights) + BLOCK_GAP * max(0, len(rows) - 1) - available
        for i in range(len(heights) - 1, -1, -1):
            if overflow <= 0:
                break
            give = min(overflow, max(0, heights[i] - floor))
            heights[i] -= give
            overflow -= give

        rects = {}
        y = self._content_y0()
        for r, height in zip(rows, heights):
            x = x0
            for key, span in r:
                rects[key] = (x, y, width_of(span), height)
                x += width_of(span) + dv.GRID_GAP
            y += height + BLOCK_GAP
        return rects

    def _render_dashboard(self):
        self._dashboard_widgets = []
        editing = getattr(self, "_customising", False)
        rects = self._compute_grid(self._grid_layout, editing=editing)
        self._grid_rects = rects
        strip = dv.HANDLE_STRIP_H if editing else 0
        builders = {
            "hero": lambda r: self._build_hero(r[0], r[1] + strip, r[2]),
            "stats": lambda r: self._build_stats(r[0], r[1] + strip, r[2]),
            "replay": lambda r: self._build_replay(r[0], r[1] + strip, r[2],
                                                   r[3] - strip),
            "activity": lambda r: self._build_activity(r[0], r[1] + strip, r[2],
                                                       r[3] - strip),
        }
        for item in self._grid_layout:
            name = item["id"]
            if name not in rects:
                continue
            before = set(self.bg.find_all())
            builders[name](rects[name])
            for canvas_item in set(self.bg.find_all()) - before:
                self.bg.addtag_withtag(f"blk_{name}", canvas_item)
                self.bg.addtag_withtag(f"content_{name}", canvas_item)
        self._build_customise_controls(rects)

    def _relayout_grid(self, new_layout, persist=False):
        """Apply a new layout by tearing the dashboard down and rebuilding it at
        the new rects. Only ever runs on a user action (drag / width toggle), so
        the rebuild cost is irrelevant.

        `persist` is off for the intermediate states during an edit session -
        only Done writes config.json, so Esc really can put everything back.
        """
        for wdg in getattr(self, "_dashboard_widgets", []):
            try:
                wdg.destroy()
            except Exception:
                pass
        self._dashboard_widgets = []
        self.bg.delete("view_dashboard")  # blk_ items are a subset, gone too
        # Rebuild against a pristine shell snapshot so embedded widgets sample
        # the right backdrop (see _build_views).
        self._composite = self._base_composite.copy()
        self._grid_layout = [dict(it) for it in new_layout]
        before = set(self.bg.find_all())
        # The old dashboard's canvas items were just deleted, so its images can
        # go with them. Without this each relayout pinned another set of
        # bitmaps and Windows eventually refused to allocate more.
        with self._image_scope("dashboard"):
            self._render_dashboard()
        for item in set(self.bg.find_all()) - before:
            self.bg.addtag_withtag("view_dashboard", item)
        self._composite = self._base_composite
        if persist:
            self._persist_grid(self._grid_layout)
        self._set_hero_state(self._hero_state)
        # The hero's primary button is created disabled and enabled by the next
        # status poll, so a rebuild used to leave it dead for up to five
        # seconds. A relayout is a user action; don't make them wait for a
        # heartbeat to get their buttons back.
        if getattr(self, "_poll_job", None) is not None:
            self._poll_now()
        # Deliberately silent. This runs on every reflow during a drag, and
        # logging it there wrote 19 identical lines in 40 seconds - the log is
        # meant to be readable. The commit path logs once instead.

    def _persist_grid(self, layout):
        # 6.8: "Persisted as dashboard_layout[] - {id, span}".
        self.config["dashboard_layout"] = [dict(it) for it in layout]
        self.config.pop("dashboard_grid", None)   # retire the interim key
        from .config import save_config
        save_config(self.config)

    # ---- customise mode (6.8) ----
    # The rebuild the spec asked for. What was here before had every defect it
    # names: "Edit chrome is drawn as an overlay on top of each module instead
    # of inside it, so handle bars cover content and modules land on top of each
    # other. There is no grid, no placeholder, and no reflow."
    #
    # One deliberate deviation, for the reason that governs this whole UI:
    # "Origin slot collapses; siblings reflow over 260ms" is a 260ms animation
    # of many canvas items, and any canvas mutation costs a full window
    # composite here. Siblings snap into place on drop instead. The dragged
    # module itself does follow the cursor - that is one image moving, which is
    # the same cost the old build already paid - and it is pre-rendered rotated
    # at press time rather than re-rotated per frame.

    def _build_customise_controls(self, rects):
        """The handle strip inside each module, plus the grid overlay.

        The strip is drawn *within* the module's rect and the module's content
        was already laid out 26px lower (see _compute_grid), so it pushes
        content down rather than covering it.
        """
        self._grips = {}
        self._grid_overlay = []
        if not getattr(self, "_customising", False):
            return

        # "Grid overlay: 12 col, 1px accent @ .10, gap 16."
        x0 = self._content_x0()
        cw = WIDTH - MARGIN - x0
        col_w = (cw - dv.GRID_GAP * (dv.GRID_COLS - 1)) / dv.GRID_COLS
        overlay_colour = dv.over(ACCENT, dv.GRID_OVERLAY_ALPHA, dv.GROUND)
        for col in range(dv.GRID_COLS):
            cx = x0 + col * (col_w + dv.GRID_GAP)
            for edge in (cx, cx + col_w):
                self._grid_overlay.append(self.bg.create_line(
                    edge, self._content_y0(), edge, HEIGHT - MARGIN,
                    fill=overlay_colour, width=1))

        for item in self._grid_layout:
            name = item["id"]
            if name not in rects:
                continue
            x, y, w, _h = rects[name]
            strip = self._glass(x, y, w, dv.HANDLE_STRIP_H, tint=ACCENT, radius=8,
                                tint_alpha=70, border_hex=ACCENT, border_alpha=90)
            label = self.bg.create_text(
                x + 12, y + dv.HANDLE_STRIP_H / 2, anchor="w",
                text=f"{ICON_GLYPHS[dv.ICONS['scene']]}  {BLOCK_LABELS[name]}",
                fill=NAV_ACTIVE_TEXT, font=dv.font(11, 500))
            parts = {"strip": strip, "label": label}

            # "Grab target: the strip only - never the whole card."
            for grab in (strip, label):
                self.bg.tag_bind(grab, "<ButtonPress-1>",
                                 lambda e=None, n=name: self._grip_press(e, n))
                self.bg.tag_bind(grab, "<B1-Motion>", self._grip_drag)
                self.bg.tag_bind(grab, "<ButtonRelease-1>", self._grip_release)
                self.bg.tag_bind(grab, "<Enter>",
                                 lambda _e=None: self.bg.configure(cursor="fleur"))
                self.bg.tag_bind(grab, "<Leave>",
                                 lambda _e=None: self.bg.configure(cursor=""))

            # "The segmented control lives in the handle strip - never a
            # floating chip over the header. Three widths only."
            if name != "hero":       # the hero is full width, always
                seg_w, seg_h = 34, 18
                right = x + w - 8
                for i, span in enumerate(reversed(dv.SPANS)):
                    sx = right - (i + 1) * seg_w - i * 3
                    active = item.get("span") == span
                    seg = self._glass(sx, y + 4, seg_w, seg_h,
                                      tint=ACCENT if active else BASE_BG, radius=6,
                                      tint_alpha=150 if active else 120, border_alpha=0)
                    text = self.bg.create_text(
                        sx + seg_w / 2, y + dv.HANDLE_STRIP_H / 2,
                        text=dv.SPAN_LABELS[span],
                        fill=NAV_ACTIVE_TEXT if active else MUTED,
                        font=dv.font(10, 500))
                    for seg_item in (seg, text):
                        self.bg.tag_bind(
                            seg_item, "<Button-1>",
                            lambda _e=None, n=name, s=span: self._set_block_span(n, s))
                    parts[f"seg{span}"] = seg
                    parts[f"segtext{span}"] = text

            # Remove returns the module to the Add-module list; 6.8 is explicit
            # that it "is never destroyed".
            close = self.bg.create_text(
                x + w - (8 if name == "hero" else 128), y + dv.HANDLE_STRIP_H / 2,
                text=ICON_GLYPHS["x"], fill=MUTED, font=(ICON_FONT, -9), anchor="e")
            self.bg.tag_bind(close, "<Button-1>",
                             lambda _e=None, n=name: self._remove_module(n))
            parts["close"] = close

            for canvas_item in parts.values():
                self.bg.addtag_withtag(f"blk_{name}", canvas_item)
            self._grips[name] = parts

        self._dim_module_content()
        self._build_add_module_row(rects)

    def _dim_module_content(self):
        """"Content while editing: pointer-events:none · opacity .55".

        Canvas items have no alpha, so the content is covered by a scrim of the
        ground colour at 45% - the same thing the browser composites - which
        also swallows clicks aimed at anything under it. Embedded widgets sit
        above the canvas and can't be covered, so they are disabled instead.
        """
        for name, (x, y, w, h) in self._grid_rects.items():
            scrim = self._glass(
                x, y + dv.HANDLE_STRIP_H, w, h - dv.HANDLE_STRIP_H,
                tint=dv.GROUND, radius=dv.CARD_LAYERS["panel"][0],
                tint_alpha=int(round((1 - dv.EDIT_CONTENT_OPACITY) * 255)),
                border_alpha=0)
            self.bg.tag_bind(scrim, "<Button-1>", lambda _e: "break")
            self.bg.addtag_withtag(f"blk_{name}", scrim)
            self._grips.setdefault(name, {})["scrim"] = scrim
        # Embedded widgets sit above the canvas, so the scrim can't cover them.
        # Disable them (that is the pointer-events half) and dim their text to
        # the same .55 the scrim gives everything else, or the activity log
        # stays bright while the card behind it greys out.
        for widget in getattr(self, "_dashboard_widgets", []):
            try:
                widget.configure(state="disabled")
            except Exception:
                pass
            try:
                current = widget.cget("text_color")
                widget._nebula_text_color = current
                widget.configure(text_color=dv.over(
                    current if isinstance(current, str) else MUTED,
                    dv.EDIT_CONTENT_OPACITY, dv.PANEL))
            except Exception:
                pass

    def _build_add_module_row(self, rects):
        """Modules that have been removed, offered back (6.8's catalogue).

        The catalogue is whatever is registered minus whatever is on the
        dashboard. Today that is the three real modules; 7g adds replay, ribbon
        and storage to it, which is why this reads the registry rather than a
        hard-coded list.
        """
        placed = {it["id"] for it in self._grid_layout}
        missing = [b for b in DEFAULT_BLOCKS if b not in placed]
        if not missing:
            return
        bottom = max((r[1] + r[3] for r in rects.values()), default=self._content_y0())
        x = self._content_x0()
        y = bottom + BLOCK_GAP
        if y > HEIGHT - MARGIN - 34:
            return
        self.bg.addtag_withtag(
            "blk_addmodule",
            self.bg.create_text(x, y + 15, anchor="w", text=self._track("Add module"),
                                fill=FAINT, font=dv.type_font("eyebrow")))
        cx = x + 100
        for name in missing:
            label = BLOCK_LABELS[name]
            chip_w = 26 + self._text_w(label, dv.font(11, 500))
            chip = self._glass(cx, y, chip_w, 30, tint=ACCENT, radius=8,
                               tint_alpha=44, border_hex=ACCENT, border_alpha=70)
            text = self.bg.create_text(cx + chip_w / 2, y + 15, text=f"+  {label}",
                                       fill=ACCENT_LIGHT, font=dv.font(11, 500))
            for item in (chip, text):
                self.bg.tag_bind(item, "<Button-1>",
                                 lambda _e, n=name: self._add_module(n))
                self.bg.addtag_withtag("blk_addmodule", item)
            cx += chip_w + 10

    def _set_customise(self, on, commit=True):
        """Enter or leave edit mode.

        Leaving rebuilds the dashboard because the handle strips changed every
        module's height; that is a user action, so the rebuild cost doesn't
        matter. `commit=False` is Esc: restore the layout captured on entry.
        """
        was = getattr(self, "_customising", False)
        self._customising = on
        if on and not was:
            self._layout_before_edit = [dict(it) for it in self._grid_layout]
        if hasattr(self, "customise_btn"):
            self.customise_btn.configure(
                text="Done" if on else "Customise",
                text_color=ACCENT_LIGHT if on else MUTED)
        if hasattr(self, "reset_btn"):
            # "Header swap: Done + Reset layout replace it in place."
            self.bg.itemconfigure(self._reset_win, state="normal" if on else "hidden")
        if was == on:
            return
        layout = self._grid_layout
        if not on and not commit:
            layout = getattr(self, "_layout_before_edit", layout)
        self._relayout_grid(layout, persist=(not on and commit))

    def _toggle_customise(self):
        leaving = self._customising
        self._set_customise(not leaving)
        if leaving:
            order = " · ".join(
                f"{it['id']}:{dv.SPAN_LABELS[it['span']]}" for it in self._grid_layout)
            self._log(f"[Manual] Dashboard layout saved: {order}")

    def _cancel_customise(self, _event=None):
        """Esc. "Done commits · Esc reverts the session"."""
        if not getattr(self, "_customising", False):
            return
        if getattr(self, "_drag_block", None):
            self._grip_cancel()
            return
        self._set_customise(False, commit=False)
        self._log("[Manual] Dashboard changes discarded.")

    def _set_block_span(self, name, span):
        if name == "hero" or not self._customising or span not in dv.SPANS:
            return
        layout = [dict(it) for it in self._grid_layout]
        for it in layout:
            if it["id"] == name:
                if it["span"] == span:
                    return
                it["span"] = span
        self._relayout_grid(layout)

    def _remove_module(self, name):
        if not self._customising or len(self._grid_layout) <= 1:
            return
        self._relayout_grid([dict(it) for it in self._grid_layout if it["id"] != name])

    def _add_module(self, name):
        if not self._customising or any(it["id"] == name for it in self._grid_layout):
            return
        layout = [dict(it) for it in self._grid_layout]
        layout.append({"id": name, "span": dv.GRID_COLS})
        self._relayout_grid(layout)

    # ---- the drag ----
    def _grip_press(self, event, name):
        if not self._customising:
            return
        self._drag_block = name
        self._drag_origin = self._grid_rects[name]
        self._drag_last = (event.x / self.scale, event.y / self.scale)
        self._drag_pos = [self._drag_origin[0], self._drag_origin[1]]

        # "Drop target: dashed accent placeholder at true size." Drawn where the
        # module came from and moved as the target slot changes.
        x, y, w, h = self._drag_origin
        self._drop_marker = self.bg.create_rectangle(
            x, y, x + w, y + h, outline=ACCENT, width=2, dash=(6, 5), fill="")
        # "Origin slot collapses" - the module leaves the flow, so hide it and
        # drag a pre-rendered rotated copy instead of the live items.
        self.bg.itemconfigure(f"blk_{name}", state="hidden")
        self._drag_ghost = self._make_drag_ghost(name, w, h)

    def _make_drag_ghost(self, name, w, h):
        """"Dragged copy: rotate -0.6deg · shadow lg · follows cursor."

        Rendered once, here, and then only moved. Re-rotating per motion event
        would be a resample plus a full window composite for every pixel of
        mouse travel.
        """
        sw, sh = self._S(w), self._S(h)
        card = self._composite.crop(
            (self._S(self._drag_origin[0]), self._S(self._drag_origin[1]),
             self._S(self._drag_origin[0]) + sw,
             self._S(self._drag_origin[1]) + sh)).convert("RGBA")
        shadow = Image.new("RGBA", (sw, sh), (0, 0, 0, 150))
        pad = self._S(18)
        canvas_img = Image.new("RGBA", (sw + pad * 2, sh + pad * 2), (0, 0, 0, 0))
        canvas_img.paste(shadow.filter(ImageFilter.GaussianBlur(self._S(9))),
                         (pad, pad + self._S(4)), None)
        canvas_img.alpha_composite(card, (pad, pad))
        canvas_img = canvas_img.rotate(dv.DRAG_ROTATE_DEG, resample=Image.BICUBIC,
                                       expand=False)
        photo = to_photo(canvas_img)
        self._keep_image(photo)
        item = self.bg.create_image(self._drag_origin[0] - 18,
                                    self._drag_origin[1] - 18,
                                    anchor="nw", image=photo)
        return item

    def _grip_drag(self, event=None):
        # Every handler bound in customise mode takes its event optionally.
        # Tkinter's _substitute passes the arguments through *raw* when their
        # count doesn't match its format, so a binding Tk invokes without
        # substitutions arrives with none at all - which crashed the stress
        # test's log-flood phase intermittently. None of these read the event.
        if event is None:
            return
        name = getattr(self, "_drag_block", None)
        if not name:
            return
        now = (event.x / self.scale, event.y / self.scale)
        dx, dy = now[0] - self._drag_last[0], now[1] - self._drag_last[1]
        self._drag_last = now
        self._drag_pos[0] += dx
        self._drag_pos[1] += dy
        self.bg.move(self._drag_ghost, dx, dy)
        self._move_drop_marker()

    def _move_drop_marker(self):
        """Put the placeholder in the slot the module would land in."""
        target = self._drop_index()
        layout = [it for it in self._grid_layout if it["id"] != self._drag_block]
        layout.insert(target, {"id": self._drag_block,
                               "span": self._span_of(self._drag_block)})
        rects = self._compute_grid(layout, editing=True)
        x, y, w, h = rects[self._drag_block]
        self.bg.coords(self._drop_marker, x, y, x + w, y + h)

    def _span_of(self, name):
        return next((it["span"] for it in self._grid_layout if it["id"] == name),
                    dv.GRID_COLS)

    def _drop_index(self):
        """Where the dragged module would slot in, from the ghost's centre.

        Compared against the *other* modules' centres, so the answer is an
        index into the list rather than a free position - which is what makes
        overlap impossible.
        """
        cx = self._drag_pos[0] + self._drag_origin[2] / 2
        cy = self._drag_pos[1] + self._drag_origin[3] / 2
        index = 0
        for it in self._grid_layout:
            if it["id"] == self._drag_block:
                continue
            rx, ry, rw, rh = self._grid_rects[it["id"]]
            past = (cy > ry + rh / 2) or (
                abs(cy - (ry + rh / 2)) < rh / 2 and cx > rx + rw / 2)
            if past:
                index += 1
        return index

    def _grip_release(self, _event=None):
        name = getattr(self, "_drag_block", None)
        if not name:
            return
        target = self._drop_index()
        self._grip_cleanup()
        layout = [dict(it) for it in self._grid_layout if it["id"] != name]
        layout.insert(target, {"id": name, "span": self._span_of(name)})
        self._relayout_grid(layout)

    def _grip_cancel(self):
        """Esc mid-drag: put it back exactly where it was."""
        name = getattr(self, "_drag_block", None)
        if not name:
            return
        self._grip_cleanup()
        self.bg.itemconfigure(f"blk_{name}", state="normal")

    def _grip_cleanup(self):
        for attr in ("_drag_ghost", "_drop_marker"):
            item = getattr(self, attr, None)
            if item:
                try:
                    self.bg.delete(item)
                except Exception:
                    pass
            setattr(self, attr, None)
        self._drag_block = None

    # ---- keyboard parity ----
    # "Handle is focusable. Space picks up, arrows move, Space drops, Esc
    # cancels. A pointer-only implementation is incomplete."
    def _customise_key(self, event):
        if not getattr(self, "_customising", False):
            return
        order = [it["id"] for it in self._grid_layout]
        if not order:
            return
        held = getattr(self, "_kbd_held", None)
        focus = getattr(self, "_kbd_focus", order[0])
        if focus not in order:
            focus = order[0]

        if event.keysym == "space":
            self._kbd_held = None if held else focus
            self._kbd_focus = focus
            self._highlight_handle(focus, picked=bool(self._kbd_held))
            return "break"
        if event.keysym not in ("Up", "Down", "Left", "Right"):
            return None
        step = -1 if event.keysym in ("Up", "Left") else 1
        index = order.index(focus)
        if held:
            new_index = max(0, min(len(order) - 1, index + step))
            if new_index == index:
                return "break"
            layout = [dict(it) for it in self._grid_layout]
            layout.insert(new_index, layout.pop(index))
            self._kbd_focus = held
            self._relayout_grid(layout)
            self._highlight_handle(held, picked=True)
        else:
            self._kbd_focus = order[max(0, min(len(order) - 1, index + step))]
            self._highlight_handle(self._kbd_focus, picked=False)
        return "break"

    def _highlight_handle(self, name, picked):
        for key, parts in self._grips.items():
            strip = parts.get("label")
            if strip is None:
                continue
            focused = key == name
            self.bg.itemconfigure(
                strip, fill=(EMBER if picked else NAV_ACTIVE_TEXT) if focused else MUTED)

    def _reset_dashboard(self):
        self._relayout_grid([dict(it) for it in DEFAULT_GRID])

    # ---- shared building blocks for the secondary views ----
    def _view_panel(self, title, subtitle):
        """Full-height glass panel with a heading, used by every non-dashboard
        view. Returns (x, y, w, h) of the area left for content below the head,
        plus the canvas id of the subtitle so it can be updated live."""
        x0, y = self._content_x0(), self._content_y0()
        w, h = WIDTH - MARGIN - x0, HEIGHT - MARGIN - y
        self._card(x0, y, w, h, kind="panel")
        self.bg.create_text(x0 + 20, y + 26, anchor="w", text=title,
                            fill=TEXT, font=dv.type_font("pane_title"))
        sub = self.bg.create_text(x0 + 20, y + 48, anchor="w", text=subtitle,
                                  fill=FAINT, font=dv.type_font("meta"), width=w - 300)
        return (x0, y, w, h), sub

    def _view_button(self, x, y, w, text, command, accent=False):
        button = ctk.CTkButton(
            self.root, text=text, command=command,
            fg_color=ACCENT_TINT if accent else SURFACE,
            hover_color=SURFACE_HOVER, text_color=ACCENT_LIGHT if accent else MUTED,
            bg_color=self._bg_at(x + w / 2, y + 15), border_width=1,
            border_color=EDGE, corner_radius=9, font=ctk.CTkFont(size=12),
        )
        self.bg.create_window(x, y, anchor="nw", window=button, width=w, height=30)
        return button

    def _scroll_list(self, x, y, w, h):
        """A scrollable region for list rows. Same rounded-plate-plus-square-
        widget trick the activity log uses, so the corners stay clean."""
        plate = make_solid_tile(self._S(w), self._S(h), LOG_BG, radius=self._S(10))
        photo = to_photo(plate)
        self._keep_image(photo)
        self.bg.create_image(x, y, anchor="nw", image=photo)
        self._composite.paste(plate, (self._S(x), self._S(y)), plate)
        # A CTkScrollableFrame is internally a child of its own private canvas
        # and only re-parents itself through pack/grid/place - so handing it
        # straight to create_window() fails ("can't use ... in a window item of
        # this canvas"). Place a plain holder instead and pack the scroller into
        # it, which is the arrangement CTk expects.
        holder = ctk.CTkFrame(self.root, fg_color=LOG_BG, bg_color=LOG_BG,
                              corner_radius=0)
        self.bg.create_window(x + 8, y + 8, anchor="nw", window=holder,
                              width=w - 16, height=h - 16)
        frame = ctk.CTkScrollableFrame(
            holder, fg_color=LOG_BG, corner_radius=0,
            scrollbar_button_color=SURFACE, scrollbar_button_hover_color=SURFACE_HOVER,
        )
        frame.pack(fill="both", expand=True)
        return frame

    def _list_row(self, parent, title, detail, meta, command=None, action=None,
                  actions=None):
        row = ctk.CTkFrame(parent, fg_color=CARD_TINT, corner_radius=9)
        row.pack(fill="x", padx=2, pady=3)
        ctk.CTkLabel(row, text=title, text_color=TEXT, anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(row, text=detail, text_color=MUTED, anchor="w",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(0, 8))
        buttons = list(actions or [])
        if action:
            buttons.append(action)
        action_w = 0
        x_off = -10
        for label, callback in reversed(buttons):
            # A row action has to be visible. The promote path used to be
            # right-click only, which is the same as not existing: it worked
            # perfectly and still read as "I can't change non-games into
            # games", because nothing on screen said it was there.
            bw = 96 if len(label) > 8 else 76
            ctk.CTkButton(row, text=label, command=callback, width=bw,
                          height=26, fg_color=SURFACE, hover_color=SURFACE_HOVER,
                          text_color=ACCENT_LIGHT, border_width=1,
                          border_color=EDGE, corner_radius=8,
                          font=ctk.CTkFont(size=11)).place(
                relx=1.0, rely=0.5, anchor="e", x=x_off)
            x_off -= bw + 8
            action_w += bw + 8
        if meta:
            # Sits left of the action when there is one, so a row can carry
            # both a value (7d's profile column) and a button.
            ctk.CTkLabel(row, text=meta, text_color=FAINT, anchor="e",
                         font=ctk.CTkFont(size=11)).place(
                relx=1.0, rely=0.5, anchor="e", x=-(action_w + 12 if action_w else 12))
        if command:
            for widget in (row, *row.winfo_children()):
                widget.bind("<Button-1>", lambda _e: command())
                widget.configure(cursor="hand2")
        return row

    def _empty_note(self, parent, text):
        ctk.CTkLabel(parent, text=text, text_color=FAINT, justify="left",
                     font=ctk.CTkFont(size=12), wraplength=700).pack(
            anchor="w", padx=14, pady=14)

    # ---- Recordings ----
    # ---- Clips (frame 2b) ----
    # v2 listed per-game *folders*. v3 lists the clips themselves: a By-game
    # sidebar with counts, then a table of Clip / Size / Recorded / Actions.
    #
    # Two columns the frame draws are deliberately absent:
    #   * Length - reading a duration out of an .mkv needs ffprobe, which this
    #     project doesn't depend on. No source, so no column (CLAUDE.md).
    #   * Thumbnails - same reason. The frame's leading chip is the game's
    #     initials ("HD" for Helldivers 2), which is real data, so that stays.
    CLIP_LIST_CAP = 400          # newest N; a recording root can hold terabytes

    def _build_clips(self):
        (x, y, w, h), sub = self._view_panel("Clips", self.config.get("recording_root", ""))
        self._rec_sub = sub

        self._clip_search = ctk.CTkEntry(
            self.root, placeholder_text="Search clips", fg_color=dv.GROUND,
            border_color=EDGE, border_width=1, text_color=TEXT,
            corner_radius=dv.RADIUS_CONTROL, font=ctk.CTkFont(size=12), height=30)
        self._clip_search.bind("<KeyRelease>", lambda _e: self._render_clips_rows())
        self.bg.create_window(x + w - 330, y + 20, anchor="nw",
                              window=self._clip_search, width=190, height=30)
        # NOT in _dashboard_widgets. That list is the dashboard's own modules,
        # and _relayout_grid destroys every widget in it - so rearranging the
        # dashboard was destroying the Clips pane's search box, leaving it dead
        # (TclError on the next keystroke) until a restart. Entering Customise
        # mode also disabled it, for the same reason.

        self._clip_sort = ctk.CTkOptionMenu(
            self.root, values=["Newest", "Oldest", "Largest"],
            command=lambda _v: self._render_clips_rows(),
            fg_color=SURFACE, button_color=SURFACE, button_hover_color=SURFACE_HOVER,
            text_color=MUTED, corner_radius=dv.RADIUS_CONTROL,
            font=ctk.CTkFont(size=12), width=110, height=30)
        self.bg.create_window(x + w - 130, y + 20, anchor="nw",
                              window=self._clip_sort, width=110, height=30)

        # 7b: "Lives in: Top of the Clips pane, full width."
        ribbon_h = dv.RIBBON_H
        self._build_ribbon(x + 12, y + 74, w - 24, ribbon_h)
        head_y = y + 82 + ribbon_h + 8

        # Left: By game. Right: the clip table.
        side_w = 224
        body_y = head_y + 14
        body_h = h - (body_y - y) - 34
        self.bg.create_text(x + 16, head_y, anchor="w", text=self._track("By game"),
                            fill=FAINT, font=dv.type_font("eyebrow"))
        self.bg.create_text(x + 16 + side_w + 16, head_y, anchor="w",
                            text=self._track("Clip"), fill=FAINT,
                            font=dv.type_font("eyebrow"))
        # Length is back (7f) - it needed ffprobe, which is now an optional
        # dependency. The column stays even without ffmpeg; the cells are just
        # empty, which is truthful and keeps the row alignment stable.
        for label, dx in (("Length", w - 376), ("Size", w - 300),
                          ("Recorded", w - 210), ("Actions", w - 96)):
            self.bg.create_text(x + dx, head_y, anchor="w", text=self._track(label),
                                fill=FAINT, font=dv.type_font("eyebrow"))
        # The frame draws a hairline under the column head. It fades like every
        # other rule here - "no hard-stopped 1px greys" outranks the frame's
        # plain CSS border (BUILD-SPEC line 175).
        head_x = x + 16 + side_w + 16
        self._fading_rule(head_x, head_y + 10, w - 32 - side_w - 16)

        self._clip_games = self._scroll_list(x + 16, body_y, side_w, body_h)
        self._rec_list = self._scroll_list(x + 16 + side_w + 16, body_y,
                                           w - 48 - side_w, body_h)

        self._view_button(x + 16, y + h - 26, side_w, "Reveal recording root",
                          self._open_recording_root)

        # "Clips under min_clip_seconds are deleted automatically and never
        # listed here." Per the build order this note IS the empty state.
        self._clip_note_text = (
            f"Clips under min_clip_seconds ({self.config.get('min_clip_seconds', 10)}s) "
            "are deleted automatically and never listed here.")
        self.bg.create_text(x + 16 + side_w + 16, y + h - 14, anchor="w",
                            text=self._clip_note_text, fill=FAINT,
                            font=dv.type_font("meta"))

        self._clips = []
        self._clip_filter_game = None
        self._rec_loaded = False

    def _refresh_clips(self):
        root_dir = self.config.get("recording_root", "")
        for child in self._rec_list.winfo_children():
            child.destroy()
        self._empty_note(self._rec_list, "Scanning…")

        def worker():
            clips, error = [], None
            try:
                for game in sorted(os.listdir(root_dir)):
                    folder = os.path.join(root_dir, game)
                    if not os.path.isdir(folder):
                        continue
                    with os.scandir(folder) as inner:
                        for f in inner:
                            if not (f.is_file() and f.name.lower().endswith(VIDEO_EXTS)):
                                continue
                            st = f.stat()
                            clips.append({
                                "game": game, "name": f.name, "path": f.path,
                                "rel": f"{game}/{f.name}",
                                "size": st.st_size, "mtime": st.st_mtime,
                            })
            except Exception as exc:
                error = exc
            self._ui(lambda: self._render_clips(clips, error, root_dir))

        threading.Thread(target=worker, daemon=True).start()

    def _render_clips(self, clips, error, root_dir):
        self._clips = clips
        self._clips_error = error
        self._clips_root = root_dir

        for child in self._clip_games.winfo_children():
            child.destroy()
        if not error:
            counts = {}
            for c in clips:
                counts[c["game"]] = counts.get(c["game"], 0) + 1
            self._game_button(None, "All clips", len(clips))
            for game, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower())):
                self._game_button(game, game, n)

        total = sum(c["size"] for c in clips)
        self.bg.itemconfigure(
            self._rec_sub,
            text=f"{len(clips)} clip{'' if len(clips) == 1 else 's'}  ·  "
                 f"{_format_bytes(total)}  ·  {root_dir}")
        self._render_clips_rows()
        self._queue_thumb_work(clips, root_dir)

    def _queue_thumb_work(self, clips, root_dir):
        """Backfill frames and durations for what's on screen (7f).

        Both run on the thumb worker's own thread. Durations come first because
        the Length column is cheap - ffprobe reads the container header - where
        four seeks per clip is not.
        """
        if not thumbs.available() or not clips:
            return
        # Single-flight. Every visit to the Clips pane calls this, and each run
        # launches an ffprobe per clip - without the guard, flicking between
        # panes stacked a thread per visit and left dozens of ffprobe processes
        # racing each other. One in flight is enough; the next render picks up
        # whatever this one didn't reach.
        if getattr(self, "_thumb_scan_busy", False):
            return
        self._thumb_scan_busy = True
        self.thumbs.recording_root = root_dir
        newest = clips[:40]      # "oldest last": the visible page first

        def worker():
            try:
                for clip in newest:
                    if clip["path"] in self._clip_durations:
                        continue
                    seconds = thumbs.duration_of(clip["path"])
                    if seconds:
                        self._clip_durations[clip["path"]] = seconds
                        self._ui(lambda p=clip["path"]: self._apply_clip_length(p))
                self.thumbs.backfill([c["path"] for c in newest])
            finally:
                self._thumb_scan_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _apply_clip_length(self, path):
        label = self._clip_length_labels.get(path)
        if label is None:
            return
        try:
            label.configure(text=self._clip_length_label({"path": path}))
        except Exception:
            self._clip_length_labels.pop(path, None)

    def _game_button(self, game, label, count):
        row = ctk.CTkFrame(self._clip_games, fg_color=CARD_TINT, corner_radius=dv.RADIUS_CONTROL)
        row.pack(fill="x", padx=2, pady=2)
        active = self._clip_filter_game == game
        ctk.CTkLabel(row, text=label, anchor="w", text_color=TEXT if active else MUTED,
                     font=ctk.CTkFont(size=12)).pack(side="left", padx=(10, 4), pady=6)
        ctk.CTkLabel(row, text=str(count), text_color=ACCENT_LIGHT if active else FAINT,
                     font=ctk.CTkFont(size=11)).pack(side="right", padx=10)

        def pick(_e=None):
            self._clip_filter_game = game
            self._render_clips(self._clips, self._clips_error, self._clips_root)

        for widget in (row, *row.winfo_children()):
            widget.bind("<Button-1>", pick)

    def _render_clips_rows(self):
        for child in self._rec_list.winfo_children():
            child.destroy()
        # The labels belong to widgets that were just destroyed; keeping the
        # map would leave _apply_clip_length writing into dead Tk objects.
        self._clip_length_labels = {}
        if getattr(self, "_clips_error", None) is not None:
            self._empty_note(self._rec_list,
                             f"Couldn't read {self._clips_root}\n{self._clips_error}")
            return

        query = (self._clip_search.get() or "").strip().lower()
        rows = [c for c in self._clips
                if (self._clip_filter_game in (None, c["game"]))
                and (not query or query in c["rel"].lower())]
        sort = self._clip_sort.get()
        if sort == "Oldest":
            rows.sort(key=lambda c: c["mtime"])
        elif sort == "Largest":
            rows.sort(key=lambda c: -c["size"])
        else:
            rows.sort(key=lambda c: -c["mtime"])

        if not rows:
            # Empty state is the min-clip note only, exactly as the frame says.
            self._empty_note(self._rec_list, self._clip_note_text)
            return
        for clip in rows[:self.CLIP_LIST_CAP]:
            self._clip_row(clip)
        if len(rows) > self.CLIP_LIST_CAP:
            self._empty_note(
                self._rec_list,
                f"Showing the newest {self.CLIP_LIST_CAP} of {len(rows)}. "
                "Narrow it with the search box.")

    @staticmethod
    def _initials(name):
        words = [w for w in re.split(r"[\s_\-]+", name) if w]
        return ("".join(w[0] for w in words[:2]) or name[:2]).upper()

    @staticmethod
    def _recorded_label(mtime):
        now = time.time()
        delta = now - mtime
        if delta < 3600:
            return f"{max(1, int(delta // 60))} min ago"
        today = time.localtime(now)
        when = time.localtime(mtime)
        if (when.tm_year, when.tm_yday) == (today.tm_year, today.tm_yday):
            return time.strftime("Today %H:%M", when)
        if delta < 86400 * 2:
            return "Yesterday"
        if delta < 86400 * 7:
            return time.strftime("%a", when)
        return time.strftime("%d %b", when)

    # 7f: the row thumbnail is 4 frames wide at heart - it shows frame 3 and
    # steps through all four as the pointer crosses it.
    CLIP_THUMB_W, CLIP_THUMB_H = 76, 43
    CLIP_THUMB_CACHE = 60          # clips' worth of frames held at once

    def _clip_row(self, clip):
        row = ctk.CTkFrame(self._rec_list, fg_color=CARD_TINT, corner_radius=dv.RADIUS_CONTROL)
        row.pack(fill="x", padx=2, pady=3)

        self._clip_thumb(row, clip)

        # Actions pack right-first so they keep their place as the title flexes.
        for role, command, tip in (
            ("delete_clip", lambda: self._delete_clip(clip), "Delete"),
            ("reveal", lambda: self._open_path(os.path.dirname(clip["path"])), "Reveal"),
        ):
            btn = ctk.CTkButton(
                row, text=ICON_GLYPHS[dv.ICONS[role]], width=28, height=28,
                fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
                corner_radius=8, font=ctk.CTkFont(family=ICON_FONT, size=13),
                command=command)
            btn.pack(side="right", padx=2)

        ctk.CTkLabel(row, text=self._recorded_label(clip["mtime"]), width=90, anchor="e",
                     text_color=MUTED, font=ctk.CTkFont(size=11)).pack(side="right", padx=6)
        ctk.CTkLabel(row, text=_format_bytes(clip["size"]), width=80, anchor="e",
                     text_color=TEXT_SOFT, font=ctk.CTkFont(size=11)).pack(side="right")
        # Length, at last - it needed ffprobe, which is now an optional
        # dependency rather than a missing one. Blank when unknown; never a
        # placeholder duration.
        length = ctk.CTkLabel(row, text=self._clip_length_label(clip), width=64,
                              anchor="e", text_color=MUTED,
                              font=ctk.CTkFont(family="Consolas", size=11))
        length.pack(side="right", padx=4)
        self._clip_length_labels[clip["path"]] = length

        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(text, text=os.path.splitext(clip["name"])[0], anchor="w",
                     text_color=TEXT, font=ctk.CTkFont(size=12)).pack(anchor="w")
        ctk.CTkLabel(text, text=clip["rel"], anchor="w", text_color=FAINT,
                     font=ctk.CTkFont(family="Consolas", size=10)).pack(anchor="w")

    def _clip_length_label(self, clip):
        seconds = self._clip_durations.get(clip["path"])
        if not seconds:
            return ""
        hours, rem = divmod(int(seconds), 3600)
        minutes, secs = divmod(rem, 60)
        return (f"{hours}:{minutes:02d}:{secs:02d}" if hours
                else f"{minutes}:{secs:02d}")

    def _clip_thumb(self, row, clip):
        """The scrubbable thumbnail (7f).

        "Trigger: pointer x over the thumb → 4 zones. Swap: instant - no
        crossfade, no transition. Leave: returns to frame 3."

        Until the frames exist it falls back to the game's initials, which is
        real data - the spec's "dashed placeholder + spinner, never blank"
        without a spinner, since animating one would repaint every tick.
        """
        frames = self._clip_frames(clip)
        if not frames:
            ctk.CTkLabel(row, text=self._initials(clip["game"]),
                         width=self.CLIP_THUMB_W, height=self.CLIP_THUMB_H,
                         fg_color=ACCENT_TINT, corner_radius=8,
                         text_color=ACCENT_LIGHT,
                         font=ctk.CTkFont(size=11, weight="bold")).pack(
                side="left", padx=(8, 10), pady=6)
            return

        holder = ctk.CTkFrame(row, fg_color="transparent")
        holder.pack(side="left", padx=(8, 10), pady=6)
        label = ctk.CTkLabel(holder, text="", image=frames[thumbs.DEFAULT_FRAME])
        label.pack()
        # "Progress line 3px, #B9AEF9" under the thumbnail, one segment lit.
        line = ctk.CTkFrame(holder, fg_color=dv.GROUND, height=3,
                            width=self.CLIP_THUMB_W, corner_radius=2)
        line.pack(fill="x")
        fill = ctk.CTkFrame(line, fg_color=ACCENT_LIGHT, height=3, corner_radius=2)

        def show(index):
            label.configure(image=frames[index])
            fill.place(relx=index / thumbs.FRAME_COUNT, rely=0,
                       relwidth=1.0 / thumbs.FRAME_COUNT, relheight=1.0)

        def on_motion(event):
            zone = int(event.x / max(1, label.winfo_width()) * thumbs.FRAME_COUNT)
            show(max(0, min(thumbs.FRAME_COUNT - 1, zone)))

        def on_leave(_event):
            label.configure(image=frames[thumbs.DEFAULT_FRAME])
            fill.place_forget()

        label.bind("<Motion>", on_motion)
        label.bind("<Leave>", on_leave)
        label.configure(cursor="hand2")

    def _clip_frames(self, clip):
        """Cached CTkImages for a clip's four frames, or None."""
        path = clip["path"]
        cached = self._clip_thumb_cache.get(path)
        if cached is not None:
            return cached
        root = self.config.get("recording_root", "")
        if not thumbs.have_frames(root, path):
            return None
        images = []
        for frame in thumbs.frame_paths(root, path):
            try:
                img = Image.open(frame).convert("RGB")
            except Exception:
                return None
            images.append(ctk.CTkImage(light_image=img, dark_image=img,
                                       size=(self.CLIP_THUMB_W, self.CLIP_THUMB_H)))
        # Bounded: four images per clip against a 400-clip list is 1600 of them
        # held forever, which is the same bitmap exhaustion the dashboard hit.
        # Oldest-inserted goes first; the visible rows are the recent ones.
        while len(self._clip_thumb_cache) >= self.CLIP_THUMB_CACHE:
            self._clip_thumb_cache.pop(next(iter(self._clip_thumb_cache)))
        self._clip_thumb_cache[path] = images
        return images

    def _on_thumbs_ready(self, clip_path, _frames):
        """Worker callback - arrives on the extraction thread."""
        def apply():
            self._clip_thumb_cache.pop(clip_path, None)
            if self._current_view == "clips":
                self._refresh_clips()
        self._ui(apply)

    def _delete_clip(self, clip):
        """Manual delete, under obs-footage-sacred's copy-verify-then-delete rule.

        The offloader never removes a local clip without a byte-verified NAS
        copy; a delete button in the UI must not be a way around that. So if
        offload is on and this clip is still queued - i.e. not yet verified at
        the far end - the delete is refused outright rather than confirmed.
        Everything else asks first.
        """
        pending = set()
        if self.offloader and self.offloader.enabled:
            try:
                pending = self.offloader.pending_paths()
            except Exception:
                pending = set()
        if clip["path"] in pending:
            tkinter.messagebox.showwarning(
                "Not offloaded yet",
                f"{clip['name']} hasn't been copied to the NAS and verified yet.\n\n"
                "Nebula won't delete a clip that has no second copy. It'll be "
                "safe to remove once the offload queue has drained.",
                parent=self.root)
            return
        if not tkinter.messagebox.askyesno(
                "Delete clip",
                f"Permanently delete {clip['rel']}?\n\n"
                f"{_format_bytes(clip['size'])} · this cannot be undone.",
                parent=self.root):
            return
        try:
            os.remove(clip["path"])
        except OSError as exc:
            error = exc
            self._log(f"[Manual] Couldn't delete {clip['name']}: {error}")
            return
        self._log(f"[Manual] Deleted {clip['rel']}")
        # The cached frames outlive nothing: a deleted clip's thumbnails are
        # just orphaned files in .nebula/thumbs that would never be cleaned up.
        thumbs.purge(self.config.get("recording_root", ""), clip["path"])
        self._clip_thumb_cache.pop(clip["path"], None)
        self._clip_durations.pop(clip["path"], None)
        self._clips = [c for c in self._clips if c["path"] != clip["path"]]
        self._render_clips(self._clips, None, self._clips_root)

    def _open_recording_root(self):
        self._open_path(self.config.get("recording_root", ""))

    def _open_path(self, path):
        try:
            if os.path.exists(path):
                os.startfile(path)
            else:
                tkinter.messagebox.showwarning("Missing", f"{path} not found.")
        except OSError as exc:
            self._log(f"[Manual] Could not open {path}: {exc}")

    # ---- Games ----
    # ---- Games (frame 2d) ----
    # Three blocks: what's awaiting a decision, the games, the ignored apps.
    #
    # Two things the frame draws are absent for want of a source: the Steam
    # AppID beside each game (the classifier stores {display_name, source}, no
    # id) and "seen 4x" on an unclassified row (nothing counts sightings).
    #
    # The unclassified block is read-only on purpose. Deciding still happens in
    # the existing modal flow (_poll_manual_review), which owns the queue's
    # _in_review bookkeeping; this block PEEKS so that showing an item can never
    # swallow the prompt the user is waiting on.
    def _build_games(self):
        (x, y, w, h), sub = self._view_panel("Games", "What the classifier has learned.")
        self._games_sub = sub
        # "Add a game" leads, because it is the button that works. Rescan can
        # only ever import Steam, and a library fed by HoYoPlay / Roblox /
        # CurseForge has nothing for it to find.
        self._view_button(x + w - 150, y + 20, 130, "Add a game", self._add_running_game)
        self._view_button(x + w - 292, y + 20, 132, "Rescan Steam", self._rescan_steam)
        self._view_button(x + w - 414, y + 20, 112, "Game data", self._open_game_data)

        col_w = (w - 48) / 2
        top_h = 96
        self.bg.create_text(x + 16, y + 82, anchor="w", text=self._track("Unclassified"),
                            fill=FAINT, font=dv.type_font("eyebrow"))
        self._games_pending = self._scroll_list(x + 16, y + 96, w - 32, top_h)

        list_y = y + 96 + top_h + 26
        list_h = h - (list_y - y) - 34
        self.bg.create_text(x + 16, list_y - 14, anchor="w", text=self._track("Games"),
                            fill=FAINT, font=dv.type_font("eyebrow"))
        self.bg.create_text(x + 32 + col_w, list_y - 14, anchor="w",
                            text=self._track("Not games"), fill=FAINT,
                            font=dv.type_font("eyebrow"))
        self._games_list = self._scroll_list(x + 16, list_y, col_w, list_h)
        self._nongames_list = self._scroll_list(x + 32 + col_w, list_y, col_w, list_h)

        self._games_foot = self.bg.create_text(
            x + 16, y + h - 14, anchor="w", text="", fill=FAINT,
            font=dv.type_font("meta"))
        self.bg.create_text(x + 32 + col_w, y + h - 14, anchor="w",
                            text="Make a game moves an app back  ·  right-click works too.",
                            fill=FAINT, font=dv.type_font("meta"))

    def _refresh_games(self):
        for parent in (self._games_list, self._nongames_list, self._games_pending):
            for child in parent.winfo_children():
                child.destroy()
        try:
            data = self.classifier._data
            games, non_games = data.get("games", {}), data.get("non_games", {})
        except Exception as exc:
            self._empty_note(self._games_list, f"Couldn't read the game list: {exc}")
            return

        pending = []
        try:
            pending = self.classifier.peek_pending_reviews()
        except Exception:
            pass
        if pending:
            for name in pending:
                self._list_row(self._games_pending, name,
                               "Nebula will ask about this one", "awaiting")
        else:
            self._empty_note(self._games_pending, "Nothing awaiting a decision.")

        # Collapse the exe->entry map down to one row per actual game.
        by_name = {}
        for key, value in games.items():
            if isinstance(value, dict):
                name = value.get("display_name") or key
                source = value.get("source", "")
            else:
                name, source = key, ""
            entry = by_name.setdefault(name, {"exes": [], "source": source})
            entry["exes"].append(key)

        awaiting = (f"{len(pending)} awaiting your call   ·   " if pending else "")
        self.bg.itemconfigure(
            self._games_sub,
            text=f"{awaiting}{len(by_name)} game{'' if len(by_name) == 1 else 's'} recorded "
                 f"automatically   ·   {len(non_games)} app"
                 f"{'' if len(non_games) == 1 else 's'} ignored")

        synced = bool(self.gamesync and self.gamesync.enabled)
        self.bg.itemconfigure(
            self._games_foot,
            text="Stored in games.json  ·  shared via GitHub" if synced
                 else "Stored in games.json  ·  this machine only")

        if not by_name:
            self._empty_note(
                self._games_list,
                "Nothing classified yet.\n\nJust launch a game — Nebula asks once "
                "and remembers the answer. That's the main path, and the only one "
                "for launcher games (HoYoPlay, Roblox, CurseForge and friends).\n\n"
                "Rescan library only imports games installed through Steam; if "
                "your Steam library is empty it will correctly find nothing.")
        else:
            for name in sorted(by_name, key=str.lower):
                entry = by_name[name]
                exes = ", ".join(sorted(entry["exes"])[:3])
                if len(entry["exes"]) > 3:
                    exes += f"  +{len(entry['exes']) - 3} more"
                # 7d's fourth column. A game with no profile says so rather
                # than showing blank - "inherits default profile" is the
                # frame's own wording.
                primary = sorted(entry["exes"])[0]
                profile = profiles.for_game(self.classifier, primary)
                self._list_row(
                    self._games_list, name, exes,
                    profiles.summary(profile) or "inherits default",
                    actions=[
                        ("Rename",
                         lambda e=primary, n=name: self._rename_known_game(e, n)),
                        ("Profile",
                         lambda e=primary, n=name: self._edit_profile(e, n)),
                    ])

        if not non_games:
            self._empty_note(self._nongames_list, "Nothing ignored yet.")
            return
        keep_alive = {p.lower() for p in self.config.get("keep_alive_audio_processes", [])}
        for basename in sorted(non_games, key=str.lower):
            row = self._list_row(
                self._nongames_list, basename,
                "keep-alive" if basename.lower() in keep_alive else "", "ignored",
                action=("Make a game",
                        lambda b=basename: self._promote_non_game(b)))
            self._bind_promote(row, basename)

    def _bind_promote(self, row, basename):
        """Right-click an ignored app to move it back to Games (frame 2d).

        The action lives in _promote_non_game so it can be exercised directly:
        CustomTkinter proxies bind() onto an inner widget, so event_generate()
        against the row never reaches this handler even though a real click
        does.
        """
        if row is None:
            return
        for widget in (row, *row.winfo_children()):
            widget.bind("<Button-3>", lambda _e, b=basename: self._promote_non_game(b))

    def _promote_non_game(self, basename):
        if not tkinter.messagebox.askyesno(
                "Move back to Games",
                f"Treat {basename} as a game again?\n\n"
                "Nebula will start recording when it's in the foreground.",
                parent=self.root):
            return False
        name = self._ask_display_name(
            basename, suggestion=suggest_display_name(basename))
        if not name:
            return False
        self.classifier.mark_game(basename, name)
        self._log(f"[Manual] {basename} -> game ({name})")
        self._refresh_games()
        self._push_game_data()
        return True

    def _rename_known_game(self, basename, display_name):
        """Change folder/display name for an already-classified game."""
        name = self._ask_display_name(basename, suggestion=display_name)
        if not name or name == display_name:
            return False
        # Same display_name may cover several exes — update them all.
        snap = self.classifier.snapshot()
        games = snap.get("games") or {}
        updated = []
        for key, value in games.items():
            if isinstance(value, dict):
                dn = value.get("display_name") or key
            else:
                dn = key
            if key.lower() == (basename or "").lower() or dn == display_name:
                if self.classifier.set_display_name(key, name):
                    updated.append(key)
        if not updated:
            return False
        self._log(f"[Manual] Renamed {', '.join(updated)} -> {name}")
        self._refresh_games()
        self._push_game_data()
        return True

    # Windows the picker should never offer: the shell, Nebula itself, OBS,
    # and the browsers/editors people have open behind a game. Anything not
    # listed here still shows - the point is to shorten the list, not to guess
    # what is or isn't a game.
    PICKER_SKIP = {
        "explorer.exe", "searchhost.exe", "shellexperiencehost.exe",
        "startmenuexperiencehost.exe", "textinputhost.exe", "applicationframehost.exe",
        "systemsettings.exe", "taskmgr.exe", "widgets.exe", "lockapp.exe",
        "python.exe", "pythonw.exe", "nebula.exe", "obs64.exe", "obs32.exe",
        "cmd.exe", "powershell.exe", "windowsterminal.exe", "conhost.exe",
    }

    def _running_candidates(self):
        """Apps with a visible window that the classifier hasn't judged yet.

        One row per executable, keeping the longest window title seen for it -
        a game usually titles its window with its own name ("Zenless Zone
        Zero"), which is a far better folder name than the exe stem.
        """
        try:
            known = set(self.classifier._data.get("games", {}))
            known |= set(self.classifier._data.get("non_games", {}))
        except Exception:
            known = set()
        known = {k.lower() for k in known}

        found = {}
        for _pid, _path, proc_name, title, _cls in list_visible_windows():
            if not proc_name or not title:
                continue
            key = proc_name.lower()
            if key in known or key in self.PICKER_SKIP:
                continue
            if len(title) > len(found.get(key, ("", ""))[1]):
                found[key] = (proc_name, title)
        return sorted(found.values(), key=lambda pair: pair[1].lower())

    def _add_running_game(self):
        """Pick a game out of what's currently running.

        Rescan only imports Steam, and this machine's Steam library is empty -
        the games come from HoYoPlay, Roblox and CurseForge, so the scan
        correctly reports "0 Steam game(s)" and there was no other way into
        the game list from this pane. The path that always works for a
        launcher game is: have it running, then point at it.
        """
        candidates = self._running_candidates()
        width = 520
        height = min(150 + 56 * max(len(candidates), 1), 520)
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Add a game")
        dialog.overrideredirect(True)
        dialog.geometry(f"{self._S(width)}x{self._S(height)}")
        dialog.attributes("-topmost", True)
        apply_rounded_corners(dialog)
        canvas = self._dialog_bg(dialog, width, height)

        canvas.create_text(width / 2, 34, anchor="center", text="Add a game",
                           fill=TEXT, font=dv.type_font("pane_title"))
        canvas.create_text(
            width / 2, 60, anchor="center", fill=MUTED,
            font=dv.type_font("row_small"), width=width - 60, justify="center",
            text=("Anything with a window that Nebula hasn't judged yet. "
                  "Launcher games only appear once they're running."))

        # Built here rather than through _scroll_list: that helper paints onto
        # the main window's canvas and composite, which this dialog isn't.
        list_h = height - 150
        holder = ctk.CTkFrame(dialog, fg_color=LOG_BG, bg_color=LOG_BG, corner_radius=0)
        canvas.create_window(24, 84, anchor="nw", window=holder,
                             width=width - 48, height=list_h)
        holder = ctk.CTkScrollableFrame(
            holder, fg_color=LOG_BG, corner_radius=0,
            scrollbar_button_color=SURFACE, scrollbar_button_hover_color=SURFACE_HOVER)
        holder.pack(fill="both", expand=True)

        def pick(basename, title):
            dialog.destroy()
            name = self._ask_display_name(basename, suggestion=title.strip())
            if not name:
                return
            self.classifier.mark_game(basename, name)
            self._log(f"[Manual] {basename} -> game ({name})")
            self._refresh_games()
            self._push_game_data()

        if candidates:
            for proc_name, title in candidates:
                self._list_row(holder, title, proc_name, "",
                               command=lambda b=proc_name, t=title: pick(b, t))
        else:
            self._empty_note(
                holder,
                "Nothing new is running.\n\nEverything with a window is already "
                "classified. Start the game first, then come back here.")

        close = ctk.CTkButton(
            dialog, text="Close", command=dialog.destroy,
            fg_color=SURFACE, hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(width / 2 / width * WIDTH,
                                 (height - 36) / height * HEIGHT, CARD_TINT, 225),
            border_width=1, border_color=EDGE, corner_radius=10,
            font=ctk.CTkFont(size=12))
        canvas.create_window(width - 130, height - 52, anchor="nw",
                             window=close, width=106, height=34)

        dialog.lift()
        dialog.focus_force()
        dialog.grab_set()
        self.root.wait_window(dialog)

    # 7d's editor sheet, mockup lines 1692-1717. Base design units.
    PROFILE_SHEET = (452, 386)
    PROFILE_PAD = 20            # sheet padding
    PROFILE_FIELD_H = 34        # control height
    PROFILE_LABEL_H = 22        # label band above each control
    PROFILE_COL_GAP = 14

    def _edit_profile(self, basename, display_name):
        """7d's editor sheet - 452x386, modal over the pane.

        Exactly five fields. "Scope guard: resolution, fps, encoder, bitrate,
        scene. That is the whole feature. No audio tracks, no filters, no
        output paths, no encoder presets - those stay in OBS, and Nebula must
        never silently overwrite settings the user changed there."

        Laid out as the mockup draws it: a 2x2 grid of stacked label-over-field
        blocks, the scene field full width beneath, then the bitrate estimate as
        its own tinted strip, then pills. The old version stacked five
        label-left rows inside a `fg_color="transparent"` CTkFrame and packed
        them, and that is exactly the trap _ask_yes_no_cancel documents: a CTk
        widget's "transparent" doesn't composite against arbitrary canvas art,
        and here the packed rows came out staircased down and across the sheet
        with half the controls clipped out of the host frame entirely. So
        everything static is drawn straight onto the canvas and only the five
        real controls are embedded, each at explicit coordinates.
        """
        current = profiles.for_game(self.classifier, basename) or {}
        width, height = self.PROFILE_SHEET
        pad = self.PROFILE_PAD
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(f"{display_name} profile")
        dialog.overrideredirect(True)
        dialog.geometry(f"{self._S(width)}x{self._S(height)}")
        dialog.attributes("-topmost", True)
        apply_rounded_corners(dialog)
        canvas = self._dialog_bg(dialog, width, height)

        def plate(x, y, w, h, radius, tint, tint_alpha, border_hex, border_alpha):
            """A glass tile on THIS canvas. _glass() paints onto the main
            window's canvas and composite, neither of which a dialog is."""
            tile = make_glass_tile(self._S(w), self._S(h), tint,
                                   tint_alpha=tint_alpha, radius=self._S(radius),
                                   border_hex=border_hex, border_alpha=border_alpha)
            photo = to_photo(tile)
            self._keep_image(photo)
            canvas.create_image(x, y, anchor="nw", image=photo)

        def sheet_bg(x, y):
            """The composited sheet colour under (x, y), for a widget's
            bg_color so its rounded corners don't cut a square out."""
            return self._bg_at(x / width * WIDTH, y / height * HEIGHT,
                               CARD_TINT, 225)

        # ---- header: art tile, name, close ----------------------------------
        plate(pad, pad, 30, 30, 9, SURFACE, 255, EDGE, 40)
        canvas.create_text(pad + 15, pad + 15, anchor="center",
                           text=ICON_GLYPHS[dv.ICONS["games"]],
                           fill=FAINT, font=(ICON_FONT, -13))
        canvas.create_text(pad + 41, pad + 15, anchor="w", text=display_name,
                           fill=TEXT, font=dv.font(14, 500))
        # The X is the sheet's cancel - the mockup's footer has no Cancel button
        # because this is it. Escape does the same thing.
        close = canvas.create_text(
            width - pad - 6, pad + 15, anchor="center", text=ICON_GLYPHS["x"],
            fill=FAINT, font=(ICON_FONT, -10))
        canvas.tag_bind(close, "<Button-1>", lambda _e: dialog.destroy())
        canvas.tag_bind(close, "<Enter>",
                        lambda _e: canvas.itemconfigure(close, fill=TEXT))
        canvas.tag_bind(close, "<Leave>",
                        lambda _e: canvas.itemconfigure(close, fill=FAINT))
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

        # ---- the five fields -------------------------------------------------
        inner = width - pad * 2
        col_w = (inner - self.PROFILE_COL_GAP) // 2
        field_h, label_h = self.PROFILE_FIELD_H, self.PROFILE_LABEL_H
        block_h = label_h + field_h

        def field_label(x, y, text, key):
            """`Resolution  res` - the label with the stored key beside it, so
            the sheet says which games.json field it is writing."""
            canvas.create_text(x, y + 8, anchor="w", text=text, fill=MUTED,
                               font=dv.font(10.5))
            span = self._text_w(text, dv.font(10.5))
            canvas.create_text(x + span + 7, y + 9, anchor="w", text=key,
                               fill=FAINT, font=dv.font(9.5, mono=True))

        def entry(x, y, w, value, placeholder):
            box = ctk.CTkEntry(
                dialog, fg_color=dv.over(dv.TEXT, 0.04, CARD_CORE),
                border_color=EDGE, border_width=1, text_color=TEXT,
                bg_color=sheet_bg(x + w / 2, y + field_h / 2),
                height=field_h, corner_radius=dv.RADIUS_CONTROL,
                font=ctk.CTkFont(size=12), placeholder_text=placeholder,
                # Explicit, because CTk's default placeholder grey sits close
                # enough to TEXT here that "2560x1440" read as a value this
                # profile already had rather than as an example of one.
                placeholder_text_color=FAINT)
            if value:
                box.insert(0, str(value))
            self._focus_ring(box)
            canvas.create_window(x, y, anchor="nw", window=box,
                                 width=w, height=field_h)
            return box

        # An unset dropdown has to say what unset MEANS. CTkOptionMenu has no
        # placeholder, so "" rendered as an empty control that looked broken -
        # the same "just blank" failure as the old scene preview. The sentinel
        # is a real menu entry and maps back to "" on the way out.
        INHERIT = "Inherit default"

        def dropdown(x, y, w, values, value):
            field = dv.over(dv.TEXT, 0.04, CARD_CORE)
            menu = ctk.CTkOptionMenu(
                dialog, values=[INHERIT] + values,
                fg_color=field,
                # The caret sits IN the field in the mockup. A contrasting
                # button colour turned it into a separate blocky chip.
                button_color=field, button_hover_color=SURFACE_HOVER,
                text_color=TEXT, dropdown_fg_color=CARD_CORE,
                dropdown_text_color=TEXT, dropdown_hover_color=SURFACE,
                bg_color=sheet_bg(x + w / 2, y + field_h / 2),
                height=field_h, corner_radius=dv.RADIUS_CONTROL,
                font=ctk.CTkFont(size=12), dropdown_font=ctk.CTkFont(size=12))
            menu.set(value or INHERIT)
            canvas.create_window(x, y, anchor="nw", window=menu,
                                 width=w, height=field_h)
            return menu

        def chosen(menu):
            """The menu's value, with the inherit sentinel read back as unset."""
            value = menu.get().strip()
            return "" if value == INHERIT else value

        left, right = pad, pad + col_w + self.PROFILE_COL_GAP
        row1 = pad + 30 + 15
        row2 = row1 + block_h + 12

        field_label(left, row1, "Resolution", "res")
        res = entry(left, row1 + label_h, col_w, current.get("res"), "2560x1440")

        field_label(right, row1, "Frame rate", "fps")
        fps = dropdown(right, row1 + label_h, col_w,
                       [str(f) for f in profiles.FPS_CHOICES],
                       str(current.get("fps") or ""))

        # ENCODERS maps id -> label. The old sheet listed the ids, so the menu
        # read "nvenc_h264"; the mockup shows "NVENC H.264". Pick by label,
        # store the id.
        by_label = {label: key for key, label in profiles.ENCODERS.items()}
        field_label(left, row2, "Encoder", "encoder")
        encoder = dropdown(left, row2 + label_h, col_w,
                           list(profiles.ENCODERS.values()),
                           profiles.ENCODERS.get(current.get("encoder"), ""))

        field_label(right, row2, "Bitrate", "bitrate_kbps")
        bitrate = entry(right, row2 + label_h, col_w,
                        current.get("bitrate_kbps"), "18000")

        scene_y = row2 + block_h + 15
        field_label(left, scene_y, "OBS scene", "scene")
        scene = entry(left, scene_y + label_h, inner, current.get("scene"),
                      "leave blank to keep the current scene")

        # ---- bitrate estimate, as its own strip ------------------------------
        est_y = scene_y + block_h + 15
        plate(pad, est_y, inner, 40, 11, ACCENT, 18, ACCENT, 46)
        canvas.create_text(pad + 14, est_y + 20, anchor="w",
                           text=ICON_GLYPHS[dv.ICONS["storage"]],
                           fill=ACCENT_LIGHT, font=(ICON_FONT, -14))
        estimate_id = canvas.create_text(
            pad + 36, est_y + 20, anchor="w", text="", fill=ACCENT_LIGHT,
            font=dv.type_font("meta"))

        def refresh_estimate(_event=None):
            try:
                kbps = int(bitrate.get())
            except (TypeError, ValueError):
                canvas.itemconfigure(
                    estimate_id, text="Set a bitrate to see the hourly cost.",
                    fill=FAINT)
                return
            gb = profiles.estimated_gb_per_hour(kbps)
            canvas.itemconfigure(
                estimate_id, fill=ACCENT_LIGHT,
                text=f"Estimated {gb:.1f} GB/h at this bitrate" if gb else "")

        bitrate.bind("<KeyRelease>", refresh_estimate)
        refresh_estimate()

        def collect():
            raw = {"enabled": True, "res": res.get().strip(),
                   "scene": scene.get().strip(),
                   "encoder": by_label.get(chosen(encoder), "")}
            raw["fps"] = chosen(fps) or None
            raw["bitrate_kbps"] = bitrate.get().strip() or None
            return profiles.sanitise(raw)

        def do_save():
            profile = collect()
            profiles.save(self.classifier, basename, profile)
            self._log(f"[Profile] {display_name}: {profiles.summary(profile) or 'cleared'}")
            dialog.destroy()
            self._refresh_games()
            self._push_game_data()

        def do_remove():
            profiles.save(self.classifier, basename, None)
            self._log(f"[Profile] {display_name}: removed, inherits the default")
            dialog.destroy()
            self._refresh_games()
            self._push_game_data()

        # ---- pills -----------------------------------------------------------
        # Radius is half the height, which is what 999px resolves to. Remove is
        # the one ember control on the sheet; it is also the only destructive one.
        btn_y, btn_h = est_y + 40 + 15, 36
        save_btn = ctk.CTkButton(
            dialog, text="Save profile", command=do_save,
            fg_color=ACCENT_TINT, hover_color=SURFACE_HOVER,
            text_color=TEXT, bg_color=sheet_bg(pad + 62, btn_y + btn_h / 2),
            border_width=1, border_color=ACCENT, corner_radius=btn_h // 2,
            font=ctk.CTkFont(size=13))
        self._focus_ring(save_btn, resting_border=ACCENT)
        canvas.create_window(pad, btn_y, anchor="nw", window=save_btn,
                             width=124, height=btn_h)

        remove_btn = ctk.CTkButton(
            dialog, text=f"{ICON_GLYPHS['trash']}  Remove", command=do_remove,
            fg_color="transparent", hover_color=SURFACE_HOVER,
            text_color=EMBER,
            bg_color=sheet_bg(width - pad - 52, btn_y + btn_h / 2),
            border_width=1, border_color=EDGE, corner_radius=btn_h // 2,
            font=ctk.CTkFont(size=13))
        self._focus_ring(remove_btn)
        canvas.create_window(width - pad - 104, btn_y, anchor="nw",
                             window=remove_btn, width=104, height=btn_h)

        dialog.lift()
        dialog.focus_force()
        dialog.grab_set()
        self.root.wait_window(dialog)

    def _push_game_data(self):
        """Mirror a manual reclassification to the shared game list."""
        if not (self.gamesync and self.gamesync.enabled):
            return
        try:
            snapshot = self.classifier.snapshot()
        except Exception:
            return
        threading.Thread(target=lambda: self.gamesync.push(snapshot), daemon=True).start()

    # ---- Macropad ----
    # ---- Macropad (frame 2e) ----
    # The frame draws a CONNECTED 3x3 pad: "HID 0x1209:0xA1B2", a live key map,
    # drag-to-bind, a last-keypress readout. None of that layer exists - there
    # is no HID code anywhere in obsauto/ - so this page says so rather than
    # miming a keypad that does nothing. Same call v2 made, and the spec's own
    # build order puts Macropad last for this reason.
    #
    # Whoever builds it needs three things, in order: an HID input layer, a
    # persisted binding map in config.json, then this pane. Bindings must be by
    # SCAN CODE, not character - see toggle_hotkey_scancode and the vault's
    # asus-m4-fan-key note.
    def _build_macropad(self):
        (x, y, w, h), _ = self._view_panel(
            "Macropad", "Bind physical keys to Nebula actions.")
        self.bg.create_text(
            x + 24, y + 96, anchor="nw", width=w - 48,
            text="No device layer yet.\n\n"
                 "The design pairs Nebula with a 3x3 HID macropad: keys bound to "
                 "start/stop, pause, mark clip and scene switches, with per-game "
                 "profiles that follow whatever you launch.\n\n"
                 "Nothing here talks to hardware, so rather than show a mock keypad "
                 "that does nothing, this page stays empty until the binding layer "
                 "exists.",
            fill=MUTED, font=dv.type_font("body"))
        binding = self.config.get("toggle_hotkey") or "—"
        self.bg.create_text(
            x + 24, y + h - 56, anchor="nw", width=w - 48,
            text=f"Meanwhile the global hotkey  {binding}  toggles monitoring from "
                 "anywhere, bound by scan code so it can't swallow a neighbouring key.",
            fill=FAINT, font=dv.type_font("meta"))

    # ---- Settings (frame 2c) ----
    # v2 was read-only. This writes config.json, following the frame's rules:
    # write on blur (not per keystroke), the saved timestamp in the pane header,
    # a unit suffix on every *_seconds field, and the mono config-key caption
    # under every label - which is part of the design, not a debug aid.
    #
    # The fields come from obsauto/settings_spec.py rather than from
    # dv.CONFIG_MAP. That module arrived from a parallel Cursor branch and is
    # the better source: it is pure and testable without a Tk window, it covers
    # every key in config.DEFAULTS rather than only the thirteen the v3 table
    # lists, and each field carries validation bounds plus a `restart` reason
    # when a value can't be applied live. dv.CONFIG_MAP stays as the transcribed
    # spec table (test_design_v3 checks it against BUILD-SPEC.md); this pane
    # renders the superset, because a Settings page that cannot edit
    # github_token or nas_offload_root would be worse than one that departs
    # from the frame's five section names.
    #
    # WARNING: a text field costs one full window composite per keystroke on this
    # window. That is unavoidable for a text field, so the design spends exactly
    # that and no more: no live validation, no status updates while typing.
    # tests/test_settings_typing.py measures it - and note p50 frame time is
    # blind to it, because keystrokes are sparse relative to the heartbeat.

    def _build_settings(self):
        (x, y, w, h), sub = self._view_panel("Settings", "Writes config.json on blur")
        self._settings_sub = sub
        self._settings_saved_at = None
        self._settings_fields = {}          # key -> (widget, field)

        self._view_button(x + w - 136, y + 20, 116, "Open config",
                          self._open_config_file)
        self._view_button(x + w - 262, y + 20, 116, "Open logs",
                          self._open_logs_folder)

        self._settings_group = settings_spec.GROUPS[0][0]
        self._settings_nav = {}
        ny = y + 78
        for key, title, _blurb in settings_spec.GROUPS:
            self._settings_nav[key] = self._settings_nav_item(x + 20, ny, 172, 34, title, key)
            ny += 38

        bx, by = x + 208, y + 76
        bw, bh = w - 232, h - 92
        # _scroll_list, not a bare CTkScrollableFrame: the latter cannot go into
        # canvas.create_window() ("can't use ... in a window item of this canvas").
        self._settings_host = self._scroll_list(bx, by, bw, bh)
        self._render_settings_group()

    def _settings_nav_item(self, x, y, w, h, title, key):
        tile = self._glass(x, y, w, h, tint=ACCENT, radius=dv.RADIUS_CONTROL,
                           tint_alpha=36, border_alpha=0)
        label = self.bg.create_text(x + 14, y + h / 2, anchor="w", text=title,
                                    fill=MUTED, font=dv.type_font("body"))
        hit = self.bg.create_rectangle(x, y, x + w, y + h, fill="", outline="")
        for item in (hit, label):
            self.bg.tag_bind(item, "<Button-1>",
                             lambda _e, k=key: self._show_settings_group(k))
            self.bg.tag_bind(item, "<Enter>", lambda _e: self.bg.configure(cursor="hand2"))
            self.bg.tag_bind(item, "<Leave>", lambda _e=None: self.bg.configure(cursor=""))
        return {"tile": tile, "text": label}

    def _show_settings_group(self, key):
        self._settings_group = key
        self._render_settings_group()

    def _render_settings_group(self):
        for key, parts in self._settings_nav.items():
            active = key == self._settings_group
            self.bg.itemconfigure(parts["tile"], state="normal" if active else "hidden")
            self.bg.itemconfigure(parts["text"], fill=NAV_ACTIVE_TEXT if active else MUTED)

        for child in self._settings_host.winfo_children():
            child.destroy()
        self._settings_fields = {}
        self._settings_obs_footer_label = None
        self._settings_sync_label = None

        blurb = next((b for k, _t, b in settings_spec.GROUPS if k == self._settings_group), "")
        if blurb:
            ctk.CTkLabel(self._settings_host, text=blurb, anchor="w", justify="left",
                         wraplength=520, text_color=FAINT,
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(10, 2))
        for field in settings_spec.fields_in(self._settings_group):
            self._settings_field(field)
        if self._settings_group == "obs":
            self._build_settings_obs_footer()
        elif self._settings_group == "updates":
            self._build_settings_updates_footer()
        elif self._settings_group == "offload" and not thumbs.available():
            # 7f: "If ffmpeg isn't on PATH, show one dismissible row in
            # Settings → Storage offering the download - not a modal, not a
            # toast per clip. Everything else keeps working."
            self._build_ffmpeg_notice()

        if self._settings_group in ("gamesync", "offload"):
            # 6.3: "Sync status belongs in Settings -> Sync."
            if self._settings_group == "offload":
                self._build_settings_offload_footer()
            else:
                self._settings_sync_label = ctk.CTkLabel(
                    self._settings_host, text=self._sync_status_text(), anchor="w",
                    justify="left", wraplength=520, text_color=ACCENT_LIGHT,
                    font=ctk.CTkFont(size=12))
                self._settings_sync_label.pack(anchor="w", padx=12, pady=(16, 12))
                self._settings_offload_btn = None

    def _build_settings_offload_footer(self):
        """NAS status card + Sync now — queue depth, Tailscale, last run."""
        foot = ctk.CTkFrame(self._settings_host, fg_color=dv.over(ACCENT, 0.07, dv.CARD_CORE),
                            corner_radius=dv.RADIUS_TILE, border_width=1,
                            border_color=dv.over(ACCENT, 0.18, dv.CARD_CORE))
        foot.pack(fill="x", padx=12, pady=(16, 12))
        self._settings_sync_label = ctk.CTkLabel(
            foot, text=self._sync_status_text(), anchor="w", justify="left",
            wraplength=400, text_color=ACCENT_LIGHT, font=ctk.CTkFont(size=12))
        self._settings_sync_label.pack(side="left", padx=14, pady=10, fill="x", expand=True)
        self._settings_offload_btn = ctk.CTkButton(
            foot, text="Sync now", command=self._sync_offload_now,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=TEXT,
            border_width=1, border_color=dv.over(ACCENT, 0.42, dv.CARD_CORE),
            corner_radius=999, font=ctk.CTkFont(size=12), width=110, height=34)
        self._focus_ring(self._settings_offload_btn)
        self._settings_offload_btn.pack(side="right", padx=8, pady=8)
        if not (self.offloader and self.offloader.enabled):
            try:
                self._settings_offload_btn.configure(state="disabled")
            except Exception:
                pass

    def _sync_offload_now(self):
        if getattr(self, "_offload_sync_busy", False):
            return
        if not self.offloader or not self.offloader.enabled:
            return
        self._offload_sync_busy = True
        btn = getattr(self, "_settings_offload_btn", None)
        if btn is not None:
            try:
                btn.configure(state="disabled", text="Syncing…")
            except Exception:
                pass
        self._log("[Offload] Sync now…")

        def worker():
            try:
                result = self.offloader.sync_now(
                    self.config.get("recording_root"))
            except Exception as exc:
                result = {"ok": False, "message": str(exc)}
            self.root.after(0, lambda r=result: self._sync_offload_now_done(r))

        threading.Thread(target=worker, daemon=True).start()

    def _sync_offload_now_done(self, result):
        self._offload_sync_busy = False
        msg = result.get("message") or ("Done." if result.get("ok") else "Sync failed.")
        self._log("[Offload] %s" % msg)
        btn = getattr(self, "_settings_offload_btn", None)
        if btn is not None:
            try:
                btn.configure(state="normal", text="Sync now")
            except Exception:
                pass
        self._refresh_sync_status()
        self._toast_replace("start" if result.get("ok") else "error", msg)

    def _build_ffmpeg_notice(self):
        """One dismissible row offering the ffmpeg download (7f).

        Dismissal is remembered in config, so it really is one row and not a
        nag - thumbnails and the Length column simply stay absent.
        """
        if self.config.get("ffmpeg_notice_dismissed"):
            return
        bar = ctk.CTkFrame(self._settings_host,
                           fg_color=dv.over(ACCENT, 0.07, dv.CARD_CORE),
                           corner_radius=dv.RADIUS_TILE, border_width=1,
                           border_color=dv.over(ACCENT, 0.18, dv.CARD_CORE))
        bar.pack(fill="x", padx=12, pady=(16, 4))
        ctk.CTkLabel(
            bar, anchor="w", justify="left", wraplength=430, text_color=MUTED,
            font=ctk.CTkFont(size=12),
            text=("ffmpeg isn't on PATH, so clips have no thumbnails and no "
                  "Length. Everything else works. Install it with "
                  "\"winget install Gyan.FFmpeg\" and restart Nebula."),
        ).pack(side="left", padx=14, pady=10)

        def dismiss():
            self.config["ffmpeg_notice_dismissed"] = True
            from .config import save_config
            save_config(self.config)
            bar.destroy()

        ctk.CTkButton(bar, text="Dismiss", command=dismiss, width=84, height=30,
                      fg_color="transparent", hover_color=SURFACE_HOVER,
                      text_color=MUTED, border_width=1, border_color=EDGE,
                      corner_radius=999,
                      font=ctk.CTkFont(size=12)).pack(side="right", padx=8, pady=8)

    def _build_settings_obs_footer(self):
        """Frame 2c: ``Connected to OBS 30.2 — handshake 41 ms`` + Test again.

        Every figure is real — version from GetVersion, handshake from the last
        successful Hello→Identified. Nothing is drawn until both exist.
        """
        foot = ctk.CTkFrame(self._settings_host, fg_color=dv.over(ACCENT, 0.07, dv.CARD_CORE),
                            corner_radius=dv.RADIUS_TILE, border_width=1,
                            border_color=dv.over(ACCENT, 0.18, dv.CARD_CORE))
        foot.pack(fill="x", padx=12, pady=(16, 12))
        self._settings_obs_footer_label = ctk.CTkLabel(
            foot, text="", anchor="w", text_color=ACCENT_LIGHT,
            font=ctk.CTkFont(size=12))
        self._settings_obs_footer_label.pack(side="left", padx=14, pady=10)
        test = ctk.CTkButton(
            foot, text="Test again", command=self._start,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=TEXT,
            border_width=1, border_color=dv.over(ACCENT, 0.42, dv.CARD_CORE),
            corner_radius=999, font=ctk.CTkFont(size=12), width=110, height=34)
        self._focus_ring(test)
        test.pack(side="right", padx=8, pady=8)
        self._refresh_settings_obs_footer()

    def _build_settings_updates_footer(self):
        """Check Releases (exe) or Save / Load origin/main (source)."""
        from . import updater as updater_mod
        from .version import display_version

        foot = ctk.CTkFrame(self._settings_host, fg_color=dv.over(ACCENT, 0.07, dv.CARD_CORE),
                            corner_radius=dv.RADIUS_TILE, border_width=1,
                            border_color=dv.over(ACCENT, 0.18, dv.CARD_CORE))
        foot.pack(fill="x", padx=12, pady=(16, 12))
        label = display_version()
        if updater_mod.is_frozen():
            blurb = (f"Running Nebula {label} (packaged). Check GitHub "
                     "Releases — Install & relaunch replaces this exe.")
        else:
            blurb = (f"Running Nebula {label}. Save this machine before you "
                     "leave; Load latest when you sit down, then restart.")
        self._settings_updates_label = ctk.CTkLabel(
            foot, text=blurb, anchor="w", justify="left", wraplength=360,
            text_color=ACCENT_LIGHT, font=ctk.CTkFont(size=12))
        self._settings_updates_label.pack(side="left", padx=14, pady=10, fill="x",
                                          expand=True)
        ghost = dict(
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=TEXT,
            border_width=1, border_color=dv.over(ACCENT, 0.42, dv.CARD_CORE),
            corner_radius=999, font=ctk.CTkFont(size=12), height=34)
        check = ctk.CTkButton(
            foot, text="Check for updates", command=self._check_for_updates,
            width=140, **ghost)
        self._focus_ring(check)
        if updater_mod.is_frozen():
            check.pack(side="right", padx=8, pady=8)
            return
        save = ctk.CTkButton(
            foot, text="Save this machine", command=self._save_source_update,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT,
            corner_radius=999, font=ctk.CTkFont(size=12), width=150, height=34)
        self._focus_ring(save)
        load = ctk.CTkButton(
            foot, text="Load latest", command=self._load_source_update,
            width=110, **ghost)
        self._focus_ring(load)
        # pack side=right: first packed is rightmost → Save, Load, Check
        save.pack(side="right", padx=(4, 8), pady=8)
        load.pack(side="right", padx=4, pady=8)
        check.pack(side="right", padx=4, pady=8)

    def _check_for_updates(self):
        """Worker → toast. Never blocks the Tk thread on GitHub."""
        if getattr(self, "_update_check_busy", False):
            return
        self._update_check_busy = True
        label = getattr(self, "_settings_updates_label", None)
        if label is not None:
            try:
                label.configure(text="Checking GitHub…")
            except Exception:
                pass

        def worker():
            from . import updater as updater_mod
            outcome = {"ok": False, "status": None, "message": "", "release": None}
            try:
                result = updater_mod.check_for_update(
                    token=self.config.get("github_token") or None)
                outcome["ok"] = True
                outcome["status"] = result["status"]
                outcome["release"] = result.get("release") or {}
                rel = outcome["release"]
                tag = rel.get("tag") or rel.get("version") or "?"
                msg = result.get("message") or ""
                if not msg:
                    if result["status"] == "current":
                        msg = f"You're on the latest ({result['local']})."
                    elif result["status"] == "no_asset":
                        msg = (
                            f"{tag} is on GitHub but has no .exe asset yet — "
                            "open the release page or Load latest.")
                    else:
                        msg = (
                            f"{tag} is available (you have {result['local']}).")
                outcome["message"] = msg
            except Exception as exc:
                outcome["message"] = f"Update check failed: {exc}"
            self.root.after(0, lambda o=outcome: self._check_for_updates_done(o))

        threading.Thread(target=worker, daemon=True).start()

    def _check_for_updates_done(self, outcome):
        self._update_check_busy = False
        label = getattr(self, "_settings_updates_label", None)
        if label is not None:
            try:
                label.configure(text=outcome["message"])
            except Exception:
                pass
        status = outcome.get("status")
        if not outcome["ok"]:
            self._toast_replace("error", outcome["message"])
            return
        if status == "current":
            self._toast_replace("pause", outcome["message"])
            return
        if status == "no_asset":
            self._toast_replace("pause", outcome["message"])
            return

        # Update available — offer download for frozen builds.
        from . import updater as updater_mod
        release = outcome["release"] or {}
        tag = release.get("tag") or "update"

        def open_page():
            import webbrowser
            url = release.get("html_url") or "https://github.com/theoriginalcheese/nebula/releases/latest"
            webbrowser.open(url)
            self._toast_dismiss_now()

        actions = [("Open release", open_page)]
        if updater_mod.is_frozen() and release.get("asset_url"):
            def install():
                self._toast_dismiss_now()
                self._install_update(release)

            actions.insert(0, ("Install & relaunch", install))
        elif not updater_mod.is_frozen() and updater_mod.source_checkout_root():
            def load():
                self._toast_dismiss_now()
                self._load_source_update()

            actions.insert(0, ("Load latest", load))
        self._toast_replace(
            "prompt", tag, {"title": "Update available"},
            actions=actions,
        )

    def _pull_source_update(self):
        self._load_source_update()

    def _load_source_update(self):
        self._run_source_snapshot("load", "Loading latest…")

    def _save_source_update(self):
        self._run_source_snapshot("save", "Saving this machine…")

    def _run_source_snapshot(self, action, waiting):
        if getattr(self, "_update_download_busy", False):
            return
        self._update_download_busy = True
        self._log("[Update] %s" % waiting)
        self._toast_replace("pause", waiting)

        def worker():
            from . import updater as updater_mod
            if action == "save":
                result = updater_mod.save_source_snapshot()
            else:
                result = updater_mod.load_source_snapshot()
            self.root.after(0, lambda r=result: self._source_snapshot_done(r))

        threading.Thread(target=worker, daemon=True).start()

    def _source_snapshot_done(self, result):
        self._update_download_busy = False
        msg = result.get("message") or (
            "Done." if result.get("ok") else "Update failed.")
        self._log("[Update] %s" % msg)
        label = getattr(self, "_settings_updates_label", None)
        if label is not None:
            try:
                label.configure(text=msg)
            except Exception:
                pass
        self._toast_replace("start" if result.get("ok") else "error", msg)

    def _pull_source_update_done(self, result):
        self._source_snapshot_done(result)

    def _install_update(self, release):
        if getattr(self, "_update_download_busy", False):
            return
        self._update_download_busy = True
        self._log(f"[Update] Downloading {release.get('asset_name')}…")
        self._toast_replace("pause", "Downloading update…")

        def worker():
            from . import updater as updater_mod
            result = {"ok": False, "path": None, "message": ""}
            try:
                dest = updater_mod.default_download_path(release.get("asset_name"))
                path = updater_mod.download_update(
                    release["asset_url"], dest,
                    token=self.config.get("github_token") or None)
                updater_mod.install_and_relaunch(path)
                result.update(
                    ok=True, path=path,
                    message="Installing — Nebula will restart.")
            except Exception as exc:
                result["message"] = f"Install failed: {exc}"
            self.root.after(0, lambda r=result: self._install_update_done(r))

        threading.Thread(target=worker, daemon=True).start()

    def _install_update_done(self, result):
        self._update_download_busy = False
        if result["ok"]:
            self._log(f"[Update] {result['message']}")
            self._toast_replace("start", result["message"])
            label = getattr(self, "_settings_updates_label", None)
            if label is not None:
                try:
                    label.configure(text=result["message"])
                except Exception:
                    pass
            # Helper is waiting for this process to exit.
            self.root.after(400, self.quit)
        else:
            self._log(f"[Update] {result['message']}")
            self._toast_replace("error", result["message"])

    def _download_update(self, release):
        if getattr(self, "_update_download_busy", False):
            return
        self._update_download_busy = True
        self._log(f"[Update] Downloading {release.get('asset_name')}…")
        self._toast_replace("pause", "Downloading update…")

        def worker():
            from . import updater as updater_mod
            result = {"ok": False, "path": None, "message": ""}
            try:
                dest = updater_mod.default_download_path(release.get("asset_name"))
                path = updater_mod.download_update(
                    release["asset_url"], dest,
                    token=self.config.get("github_token") or None)
                result.update(ok=True, path=path,
                              message=f"Saved to {path}. Quit Nebula and swap the exe.")
            except Exception as exc:
                result["message"] = f"Download failed: {exc}"
            self.root.after(0, lambda r=result: self._download_update_done(r))

        threading.Thread(target=worker, daemon=True).start()

    def _download_update_done(self, result):
        self._update_download_busy = False
        if result["ok"]:
            self._log(f"[Update] {result['message']}")
            self._toast_replace("start", result["message"])
            label = getattr(self, "_settings_updates_label", None)
            if label is not None:
                try:
                    label.configure(text=result["message"])
                except Exception:
                    pass
        else:
            self._log(f"[Update] {result['message']}")
            self._toast_replace("error", result["message"])

    def _refresh_settings_obs_footer(self):
        label = getattr(self, "_settings_obs_footer_label", None)
        if label is None:
            return
        try:
            if not label.winfo_exists():
                return
        except Exception:
            return
        if self._obs_connected and self._obs_version and self._handshake_ms is not None:
            text = (f"Connected to OBS {self._obs_version} — "
                    f"handshake {self._handshake_ms} ms")
        elif self._obs_connected and self._obs_version:
            text = f"Connected to OBS {self._obs_version}"
        elif self._obs_connected:
            text = "Connected to OBS"
        else:
            text = "Not connected to OBS"
        label.configure(text=text)

    def _settings_field(self, field):
        row = ctk.CTkFrame(self._settings_host, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(8, 2))

        head = ctk.CTkFrame(row, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=field.label, anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(size=12)).pack(side="left")
        # The config key in mono under the label - part of the design.
        ctk.CTkLabel(head, text=field.key, anchor="w", text_color=FAINT,
                     font=ctk.CTkFont(family="Consolas", size=10)).pack(side="left", padx=8)
        if field.key.endswith("_seconds"):
            ctk.CTkLabel(head, text="seconds", text_color=FAINT,
                         font=ctk.CTkFont(size=10)).pack(side="right")

        value = self.config.get(field.key)
        if field.kind == "choice":
            widget = ctk.CTkOptionMenu(
                row, values=list(field.choices), fg_color=SURFACE,
                button_color=SURFACE, button_hover_color=SURFACE_HOVER,
                text_color=TEXT, corner_radius=dv.RADIUS_CONTROL,
                font=ctk.CTkFont(size=12),
                command=lambda _v, k=field.key: self._settings_commit(k))
            widget.set(settings_spec.render(field, value) or field.choices[0])
            widget.pack(anchor="w", pady=(4, 0))
        else:
            widget = ctk.CTkEntry(
                row, fg_color=dv.GROUND, border_color=EDGE, border_width=1,
                text_color=TEXT, corner_radius=dv.RADIUS_CONTROL, height=30,
                font=ctk.CTkFont(family="Consolas", size=12),
                show="*" if field.kind == "secret" else "")
            widget.insert(0, settings_spec.render(field, value))
            widget.pack(fill="x", pady=(4, 0))
            # "Write on blur, not per keystroke." Return commits too, so a field
            # you finish typing in doesn't need defocusing first.
            widget.bind("<FocusOut>", lambda _e, k=field.key: self._settings_commit(k))
            widget.bind("<Return>", lambda _e, k=field.key: self._settings_commit(k))

        hint = field.hint
        if field.restart:
            hint = (hint + "  " if hint else "") + f"Takes effect after a restart — {field.restart}."
        if hint:
            ctk.CTkLabel(row, text=hint, anchor="w", justify="left", wraplength=520,
                         text_color=FAINT, font=ctk.CTkFont(size=10)).pack(
                anchor="w", pady=(2, 0))

        self._settings_fields[field.key] = (widget, field)

    def _settings_commit(self, key):
        widget, field = self._settings_fields[key]
        old = self.config.get(key)
        value, error = settings_spec.parse(field, widget.get())
        if error:
            # Put the stored value back rather than writing nonsense. Reported
            # to the log, not inline, so typing stays one composite per key.
            if field.kind != "choice":
                widget.delete(0, "end")
                widget.insert(0, settings_spec.render(field, old))
            self._log(f"[Manual] {field.label}: {error} — kept {old!r}")
            return
        if value == old:
            return
        self.config[key] = value
        self._save_settings()
        self._log(f"[Manual] {key} = {value!r}")
        self._settings_apply_live(key, value)

    def _settings_apply_live(self, key, value):
        """Push an edited value into the object that owns it.

        Most config is read live off the shared dict, so nothing is needed. The
        exceptions are the objects holding OS-level or cached state: a hotkey
        hook must be taken down before a new one is bound (a lingering
        suppress=True hook keeps swallowing the old key system-wide), and the
        offload worker needs waking so a queue that backed off against an
        unreachable root retries at once. Fields that genuinely can't apply live
        carry a `restart` reason and say so under the field.
        """
        try:
            # Any of the three global keys - _register_hotkey rebinds all of
            # them together. replay_* and palette_hotkey were missing here, so
            # changing them did nothing at all while the field claimed (via
            # restart=False) that it applied live.
            if key in ("toggle_hotkey", "toggle_hotkey_scancode",
                       "replay_hotkey", "replay_hotkey_scancode",
                       "replay_enabled", "palette_hotkey"):
                self._register_hotkey()
            elif key.startswith("nas_offload") and self.offloader:
                self.offloader.refresh()
            elif key == "keep_alive_audio_processes":
                keepalive = getattr(self.monitor, "audio_keepalive", None)
                if keepalive and hasattr(keepalive, "set_processes"):
                    keepalive.set_processes(value)
            elif key.startswith("github_") and self.gamesync:
                self.gamesync.configure(self.config)
        except Exception as exc:
            error = exc
            self._log(f"[Manual] Couldn't apply {key} live: {error}")

    def _save_settings(self):
        """Merge over DEFAULTS and keep everything else.

        load_config() starts from DEFAULTS and updates from the file, so
        self.config carries any key a hand-edited config.json had - including
        ones this app has never heard of. Writing it back whole is what keeps
        "never silently drop an unknown key" true.
        """
        from .config import save_config
        try:
            save_config(self.config)
        except OSError as exc:
            error = exc
            self._log(f"[Manual] Couldn't write config.json: {error}")
            return
        self._settings_saved_at = time.strftime("%H:%M:%S")
        self.bg.itemconfigure(
            self._settings_sub,
            text=f"Writes config.json on blur  ·  Saved {self._settings_saved_at}")

    def _open_config_file(self):
        from .paths import APP_DIR
        self._open_path(os.path.join(APP_DIR, "config.json"))

    def _open_logs_folder(self):
        from .paths import APP_DIR
        self._open_path(os.path.join(APP_DIR, "logs"))

    # ---- hero recording card (frames 2a, 2f-2h) ----
    # "Only the hero card changes; nothing else on the dashboard moves. Same
    # 22px padding, same button row position - swap the eyebrow, the tint, and
    # the primary action." So this builds one card and _set_hero_state swaps
    # four states through it; nothing here is rebuilt on a state change.
    def _build_hero(self, x, y, w):
        # The hero always spans the full content width (its internal layout -
        # readouts on the left, scene preview pinned right - is tuned for it), so
        # the grid only ever varies its y. h is fixed.
        h = HERO_H
        pad = dv.HERO_PAD
        bezel = dv.CARD_LAYERS["hero"][1]

        # 22 / 5 / 17 out of the nesting table. "Every card is two layers:
        # tinted outer shell, darker inner core. A flat card is a bug."
        self._status_card_geom = (x, y, w, h)   # reused by _flash_status_card
        self._status_card_item, _core, self._hero_core_geom = self._card(
            x, y, w, h, kind="hero")

        left_x = x + bezel + pad
        preview_w = 340
        preview_h = int(preview_w * 9 / 16)          # the spec's 16/9 tile
        preview_x = x + w - bezel - pad - preview_w
        preview_y = y + bezel + pad
        left_w = preview_x - 22 - left_x

        # --- eyebrow badge (the state pill) ---
        self._hero_badge_geom = (left_x, y + pad + 2, 128, 22)
        self._hero_badge_item = self._glass(left_x, y + pad + 2, 128, 22, tint=ACCENT,
                                            radius=7, tint_alpha=40, border_alpha=0)
        self.rec_dot_id = self.bg.create_text(
            left_x + 13, y + pad + 13, text=ICON_GLYPHS["record"],
            fill=ACCENT, font=(ICON_FONT, -7))
        self._hero_badge_text = self.bg.create_text(
            left_x + 26, y + pad + 13, anchor="w", text=self._track("Watching"),
            fill=ACCENT_LIGHT, font=dv.type_font("eyebrow"))
        self._hero_sub_id = self.bg.create_text(
            left_x + 142, y + pad + 13, anchor="w", text="", fill=MUTED,
            font=dv.type_font("meta"))

        # --- game title + its source line ---
        self.game_label_id = self.bg.create_text(
            left_x, y + 74, anchor="w", text="No game detected",
            fill=MUTED, font=dv.type_font("game_title"))
        self._hero_source_id = self.bg.create_text(
            left_x, y + 98, anchor="w", text="", fill=FAINT,
            font=dv.font(11, mono=True), width=left_w)

        # No folder chip. 6.6's idle-hero table is explicit - "Path field: rail
        # footer only, not in the hero" - and the rail footer already carries
        # the recording root with its fill bar, as 2a draws it.

        # --- the three readouts: Elapsed / File size / Bitrate ---
        # Every one is real. Elapsed and File size come straight from OBS's
        # GetRecordStatus; Bitrate is computed from successive polls of it
        # (see _poll_obs_status) rather than being drawn in as a number.
        self._readouts = {}
        col_w = left_w / 3.0
        for i, (key, label) in enumerate((("elapsed", "Elapsed"),
                                          ("size", "File size"),
                                          ("bitrate", "Bitrate"))):
            rx = left_x + i * col_w
            cap = self.bg.create_text(rx, y + 168, anchor="w", text=self._track(label),
                                      fill=FAINT, font=dv.type_font("eyebrow"))
            val = self.bg.create_text(
                rx, y + 192, anchor="w", text="--",
                fill=TEXT, font=dv.font(dv.TYPE["timer"]["size"] if key == "elapsed" else 19,
                                        mono=True))
            self._readouts[key] = (cap, val)
        # Kept under the old names - _poll_obs_status and the tests use them.
        self.timer_label_id = self._readouts["elapsed"][1]
        self.storage_label_id = self._readouts["size"][1]
        self._elapsed_label_id = self._readouts["elapsed"][0]
        self._size_label_id = self._readouts["size"][0]

        # Shown instead of the readouts while nothing is being recorded, so the
        # card reads as calm-and-ready rather than simply empty.
        self._hero_hint_id = self.bg.create_text(
            left_x, y + 180, anchor="w", text="", fill=FAINT,
            font=dv.type_font("body"), width=left_w)

        # --- transport buttons ---
        # Two, not the frame's three: "Mark clip" has no backend, and a button
        # that silently does nothing is worse than an absent one. Same reason v2
        # dropped it. Both buttons are relabelled and rebound per state by
        # _set_hero_state - that is what "one state enum" means here.
        bt_y = y + h - bezel - pad - 40
        self._hero_primary_cmd = self._toggle_record
        self._hero_primary_text = ACCENT_LIGHT
        self._hero_secondary_cmd = self._toggle_pause
        self.record_toggle_btn = ctk.CTkButton(
            self.root, text="Record now", command=lambda: self._hero_primary_cmd(),
            state="disabled",
            fg_color=GREEN_TINT, hover_color=GREEN_TINT_HOVER, text_color=ACCENT_LIGHT,
            bg_color=self._bg_at(left_x + 78, bt_y + 20), border_width=1,
            border_color=ACCENT, corner_radius=dv.RADIUS_CONTROL,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._focus_ring(self.record_toggle_btn, resting_border=ACCENT)
        self._record_btn_win = self.bg.create_window(
            left_x, bt_y, anchor="nw", window=self.record_toggle_btn, width=180, height=dv.CONTROL_PILL_H)
        self._dashboard_widgets.append(self.record_toggle_btn)
        self.pause_btn = ctk.CTkButton(
            self.root, text="Pause", command=lambda: self._hero_secondary_cmd(),
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(left_x + 174 + 60, bt_y + 20), border_width=1,
            border_color=EDGE, corner_radius=dv.RADIUS_CONTROL,
            font=ctk.CTkFont(size=13),
        )
        self._focus_ring(self.pause_btn)
        self._pause_btn_win = self.bg.create_window(
            left_x + 190, bt_y, anchor="nw", window=self.pause_btn, width=150,
            height=dv.CONTROL_PILL_H)
        self._dashboard_widgets.append(self.pause_btn)

        # --- scene preview + info row (right column) ---
        self._build_preview(preview_x, preview_y, preview_w, preview_h)
        self._preview_geom = (preview_x, preview_y, preview_w, preview_h)
        info_y = preview_y + preview_h + 10
        self._glass(preview_x, info_y, preview_w, 36, tint=CARD_TINT,
                    radius=dv.RADIUS_TILE, tint_alpha=120,
                    border_hex=CARD_BORDER, border_alpha=26)
        self.bg.create_text(preview_x + 14, info_y + 18, anchor="w",
                            text=ICON_GLYPHS[dv.ICONS["scene"]],
                            fill=ACCENT, font=(ICON_FONT, -12))
        self._preview_info_id = self.bg.create_text(
            preview_x + 34, info_y + 18, anchor="w",
            text="Scene capture idle", fill=TEXT_SOFT, font=dv.type_font("meta"))

        self._set_hero_state("disconnected")

    def _build_preview(self, x, y, w, h):
        """A stylised 16:9 'scene preview' tile - a violet gradient stand-in for
        the live capture (rendering real OBS frames is out of scope), with the
        source label and a little equaliser that comes alive while recording."""
        tile = self._make_preview_tile(w, h)
        photo = to_photo(tile)
        self._keep_image(photo)
        self.bg.create_image(x, y, anchor="nw", image=photo)

        # Source label chip, top-left. Scene name is filled in once OBS answers
        # GetCurrentProgramScene — never a fabricated "Game Capture" string.
        self._glass(x + 12, y + 12, 168, 24, tint=BASE_BG, radius=8,
                    tint_alpha=150, border_alpha=0)
        self._preview_dot_id = self.bg.create_text(x + 22, y + 24, anchor="w", text=ICON_GLYPHS["record"],
                                                   fill=FAINT, font=(ICON_FONT, -8))
        self._preview_scene_chip = self.bg.create_text(
            x + 34, y + 24, anchor="w", text="OBS scene",
            fill=NAV_ACTIVE_TEXT, font=dv.font(10, 500))

        # The centred placeholder label. 6.6's accepted version has one - "it is
        # a dark placeholder WITH A LABEL" - and without it the tile is just an
        # empty box with two chips floating in it. Tracked out by hand because
        # Tk has no letter-spacing (see _track), against the ramp's mid stop.
        self._preview_label_id = self.bg.create_text(
            x + w / 2, y + h / 2, anchor="center",
            text=self._track("Scene preview".upper()),
            fill=dv.over(dv.TEXT, 0.45, self.PREVIEW_STOPS[1][1]),
            font=dv.font(9.5, 500))

        # Res/fps chip (frame 2a: ``2560×1440 · 60 fps``). Blank until
        # GetVideoSettings arrives — never a placeholder resolution.
        self._preview_video_id = self.bg.create_text(
            x + w - 12, y + h - 14, anchor="se", text="",
            fill=ACCENT_LIGHT, font=dv.font(10, mono=True))

        # 6.6: "The build filled the preview with a bright violet gradient and
        # invented audio bars." The eleven-bar equaliser that used to sit here
        # was a fixed sine waveform - it looked like a level meter and metered
        # nothing. There is no audio source behind it, so it is gone rather
        # than faked. The equaliser list stays as an empty tuple because
        # _set_hero_state still iterates it.
        self._eq_bars = ()

    # mockup 6.6, the *good* half: linear-gradient(140deg, #241E44 0%,
    # #2E2358 46%, #5340A8 100%) under radial-gradient(90% 80% at 30% 20%,
    # rgba(245,243,255,0.10), transparent 70%), 1px rgba(245,243,255,0.09).
    PREVIEW_STOPS = ((0.0, "#241E44"), (0.46, "#2E2358"), (1.0, "#5340A8"))
    PREVIEW_ANGLE = 140
    PREVIEW_SHEEN = (0.30, 0.20, 0.90, 0.80, 0.10, 0.70)  # cx cy rx ry alpha fade

    def _make_preview_tile(self, w, h):
        """The scene placeholder: a dark tile, not a lit one.

        6.6 again - "When there is no frame to show, it is a dark placeholder
        with a label. Bright flat fills fight the aurora and blow out the only
        ember cue." A live frame would mean polling GetSourceScreenshot on a
        timer, which is one full window composite per tick and therefore fatal
        here, so the placeholder is what the pane shows.

        What 6.6 objects to is the *bright flat fill* and the invented audio
        bars, not depth - its own accepted version is a diagonal ramp with a
        soft highlight and a centred label. This had kept the darkness and
        dropped all three, which is how the panel ended up an empty black box:
        the other way to fail the same frame. The ramp tops out at #5340A8, a
        raised surface tone, so nothing here outshines the ember cue.

        Both gradients are the lowest-frequency thing in the pane, so they are
        painted at 96x54 and upscaled - the ground gradient's trick.
        """
        sw, sh = self._S(w), self._S(h)
        gw, gh = 96, 54
        grad = Image.new("RGB", (gw, gh))
        px = grad.load()
        stops = [(at, (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)))
                 for at, c in self.PREVIEW_STOPS]
        # CSS 0deg points up and turns clockwise, so 140deg runs down-and-right.
        # Both components come out positive, which puts t=0 at the top-left
        # corner and t=1 at the bottom-right - no origin offset needed.
        ax = math.sin(math.radians(self.PREVIEW_ANGLE))
        ay = -math.cos(math.radians(self.PREVIEW_ANGLE))
        length = abs(gw * ax) + abs(gh * ay)
        hx, hy, hrx, hry, ha, hfade = self.PREVIEW_SHEEN
        for y in range(gh):
            for x in range(gw):
                t = min(1.0, max(0.0, ((x + 0.5) * ax + (y + 0.5) * ay) / length))
                for i in range(len(stops) - 1):
                    at0, c0 = stops[i]
                    at1, c1 = stops[i + 1]
                    if t <= at1 or i == len(stops) - 2:
                        k = (t - at0) / (at1 - at0) if at1 > at0 else 0.0
                        k = min(1.0, max(0.0, k))
                        col = [c0[j] + (c1[j] - c0[j]) * k for j in range(3)]
                        break
                dx = ((x + 0.5) / gw - hx) / hrx
                dy = ((y + 0.5) / gh - hy) / hry
                lit = ha * max(0.0, 1.0 - (dx * dx + dy * dy) ** 0.5 / hfade)
                sheen = (245, 243, 255)
                px[x, y] = tuple(int(round(col[j] + (sheen[j] - col[j]) * lit))
                                 for j in range(3))
        img = grad.resize((sw, sh), Image.BICUBIC).convert("RGBA")
        radius = self._S(13)
        # The hairline, composited rather than stroked opaque - it has to read
        # as an edge on glass, not as a drawn outline.
        edge = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        ImageDraw.Draw(edge).rounded_rectangle(
            [0, 0, sw - 1, sh - 1], radius=radius, fill=None,
            outline=(245, 243, 255, int(round(0.09 * 255))), width=1)
        img = Image.alpha_composite(img, edge)
        mask = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, sw - 1, sh - 1], radius=radius, fill=255)
        img.putalpha(mask)
        return img

    def _adopt_view_items(self, view, items, extra_tags=()):
        """Tag freshly-created canvas items into a view, and hide them if that
        view isn't the one on screen.

        `_show_view` hides a view by setting state on the items that exist at
        that moment. Anything drawn *afterwards* is born with state="normal",
        so a refresh that runs while another pane is showing paints straight
        over it - which is how the Clips pane's session ribbon ended up drawn
        across the Dashboard's hero card, and how the replay module's rows
        could appear over Clips (the bitrate poll refreshes it every second
        while recording).
        """
        state = "normal" if self._current_view == view else "hidden"
        for item in items:
            self.bg.addtag_withtag(f"view_{view}", item)
            for tag in extra_tags:
                self.bg.addtag_withtag(tag, item)
            self.bg.itemconfigure(item, state=state)

    def _hero_vis(self, want_visible):
        """"normal" only if the hero is actually on screen.

        _set_hero_state un-hides the readouts and the transport buttons, and
        _poll_obs_status calls it once a second - so while a recording ran, the
        elapsed timer, file size, bitrate and the Pause button reappeared on
        top of whatever pane you had navigated to. _show_view hides them once;
        the very next poll put them straight back.

        Every visibility change on a hero item goes through here, so the answer
        is always "is the dashboard showing?" rather than a hidden state that
        one code path happens to respect.
        """
        return "normal" if (want_visible and self._current_view == "dashboard") else "hidden"

    def _keep_image(self, photo):
        """Hold a PhotoImage against Tk's garbage collector.

        Goes into the active scope if one is open, so a surface that rebuilds
        itself doesn't pin every generation it has ever drawn.
        """
        sink = self._image_sink
        (self._images if sink is None else sink).append(photo)
        return photo

    @contextlib.contextmanager
    def _image_scope(self, name):
        """Images drawn inside this block replace the previous generation.

        The canvas items from the last pass have already been deleted by the
        caller, so nothing on screen is referencing those images any more -
        dropping them is what returns the bitmaps to Windows.
        """
        attr = f"_images_{name}"
        setattr(self, attr, [])                 # releases the previous list
        previous, self._image_sink = self._image_sink, getattr(self, attr)
        try:
            yield
        finally:
            self._image_sink = previous

    def _hero_present(self):
        """Is the hero card actually built right now?

        6.8's catalogue lets any module be removed, the hero included - and
        when it goes, its widgets are destroyed while _poll_obs_status carries
        on calling _set_hero_state once a second. Without this guard that is a
        TclError ("invalid command name") every second, into a stderr that
        doesn't exist under pythonw.
        """
        button = getattr(self, "record_toggle_btn", None)
        if button is None:
            return False
        try:
            return bool(button.winfo_exists())
        except Exception:
            return False

    def _set_hero_state(self, state):
        """Swap the hero card between the four v3 states from one enum.

        Frames 2a (recording), 2f (idle - watching), 2g (paused) and 2h (OBS
        disconnected). Per the spec only the eyebrow, the tint and the primary
        action change - the padding and the button row stay put, so nothing
        else on the dashboard moves. Elapsed / size / bitrate are filled in by
        _poll_obs_status; this owns everything else.

        Note the tints: v3 is a two-hue system and "Disconnected - the only
        place the ember hue leads". Recording is therefore accent, not red.
        """
        # The state is remembered either way, so putting the module back
        # restores the card in whatever state the app has since reached.
        self._hero_state = state
        if not self._hero_present():
            return
        tint = dv.HERO_STATES[state]["tint"] or CARD_BORDER
        light = EMBER if tint is EMBER else ACCENT_LIGHT
        if state == "paused" and getattr(self, "_pause_reason", None) == "session":
            paused_eyebrow = "Paused — stream ended"
        else:
            paused_eyebrow = (
                f"Paused - idle {self.config.get('idle_timeout_seconds', 4)} s")
        eyebrow = {
            "disconnected": "OBS disconnected",
            "watching": "Idle - watching",
            "recording": "Recording",
            "paused": paused_eyebrow,
        }[state]
        sub = {
            "disconnected": "Can't reach OBS",
            "watching": "",
            "recording": "",
            "paused": "",
        }[state]

        # The badge sizes itself to the eyebrow. The four labels differ a lot in
        # length ("Recording" vs "Paused - idle 4 s"), and tracking them out
        # widens them further - a fixed pill overflowed on two of the states and
        # collided with the subtitle.
        badge_label = self._track(eyebrow)
        bx, by, _, bh = self._hero_badge_geom
        bw = 26 + self._text_w(badge_label, dv.type_font("eyebrow")) + 12
        self._hero_badge_geom = (bx, by, bw, bh)
        self._regen_glass(self._hero_badge_item, bx, by, bw, bh, tint=tint,
                          radius=7, tint_alpha=40, border_alpha=0)
        self.bg.itemconfigure(self._hero_badge_text, text=badge_label, fill=light)
        self.bg.itemconfigure(self.rec_dot_id, fill=tint)
        self.bg.itemconfigure(self._hero_sub_id, text=sub, fill=light if sub else MUTED)
        self.bg.coords(self._hero_sub_id, bx + bw + 12, by + bh / 2)

        hx, hy, hw, hh = self._status_card_geom
        self._regen_hero_shell(hx, hy, hw, hh, tint, 70)

        # Readouts only carry meaning while a recording exists. 2f is explicit:
        # "Idle - neutral tint, no timer, no scene preview."
        show_readout = state in ("recording", "paused")
        for cap, val in self._readouts.values():
            self.bg.itemconfigure(cap, state=self._hero_vis(show_readout))
            self.bg.itemconfigure(val, state=self._hero_vis(show_readout))
        # "Paused - accent tint, timer frozen at 60% opacity." No alpha on a
        # canvas item, so the 60% is composited against the card core.
        self.bg.itemconfigure(
            self.timer_label_id,
            fill=dv.over(dv.TEXT, dv.PAUSED_TIMER_OPACITY, dv.CARD_CORE)
            if state == "paused" else TEXT)

        self.bg.itemconfigure(
            self._hero_hint_id,
            state=self._hero_vis(not show_readout),
            text="" if show_readout else {
                "disconnected": (
                    f"Retrying every {self.config.get('reconnect_interval_seconds', 10)}s. "
                    "Launching from obs_path if it's set."),
                "watching": "Standing by — recording starts by itself the moment a game launches.",
            }.get(state, ""),
        )

        # 6.6's idle-hero row: "Foreground exe - 'chrome.exe - not a game'".
        # Only while watching, and only once the monitor has actually told us
        # what has focus - before then there is nothing true to say.
        foreground = getattr(self, "_foreground_exe", None)
        if state == "watching" and foreground:
            name, verdict = foreground
            self.bg.itemconfigure(
                self._hero_source_id, state=self._hero_vis(True),
                text=f"Foreground: {name} — " + {
                    "non_game": "classified as not a game.",
                    "unknown": "not classified yet.",
                }.get(verdict, "not a game Nebula records."))
        else:
            self.bg.itemconfigure(self._hero_source_id, text="", state="hidden")

        # Scene-preview caption follows the capture, so the right column isn't
        # claiming "idle" while a recording is plainly running. Scene name is
        # real (GetCurrentProgramScene); res/fps only appear once fetched.
        scene = self._scene_name
        if state == "paused" and getattr(self, "_pause_reason", None) == "session":
            paused_info = (f"{scene} — stream ended" if scene
                           else "Capture held — stream ended")
        else:
            paused_info = (f"{scene} — paused" if scene
                           else "Capture held — paused")
        info = {
            "recording": (f"{scene} → {self._current_game}" if scene and self._current_game
                          else scene or (f"Capturing {self._current_game}"
                                         if self._current_game else "Capturing")),
            "paused": paused_info,
            "watching": (f"Scene — {scene}" if scene else "Scene capture idle"),
            "disconnected": "No scene — OBS offline",
        }[state]
        self.bg.itemconfigure(self._preview_info_id, text=info)
        self.bg.itemconfigure(self._preview_dot_id, fill=tint if show_readout else FAINT)
        if getattr(self, "_preview_scene_chip", None):
            self.bg.itemconfigure(
                self._preview_scene_chip,
                text=(scene[:22] if scene else "OBS scene"))
        if getattr(self, "_preview_video_id", None):
            # 2f: idle watching has no scene preview chrome with live numbers.
            show_vid = bool(self._video_label) and state in ("recording", "paused", "watching")
            self.bg.itemconfigure(
                self._preview_video_id,
                text=self._video_label if show_vid else "",
                state=self._hero_vis(show_vid))

        # The button row: same position always, different label / binding /
        # emphasis per state (2f-2h). Ember only leads on a real disconnection.
        primary, secondary = {
            "recording":    (("Stop recording", self._toggle_record, True),
                             ("Pause", self._toggle_pause, False)),
            "paused":       (("Resume", self._toggle_pause, False),
                             ("Stop & save", self._toggle_record, False)),
            "watching":     (("Record anyway", self._toggle_record, False),
                             ("Pause monitoring", self._toggle_monitoring, False)),
            "disconnected": (("Retry now", self._start, False),
                             ("Connection settings", lambda: self._show_view("settings"), False)),
        }[state]

        text, command, is_ember = primary
        self._hero_primary_cmd = command
        pill_tint = EMBER if is_ember else ACCENT
        pill_text = EMBER if is_ember else ACCENT_LIGHT
        self._hero_primary_text = pill_text
        # "Trailing icons on primary pills live in their own 26-28px circle,
        # flush to the right padding." Rendered as the button's own image so it
        # sits inside the pill; a canvas circle would be painted over by the
        # embedded widget.
        # These are *actions*, not states: the trailing icon says what clicking
        # does. watching -> start (record) is correct and is not the missing
        # ICONS["watching"] lookup - the Tk hero has no status glyph slot at all.
        role = {"recording": "square", "paused": "resume",
                "watching": "start", "disconnected": "rescan"}[state]
        glyph = ICON_GLYPHS.get(role) or ICON_GLYPHS[dv.ICONS[role]]
        circle = pill_trailing_icon(glyph, pill_tint, dv.CARD_CORE,
                                    dv.PILL_TRAILING_CIRCLE[0], self.scale)
        self._hero_pill_image = ctk.CTkImage(
            light_image=circle, dark_image=circle,
            size=(dv.PILL_TRAILING_CIRCLE[0], dv.PILL_TRAILING_CIRCLE[0]))
        self.record_toggle_btn.configure(
            text=text,
            image=self._hero_pill_image, compound="right", anchor="w",
            fg_color=RED_TINT if is_ember else GREEN_TINT,
            hover_color=RED_TINT_HOVER if is_ember else GREEN_TINT_HOVER,
            text_color=pill_text,
            border_color=pill_tint,
        )
        text, command, _ = secondary
        self._hero_secondary_cmd = command
        self.pause_btn.configure(text=text)
        # Both buttons are meaningful in every v3 state, so unlike v2 the
        # secondary is never hidden - only relabelled. It still follows the
        # view, or it floats over the Macropad pane while a recording runs.
        self.bg.itemconfigure(self._pause_btn_win, state=self._hero_vis(True))

    # ---- stat tiles ----
    def _build_stats(self, x0, y, w):
        # 4 tiles across when there's room (full-width), 2x2 when the panel is in
        # a half-width grid slot. Every tile's contents are laid out relative to
        # its own (tx, ty), so both arrangements just work.
        gap = 14
        # Four across only when there is genuinely room. At half width the four
        # tiles came out ~110px each and their captions clipped, which is how a
        # stray letter ended up floating outside the module.
        cols = 4 if w >= 700 else 2
        tw = (w - gap * (cols - 1)) / cols
        h = 92

        def cell(i):
            col, row = i % cols, i // cols
            return x0 + col * (tw + gap), y + row * (h + gap)

        # 1) Today's clips (filled in by _poll_disk_stats)
        tx, ty = cell(0)
        self._stat_tile(tx, ty, tw, h, "film-strip", ACCENT, "Clips today")
        self._stat_today_val = self.bg.create_text(
            tx + 15, ty + 48, anchor="w", text="–", fill=TEXT,
            font=dv.font(21, 500))
        self._stat_today_sub = self.bg.create_text(
            tx + 15, ty + 71, anchor="w", text="scanning…", fill=MUTED,
            font=dv.type_font("meta"))

        # 2) Recorded
        tx, ty = cell(1)
        self._stat_tile(tx, ty, tw, h, "record", ACCENT, "Recorded")
        self._stat_recorded_val = self.bg.create_text(
            tx + 15, ty + 48, anchor="w", text="–", fill=TEXT,
            font=dv.font(21, 500))
        self._stat_recorded_sub = self.bg.create_text(
            tx + 15, ty + 71, anchor="w", text="today", fill=MUTED,
            font=dv.type_font("meta"))

        # 3) Auto-culled
        tx, ty = cell(2)
        self._stat_tile(tx, ty, tw, h, "scissors", ACCENT, "Auto-culled")
        self._stat_culled_val = self.bg.create_text(
            tx + 15, ty + 48, anchor="w", text="–", fill=TEXT,
            font=dv.font(21, 500))
        self._stat_culled_sub = self.bg.create_text(
            tx + 15, ty + 71, anchor="w",
            text=f"under {self.config.get('min_clip_seconds', 10)}s",
            fill=MUTED, font=dv.type_font("meta"))

        # 4) Idle pauses
        tx, ty = cell(3)
        self._stat_tile(tx, ty, tw, h, "moon", ACCENT, "Idle pauses")
        self._stat_idle_val = self.bg.create_text(
            tx + 15, ty + 48, anchor="w", text="–", fill=TEXT,
            font=dv.font(21, 500))
        self._stat_idle_sub = self.bg.create_text(
            tx + 15, ty + 71, anchor="w",
            text=f"after {self.config.get('idle_timeout_seconds', 4)}s idle",
            fill=MUTED, font=dv.type_font("meta"))

        self._refresh_stat_tiles()

    def _refresh_stat_tiles(self):
        """Fill the four tiles from the session log.

        6.3: "A stat tile shows one number and one caption. It never contains a
        control." The Idle timeout tile held a live slider and the Sync tile
        held a queue readout, so two of the four were controls wearing a tile's
        clothes. The slider moved to Settings, where every other setting lives,
        and sync moved to Settings -> Sync. Disk free was a duplicate: the rail
        footer already carries it with its bar, which is where 2a puts it.

        The replacements are counted from sessions.jsonl, so a fresh install
        reads zero because zero is true - not because the source is missing.
        """
        if not hasattr(self, "_stat_culled_val"):
            return
        try:
            stats = session_log.today()
        except Exception:
            return
        seconds = int(stats["recorded_seconds"])
        hours, rem = divmod(seconds, 3600)
        minutes = rem // 60
        self.bg.itemconfigure(
            self._stat_recorded_val,
            text=f"{hours}h {minutes:02d}m" if hours else f"{minutes}m")
        self.bg.itemconfigure(self._stat_culled_val, text=str(stats["culled"]))
        self.bg.itemconfigure(self._stat_idle_val, text=str(stats["idle_pauses"]))
        if getattr(self, "_stat_today_val", None) is not None and stats["clips"]:
            # The disk scan also fills this one; the log is the faster answer
            # and agrees with it for anything recorded since midnight.
            self.bg.itemconfigure(self._stat_today_val, text=str(stats["clips"]))

    def on_offload_state(self, pending, reachability=None):
        """Called (from the offloader's thread) as the NAS queue drains.

        6.3 moved this off the dashboard - "Sync status belongs in Settings ->
        Sync" - so the queue depth is held here and rendered by the Settings
        pane rather than by a stat tile. ``reachability`` is an optional
        diagnose() code from the offloader (Tailscale-aware NAS status).
        """
        self._offload_pending = pending
        if reachability is not None:
            self._offload_reachability = reachability
        self._ui(self._refresh_sync_status)

    def _sync_status_text(self):
        pending = getattr(self, "_offload_pending", 0)
        reach = getattr(self, "_offload_reachability", None)
        if reach is None and self.offloader and self.offloader.enabled:
            try:
                reach = self.offloader.reachability()
                self._offload_reachability = reach
            except Exception:
                reach = None

        if pending > 0:
            text = f"{pending} clip{'' if pending == 1 else 's'} queued for the NAS"
            if reach and reach.startswith("nas_down"):
                text = f"{pending} clip{'' if pending == 1 else 's'} waiting — NAS unreachable"
        elif self.offloader and self.offloader.enabled:
            if reach and reach.startswith("nas_down"):
                text = "NAS unreachable"
            else:
                text = "NAS offload up to date"
        else:
            text = "NAS offload off"

        from . import tailscale as ts
        clause = ts.diagnose_label(reach) if reach else ""
        if clause:
            text = f"{text}  ·  {clause}"

        if self.offloader and self.offloader.enabled:
            try:
                st = self.offloader.status_snapshot()
                if st.get("peer"):
                    peer = st["peer"]
                    if st.get("peer_online") is True:
                        peer += " online"
                    elif st.get("peer_online") is False:
                        peer += " offline"
                    text = f"{text}  ·  {peer}"
                if st.get("last_success_ago"):
                    text = f"{text}  ·  verified {st['last_success_ago']}"
                elif st.get("last_scan_ago"):
                    text = f"{text}  ·  scanned {st['last_scan_ago']}"
                hours = st.get("interval_hours")
                if hours:
                    text = f"{text}  ·  auto every {hours}h"
                else:
                    text = f"{text}  ·  auto off"
                if st.get("message"):
                    text = f"{text}\n{st['message']}"
            except Exception:
                pass

        if self.gamesync and self.gamesync.enabled:
            return text + "\nGame list synced with GitHub"
        return text + "\nGame list is local to this machine"

    def _refresh_sync_status(self):
        label = getattr(self, "_settings_sync_label", None)
        if label is None:
            return
        try:
            label.configure(text=self._sync_status_text())
        except Exception:
            self._settings_sync_label = None   # the group was navigated away from

    def _stat_tile(self, x, y, w, h, role, color, label):
        """One stat tile - 16 / 4 / 12, per 6.2's nesting table."""
        self._card(x, y, w, h, kind="tile")
        self.bg.create_text(x + 15, y + 20, anchor="w", text=ICON_GLYPHS[role],
                            fill=color, font=(ICON_FONT, -13))
        self.bg.create_text(x + 34, y + 20, anchor="w", text=self._track(label),
                            fill=FAINT, font=dv.type_font("eyebrow"))

    # ---- command palette (7e) ----
    # "Ctrl K from anywhere, including a global hotkey that opens it over a
    # game." Matching and ranking live in obsauto/palette.py; this is the
    # window and the row builders.

    def _palette_rows(self):
        """The four sources, in the spec's order.

        Nothing destructive is offered: "Destructive rows never in the palette
        - no delete, no cull." A fuzzy list that can delete a clip two
        keystrokes after a typo is a trap, so those actions simply aren't
        built.
        """
        rows = []

        def add(group, label, action, hint="", recency=0.0):
            rows.append(palette.Row(group, label, action, hint, recency))

        # --- Actions ---
        recording = self._is_recording
        add("Actions",
            "Stop recording" if recording else "Start recording — current window",
            self._toggle_record, hint="record")
        if recording:
            add("Actions", "Resume recording" if self._is_paused else "Pause recording",
                self._toggle_pause, hint="pause")
        if getattr(self, "replay", None) and self.replay.enabled:
            add("Actions", f"Save the last {self.replay.seconds}s (instant replay)",
                self._save_replay, hint=(self.config.get("replay_hotkey") or "").upper())
        add("Actions", "Open recordings folder", self._open_recording_root,
            hint="folder")
        add("Actions",
            "Turn monitoring off" if self._monitoring_on else "Turn monitoring on",
            self._toggle_monitoring, hint="monitor")
        add("Actions", "Show the mini overlay", self.show_mini, hint="overlay")

        # --- Games (real classifications, never invented) ---
        try:
            games = self.classifier._data.get("games", {})
        except Exception:
            games = {}
        seen = set()
        for key, value in games.items():
            name = value.get("display_name") if isinstance(value, dict) else None
            name = name or key
            if name in seen:
                continue
            seen.add(name)
            add("Games", name, lambda n=name: self._show_game(n), hint=key)

        # --- Recent clips ---
        for clip in (getattr(self, "_clips", None) or [])[:12]:
            add("Recent clips", os.path.splitext(clip["name"])[0],
                lambda c=clip: self._open_path(os.path.dirname(c["path"])),
                hint=clip["game"], recency=clip.get("mtime", 0))

        # --- Settings ---
        for field in settings_spec.FIELDS:
            add("Settings", field.label,
                lambda g=field.group: self._open_settings_group(g),
                hint=field.key)
        return rows

    def _show_game(self, name):
        self._show_view("games")
        self._refresh_games()

    def _open_settings_group(self, group):
        self._show_view("settings")
        self._show_settings_group(group)

    def show_palette(self):
        """Ctrl+K. Opens over whatever is in front, without stealing the game."""
        if getattr(self, "_palette", None) is not None:
            try:
                self._palette["popup"].destroy()
            except Exception:
                pass
            self._palette = None

        rows = self._palette_rows()
        width = dv.PALETTE_W
        popup = ctk.CTkToplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(fg_color=dv.CARD_CORE)
        apply_rounded_corners(popup)

        left, top, right, bottom = self._monitor_workarea(primary=False)
        sw = self._S(width)
        x = left + ((right - left) - sw) // 2
        y = top + int((bottom - top) * dv.PALETTE_TOP_FRACTION)

        entry = ctk.CTkEntry(
            popup, placeholder_text="Search actions, games, clips and settings",
            fg_color=dv.GROUND, border_color=EDGE, border_width=1, text_color=TEXT,
            corner_radius=dv.RADIUS_CONTROL, font=ctk.CTkFont(size=15), height=44)
        entry.pack(fill="x", padx=14, pady=(14, 8))

        body = ctk.CTkFrame(popup, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8)

        footer = ctk.CTkLabel(popup, text="", anchor="w", text_color=FAINT,
                              font=ctk.CTkFont(size=11))
        footer.pack(fill="x", padx=18, pady=(4, 12))

        state = {"popup": popup, "rows": rows, "flat": [], "index": 0,
                 "widgets": []}
        self._palette = state

        def close(_event=None):
            self._palette = None
            try:
                popup.destroy()
            except Exception:
                pass

        def run(_event=None):
            flat = state["flat"]
            if not flat:
                return "break"
            action = flat[state["index"]].action
            close()
            # "Over a game: shows, runs, and closes - no window focus." The
            # window is only raised if the action itself is one that needs it.
            try:
                action()
            except Exception as exc:
                self._log(f"[Palette] {exc}")
            return "break"

        def move(step):
            if state["flat"]:
                state["index"] = (state["index"] + step) % len(state["flat"])
                paint()
            return "break"

        def paint():
            for widget in state["widgets"]:
                widget.destroy()
            state["widgets"] = []
            query = entry.get().strip()
            grouped = palette.search(rows, query)
            state["flat"] = palette.flatten(grouped)
            state["index"] = min(state["index"], max(0, len(state["flat"]) - 1))

            if not state["flat"]:
                # "No match: Nothing matches 'xyzzy' / Try a game name, a clip
                # date, or an action."
                label = ctk.CTkLabel(
                    body, justify="left", anchor="w", text_color=MUTED,
                    font=ctk.CTkFont(size=13),
                    text=f'Nothing matches "{query}"\n'
                         "Try a game name, a clip date, or an action")
                label.pack(fill="x", padx=10, pady=14)
                state["widgets"].append(label)
                footer.configure(text="Esc  close")
                return

            position = 0
            for group, group_rows in grouped:
                heading = ctk.CTkLabel(
                    body, text=self._track(group if query else "Suggested"),
                    anchor="w", text_color=FAINT, font=ctk.CTkFont(size=10))
                heading.pack(fill="x", padx=12, pady=(8, 2))
                state["widgets"].append(heading)
                for row in group_rows:
                    selected = position == state["index"]
                    item = ctk.CTkFrame(
                        body, fg_color=ACCENT_TINT if selected else "transparent",
                        corner_radius=8, height=dv.PALETTE_ROW_H)
                    item.pack(fill="x", padx=8, pady=1)
                    ctk.CTkLabel(item, text=row.label, anchor="w",
                                 text_color=TEXT if selected else TEXT_SOFT,
                                 font=ctk.CTkFont(size=13)).pack(
                        side="left", padx=12, pady=7)
                    if row.hint:
                        ctk.CTkLabel(item, text=row.hint, anchor="e",
                                     text_color=FAINT,
                                     font=ctk.CTkFont(family="Consolas", size=10)).pack(
                            side="right", padx=12)
                    for widget in (item, *item.winfo_children()):
                        widget.bind("<Button-1>",
                                    lambda _e, i=position: (state.update(index=i), run()))
                    state["widgets"].append(item)
                    position += 1

            total = palette.count_all(rows, query)
            footer.configure(
                text=f"↑↓  navigate     ↵  run     Esc  close"
                     f"          {len(state['flat'])} of {total} results")

        entry.bind("<KeyRelease>", lambda _e: paint())
        entry.bind("<Down>", lambda _e: move(1))
        entry.bind("<Up>", lambda _e: move(-1))
        entry.bind("<Return>", run)
        entry.bind("<Escape>", close)
        popup.bind("<Escape>", close)
        popup.bind("<FocusOut>", lambda _e: None)

        paint()
        popup.update_idletasks()
        popup.geometry(f"{sw}x{popup.winfo_reqheight()}+{x}+{y}")
        popup.lift()
        entry.focus_force()
        return state

    # ---- session ribbon (7b) ----
    # "The day as one strip. Blocks are recording spans coloured per game,
    # hatched gaps are idle pauses, ember ticks are clip marks, and the last
    # block glows if it's still running."
    #
    # The whole thing is a rendering of sessions.jsonl - session_log.spans()
    # does the folding, and nothing here collects data of its own.
    RIBBON_RANGE_SECONDS = {"Day": None, "12h": 12 * 3600, "Session": None}

    def _build_ribbon(self, x0, y, w, h):
        self._card(x0, y, w, h, kind="panel")
        pad = 18
        self.bg.create_text(x0 + pad, y + 22, anchor="w",
                            text=self._track("Session ribbon"),
                            fill=FAINT, font=dv.type_font("eyebrow"))
        self._ribbon_summary = self.bg.create_text(
            x0 + pad, y + 44, anchor="w", text="", fill=TEXT_SOFT,
            font=dv.type_font("body"))

        # Day / 12h / Session, a segmented control in the header. The tiles are
        # canvas items, so switching range only re-tints them - no rebuild.
        seg_w = 56
        self._ribbon_segments = {}
        for i, name in enumerate(reversed(dv.RIBBON_RANGES)):
            sx = x0 + w - pad - (i + 1) * seg_w - i * 3
            tile = self._glass(sx, y + 14, seg_w, 24, tint=BASE_BG,
                               radius=dv.RADIUS_CONTROL, tint_alpha=90,
                               border_alpha=0)
            text = self.bg.create_text(sx + seg_w / 2, y + 26, text=name,
                                       fill=MUTED, font=dv.font(11, 500))
            for item in (tile, text):
                self.bg.tag_bind(item, "<Button-1>",
                                 lambda _e, n=name: self._set_ribbon_range(n))
            self._ribbon_segments[name] = (text, (sx, y + 14, seg_w, 24), tile)
        self._paint_ribbon_segments()

        self._ribbon_geom = (x0 + pad, y + 66, w - pad * 2, dv.RIBBON_TRACK_H)
        self._ribbon_items = []
        self._ribbon_detail_y = y + 66 + dv.RIBBON_TRACK_H + 34
        self._ribbon_detail = self.bg.create_text(
            x0 + pad, self._ribbon_detail_y, anchor="w", text="", fill=TEXT,
            font=dv.type_font("body"))
        self._ribbon_detail_sub = self.bg.create_text(
            x0 + pad, self._ribbon_detail_y + 20, anchor="w", text="",
            fill=FAINT, font=dv.font(11, mono=True))
        self._refresh_ribbon()

    def _tick_ribbon(self):
        """7b: "Live update: last block width every 10s, no reflow".

        Only while a recording is actually running and the Clips pane is on
        screen - the live block is the only thing that moves, and redrawing an
        unwatched pane is a full window composite for nothing.
        """
        try:
            if self._is_recording and self._current_view == "clips":
                self._refresh_ribbon()
        except Exception:
            pass
        self.root.after(dv.RIBBON_LIVE_UPDATE_MS, self._tick_ribbon)

    def _tick_forecast(self):
        """7c: "Refresh: on launch, on rec_stop, every 15 min"."""
        try:
            self._refresh_forecast()
            self._refresh_stat_tiles()
        except Exception:
            pass
        self.root.after(dv.FORECAST_REFRESH_MS, self._tick_forecast)

    def _paint_ribbon_segments(self):
        active = getattr(self, "_ribbon_range", "Day")
        for name, (text, geom, tile) in self._ribbon_segments.items():
            on = name == active
            self._regen_glass(tile, *geom, tint=ACCENT if on else BASE_BG,
                              radius=dv.RADIUS_CONTROL,
                              tint_alpha=120 if on else 90, border_alpha=0)
            self.bg.itemconfigure(text, fill=NAV_ACTIVE_TEXT if on else MUTED)

    def _set_ribbon_range(self, name):
        self._ribbon_range = name
        self._paint_ribbon_segments()
        self._refresh_ribbon()

    def _ribbon_window(self, spans, now):
        """(start, end) of the axis for the current range."""
        choice = getattr(self, "_ribbon_range", "Day")
        if choice == "12h":
            return now - 12 * 3600, now
        if choice == "Session" and spans:
            return min(s["start"] for s in spans), now
        return session_log.day_start(now), now

    def _refresh_ribbon(self):
        if getattr(self, "_ribbon_geom", None) is None:
            return
        for item in self._ribbon_items:
            self.bg.delete(item)
        self._ribbon_items = []

        now = time.time()
        try:
            spans = session_log.spans(now=now)
        except Exception:
            spans = []
        start, end = self._ribbon_window(spans, now)
        spans = [s for s in spans if (s["end"] or now) >= start]

        summary = session_log.summarise(spans)
        hours, rem = divmod(int(summary["seconds"]), 3600)
        self.bg.itemconfigure(
            self._ribbon_summary,
            text=(f"{hours}h {rem // 60:02d}m recorded  ·  {summary['games']} game"
                  f"{'' if summary['games'] == 1 else 's'}  ·  {summary['marks']} mark"
                  f"{'' if summary['marks'] == 1 else 's'}") if spans
                 else "Nothing recorded today")

        tx, ty, tw, th = self._ribbon_geom
        # One gradient tile per block and one hatch per idle gap, redrawn on
        # every refresh - on a rec_stop, a range switch, or the live tick. The
        # scope drops the last pass's bitmaps, which the deletes above already
        # orphaned.
        with self._image_scope("ribbon"):
            # The track itself, always drawn - "Empty state: hairline + Nothing
            # recorded today", so the strip exists even with no spans on it.
            self._ribbon_items.append(self._glass(
                tx, ty, tw, th, tint=dv.GROUND, radius=dv.RIBBON_END_RADIUS,
                tint_alpha=150, border_alpha=0))

            span_seconds = max(1.0, end - start)
            games = sorted({s["game"] for s in spans})
            for span in spans:
                self._ribbon_block(span, tx, ty, tw, th, start, span_seconds, games)
            self._ribbon_axis(tx, ty + th + 10, tw, start, end)
        self._adopt_view_items("clips", self._ribbon_items)

    def _ribbon_block(self, span, tx, ty, tw, th, start, span_seconds, games):
        now = time.time()
        s_start = max(span["start"], start)
        s_end = min(span["end"] or now, start + span_seconds)
        if s_end <= s_start:
            return
        # Clamp into the track before measuring: a span that starts past the
        # right edge (or a range change mid-refresh) otherwise yields a zero or
        # negative width, and PIL refuses to draw that.
        bx = min(max(tx, tx + (s_start - start) / span_seconds * tw), tx + tw)
        bw = max(dv.RIBBON_MIN_BLOCK, (s_end - s_start) / span_seconds * tw)
        bw = min(bw, tx + tw - bx)
        if bw < 1:
            return

        # "Per-game shade: lightness ±8% only - never a new hue."
        index = games.index(span["game"]) if span["game"] in games else 0
        step = ((index % 3) - 1) * dv.RIBBON_SHADE_STEP
        top = _shift_lightness(dv.RIBBON_BLOCK_TOP, step)
        bottom = _shift_lightness(dv.RIBBON_BLOCK_BOTTOM, step)
        if span["live"]:
            # "Live block: ember + 18px glow + pulsing dot." Ember and glow
            # yes; the pulse would be a per-frame canvas repaint.
            top, bottom = EMBER, _shift_lightness(EMBER, -0.18)

        tile = _vertical_gradient_tile(self._S(int(bw)), self._S(th),
                                       top, bottom, self._S(dv.RIBBON_RADIUS))
        photo = to_photo(tile)
        self._keep_image(photo)
        self._ribbon_items.append(
            self.bg.create_image(bx, ty, anchor="nw", image=photo))

        # "Idle gap: 135° hatch, 4px period, alpha .07."
        for gap_start, gap_end in span.get("gaps", ()):
            gx = tx + (max(gap_start, start) - start) / span_seconds * tw
            gw = (min(gap_end or now, start + span_seconds) - max(gap_start, start))
            gw = gw / span_seconds * tw
            if gw <= 0:
                continue
            hatch = _hatch_tile(self._S(max(1, int(gw))), self._S(th),
                                dv.HAIRLINE_RGB, dv.RIBBON_HATCH_ALPHA,
                                self._S(dv.RIBBON_HATCH_PERIOD))
            hphoto = to_photo(hatch)
            self._keep_image(hphoto)
            self._ribbon_items.append(
                self.bg.create_image(gx, ty, anchor="nw", image=hphoto))

        # "Clip mark: 2px #FF5C7A, overhangs 5px both ends."
        for mark in span.get("marks", ()):
            mx = tx + (mark - start) / span_seconds * tw
            self._ribbon_items.append(self.bg.create_rectangle(
                mx, ty - dv.RIBBON_MARK_OVERHANG,
                mx + dv.RIBBON_MARK_W, ty + th + dv.RIBBON_MARK_OVERHANG,
                fill=EMBER, outline=""))

        hit = self.bg.create_rectangle(bx, ty, bx + bw, ty + th,
                                       fill="", outline="")
        self.bg.tag_bind(hit, "<Button-1>", lambda _e, s=span: self._select_span(s))
        self.bg.tag_bind(hit, "<Enter>", lambda _e: self.bg.configure(cursor="hand2"))
        self.bg.tag_bind(hit, "<Leave>", lambda _e=None: self.bg.configure(cursor=""))
        self._ribbon_items.append(hit)

    def _ribbon_axis(self, tx, ty, tw, start, end):
        """"Axis: mono 9.5, 4-5 ticks, 'now' last"."""
        ticks = dv.RIBBON_AXIS_TICKS[0]
        for i in range(ticks):
            fraction = i / float(ticks)
            when = start + (end - start) * fraction
            self._ribbon_items.append(self.bg.create_text(
                tx + fraction * tw, ty, anchor="nw",
                text=time.strftime("%H:%M", time.localtime(when)),
                fill=FAINT, font=dv.font(9.5, mono=True)))
        self._ribbon_items.append(self.bg.create_text(
            tx + tw, ty, anchor="ne", text="now", fill=MUTED,
            font=dv.font(9.5, mono=True)))

    def _select_span(self, span):
        """"Click: select → fills detail row"."""
        started = time.strftime("%H:%M", time.localtime(span["start"]))
        ended = ("now" if span["live"]
                 else time.strftime("%H:%M", time.localtime(span["end"])))
        seconds = int((span["end"] or time.time()) - span["start"])
        mm, ss = divmod(seconds, 60)
        parts = [f"{mm}:{ss:02d}"]
        if span.get("size"):
            parts.append(_format_bytes(span["size"]))
        if span.get("marks"):
            parts.append(f"{len(span['marks'])} mark"
                         + ("" if len(span["marks"]) == 1 else "s"))
        if span.get("path"):
            parts.append(os.path.basename(span["path"]))
        self.bg.itemconfigure(self._ribbon_detail,
                              text=f"{span['game']}  ·  {started} → {ended}")
        self.bg.itemconfigure(self._ribbon_detail_sub, text="  ·  ".join(parts))
        self._ribbon_selected = span

    # ---- instant replay module (7a) ----
    # "Dashboard module - 486x236, half width." Registers in the 6.8 catalogue
    # like any other module, which is what 7g means by "7a, 7b and 7c each
    # register in the module catalogue from 6h".
    def _build_replay(self, x0, y, w, h):
        self._card(x0, y, w, h, kind="panel")
        pad = 16
        self.bg.create_text(x0 + pad, y + 22, anchor="w",
                            text=self._track("Instant replay"),
                            fill=FAINT, font=dv.type_font("eyebrow"))

        # The armed badge. Ember, because an armed buffer is a live thing -
        # the spec pulses it, which would be a per-frame canvas repaint, so it
        # is a static ember badge and the state reads from the fill instead.
        self._replay_badge = self._glass(x0 + w - pad - 104, y + 12, 104, 22,
                                         tint=EMBER, radius=dv.RADIUS_CONTROL,
                                         tint_alpha=44, border_hex=EMBER,
                                         border_alpha=90)
        self._replay_badge_text = self.bg.create_text(
            x0 + w - pad - 52, y + 23, text=self._track("Disarmed"),
            fill=MUTED, font=dv.type_font("eyebrow"))

        self._replay_len_id = self.bg.create_text(
            x0 + pad, y + 54, anchor="w", text="", fill=TEXT,
            font=dv.font(19, 500))
        self._replay_ram_id = self.bg.create_text(
            x0 + pad, y + 78, anchor="w", text="", fill=MUTED,
            font=dv.type_font("meta"))

        key = (self.config.get("replay_hotkey") or "").upper()
        if key:
            self._draw_keycap(x0 + w - pad - 22, y + 62, key)
        self.bg.create_text(
            x0 + pad, y + 104, anchor="w",
            text=f"Save the last {self.replay.seconds} seconds",
            fill=TEXT_SOFT, font=dv.type_font("body"))
        self.bg.create_text(
            x0 + pad, y + 124, anchor="w", text="Tray menu  ·  mini overlay",
            fill=FAINT, font=dv.type_font("meta"))

        self._fading_rule(x0 + pad, y + 142, w - pad * 2)
        self.bg.create_text(x0 + pad, y + 160, anchor="w",
                            text=self._track("Saved this session"),
                            fill=FAINT, font=dv.type_font("eyebrow"))
        self._replay_rows_y = y + 178
        self._replay_rows_w = w - pad * 2
        self._replay_rows = []

        # The Enable button for 7a's inline fix. An embedded widget rather than
        # canvas text because it is a real action; hidden unless OBS actually
        # reports the buffer as unavailable.
        self._replay_fix_btn = ctk.CTkButton(
            self.root, text="Enable in OBS", command=self._enable_replay_buffer,
            fg_color=ACCENT_TINT, hover_color=SURFACE_HOVER, text_color=ACCENT_LIGHT,
            border_width=1, border_color=ACCENT, corner_radius=dv.RADIUS_CONTROL,
            font=ctk.CTkFont(size=12))
        self._replay_fix_win = self.bg.create_window(
            x0 + w - pad - 128, y + 176, anchor="nw",
            window=self._replay_fix_btn, width=128, height=30)
        self.bg.itemconfigure(self._replay_fix_win, state="hidden")
        self._dashboard_widgets.append(self._replay_fix_btn)
        self._refresh_replay_module()

    def _enable_replay_buffer(self):
        """Turn OBS's replay buffer on, off the Tk thread."""
        def worker():
            ok = self.replay.enable_in_obs()
            self._ui(lambda: self._replay_enabled_result(ok))
        threading.Thread(target=worker, daemon=True).start()

    def _replay_enabled_result(self, ok):
        self._refresh_replay_module()
        if not ok:
            self._toast_replace("error", "OBS needs a restart to create the buffer")

    def _refresh_replay_module(self):
        if getattr(self, "_replay_badge", None) is None:
            return
        armed = self.replay.armed
        # "Armed: ember badge · Disarmed: neutral badge, key dimmed."
        self._regen_glass(
            self._replay_badge, *self._replay_badge_geom(),
            tint=EMBER if armed else dv.GROUND, radius=dv.RADIUS_CONTROL,
            tint_alpha=44 if armed else 120,
            border_hex=EMBER if armed else EDGE, border_alpha=90 if armed else 40)
        self.bg.itemconfigure(self._replay_badge_text,
                              text=self._track("Buffer armed" if armed else "Disarmed"),
                              fill=EMBER if armed else MUTED)
        self.bg.itemconfigure(self._replay_len_id, text=f"{self.replay.seconds}s")

        # "Show it live next to the duration so raising the buffer has a
        # visible cost. Warn above 2 GB." Nothing is shown until a real bitrate
        # exists - an estimate from a guessed bitrate is a made-up number.
        mb = replay_mod.ram_estimate_mb(self._last_bitrate_mbps, self.replay.seconds)
        if mb is None:
            self.bg.itemconfigure(self._replay_ram_id, text="", fill=MUTED)
        else:
            over = mb > replay_mod.RAM_WARN_MB
            self.bg.itemconfigure(
                self._replay_ram_id,
                text=f"~{mb / 1024:.1f} GB RAM" if mb >= 1024 else f"~{mb:.0f} MB RAM",
                fill=EMBER if over else MUTED)

        for item in self._replay_rows:
            self.bg.delete(item)
        self._replay_rows = []

        # 7a's inline fix: "Replay buffer is off in OBS / Nebula can switch it
        # on for you / [Enable]". Only for the specific "not available" case -
        # a transient failure isn't something a button can fix.
        wants_fix = self.replay.unavailable and self.obs.connected
        if getattr(self, "_replay_fix_btn", None) is not None:
            self.bg.itemconfigure(self._replay_fix_win,
                                  state="normal" if wants_fix else "hidden")
        if wants_fix:
            self._replay_rows.append(self.bg.create_text(
                self._content_x0() + 16, self._replay_rows_y, anchor="nw",
                text="Replay buffer is off in OBS.\nNebula can switch it on for you.",
                fill=MUTED, font=dv.type_font("meta")))
            self._adopt_view_items("dashboard", self._replay_rows, ("blk_replay",))
            return

        recent = list(reversed(self.replay.saved_this_session))[:2]
        if not recent:
            self._replay_rows.append(self.bg.create_text(
                self._content_x0() + 16, self._replay_rows_y, anchor="nw",
                text="Nothing saved yet." if armed
                     else "Arm the buffer to start holding the last few seconds.",
                fill=FAINT, font=dv.type_font("meta")))
        else:
            for i, (path, when) in enumerate(recent):
                age = max(0, int((time.time() - when) // 60))
                self._replay_rows.append(self.bg.create_text(
                    self._content_x0() + 16, self._replay_rows_y + i * 20, anchor="nw",
                    text=os.path.basename(path), fill=TEXT_SOFT,
                    font=dv.font(11, mono=True)))
                self._replay_rows.append(self.bg.create_text(
                    self._content_x0() + 16 + self._replay_rows_w,
                    self._replay_rows_y + i * 20, anchor="ne",
                    text=f"{self.replay.seconds}s  ·  {age}m ago" if age
                         else f"{self.replay.seconds}s  ·  just now",
                    fill=FAINT, font=dv.type_font("meta")))
        self._adopt_view_items("dashboard", self._replay_rows, ("blk_replay",))

    def _replay_badge_geom(self):
        x, y, w, _h = self._grid_rects.get("replay", (0, 0, 0, 0))
        return (x + w - 16 - 104, y + 12, 104, 22)

    # ---- activity log (6.4) ----
    # "Currently a tall empty box with the text clipped at the top and a
    # scrollbar. It is a fixed-height panel with a header bar, newest entry
    # first, and three aligned columns."
    ACTIVITY_HEADER_H = 34          # the header bar inside the panel
    ACTIVITY_COL_TIME = 58          # "Columns: time 58 · tag 74 · message flex"
    ACTIVITY_COL_TAG = 74
    ACTIVITY_FULL_ROWS = 5          # "Older rows opacity .5 past the 5th entry"

    def _build_activity(self, x0, y, w, h):
        # No eyebrow above the panel: the panel has its own header bar now, and
        # 6.8 is explicit that a module must not show its name twice ("the
        # module's own eyebrow must be replaced by the handle-strip name, not
        # shown alongside it"). In customise mode the handle strip names it.
        py = y + 22
        panel_h = h - 22
        self._card(x0, py, w, panel_h, kind="panel")

        # The header bar, inside the panel and above the rows: the label on the
        # left, the two actions on the right, a fading rule underneath.
        hy = py + self.ACTIVITY_HEADER_H / 2
        self.bg.create_text(x0 + 16, hy, anchor="w", text=self._track("Activity"),
                            fill=FAINT, font=dv.type_font("eyebrow"))
        self._activity_filter_btn = ctk.CTkButton(
            self.root, text="All tags", command=self._cycle_log_filter,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(x0 + w - 150, hy), border_width=1, border_color=EDGE,
            corner_radius=8, font=ctk.CTkFont(size=11))
        self.bg.create_window(x0 + w - 178, hy - 12, anchor="nw",
                              window=self._activity_filter_btn, width=84, height=24)
        copy_btn = ctk.CTkButton(
            self.root, text="Copy log", command=self._copy_log,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(x0 + w - 60, hy), border_width=1, border_color=EDGE,
            corner_radius=8, font=ctk.CTkFont(size=11))
        self.bg.create_window(x0 + w - 88, hy - 12, anchor="nw",
                              window=copy_btn, width=76, height=24)
        self._dashboard_widgets.extend([self._activity_filter_btn, copy_btn])
        self._fading_rule(x0 + 12, py + self.ACTIVITY_HEADER_H, w - 24)

        # Rounded plate + a flat square textbox inset inside it (see the note in
        # the old build - a tall widget can't match a sheen gradient's corners).
        box_x, box_y = x0 + 10, py + self.ACTIVITY_HEADER_H + 6
        box_w = max(40, w - 20)
        # Edit mode borrows height from the last row for the handle strips, and
        # a narrow module can leave nothing under the header bar. Clamp rather
        # than hand PIL a negative size - the panel just shows fewer rows.
        box_h = max(30, panel_h - self.ACTIVITY_HEADER_H - 16)
        box_r = 10
        backing = make_solid_tile(self._S(box_w), self._S(box_h), LOG_BG, radius=self._S(box_r))
        backing_photo = to_photo(backing)
        self._keep_image(backing_photo)
        self.bg.create_image(box_x, box_y, anchor="nw", image=backing_photo)
        self._composite.paste(backing, (self._S(box_x), self._S(box_y)), backing)

        self.console = ctk.CTkTextbox(
            self.root, state="disabled", wrap="word", fg_color=LOG_BG, corner_radius=0,
            bg_color=LOG_BG,
            font=ctk.CTkFont(family="Consolas", size=11), text_color=MUTED,
        )
        self.bg.create_window(box_x + box_r, box_y + box_r, anchor="nw", window=self.console,
                              width=box_w - box_r * 2, height=box_h - box_r * 2)
        # 6.4 lists the scrollbar among the defects ("a tall empty box with the
        # text clipped at the top and a scrollbar"). It is a fixed-height panel
        # showing the newest entries; anything older is in the log file, and
        # Copy log is right there in the header.
        try:
            self.console.configure(activate_scrollbars=False)
        except Exception:
            pass
        self._prepare_log_tags(self.console)
        self._dashboard_widgets.append(self.console)
        # Replay history so switching layouts (which rebuilds this) doesn't wipe
        # the visible log.
        # Oldest-first history into a newest-first panel, so replay reversed.
        self._append_log_batch(self.console,
                               list(reversed(self._log_lines[-LOG_HISTORY:])))

    # ---- disk / clip stats ----
    def _poll_disk_stats(self):
        """Fill the Today + Disk-free tiles from the real recording folder,
        off the Tk thread (a recursive scan + disk query can be slow)."""
        root_dir = self.config.get("recording_root", "")

        def worker():
            free_txt, drive, usage_pair = "", "", None
            try:
                usage = shutil.disk_usage(root_dir if os.path.isdir(root_dir) else os.path.expanduser("~"))
                free_txt = _format_bytes(usage.free)
                drive = os.path.splitdrive(os.path.abspath(root_dir))[0] or ""
                # The rail's storage card needs the total as well as the free
                # space - it shows a fill bar and "X free of Y" (frame 2a).
                usage_pair = (usage.free, usage.total)
            except Exception:
                pass
            clips, total = 0, 0
            try:
                today = time.localtime()

                def is_today(ts):
                    lt = time.localtime(ts)
                    return (lt.tm_year, lt.tm_yday) == (today.tm_year, today.tm_yday)

                exts = (".mkv", ".mp4", ".mov", ".flv", ".ts", ".m4v")
                # Walk with scandir and prune whole subtrees that weren't touched
                # today - a directory's mtime moves when a file is added to it, so
                # yesterday's per-game folders can be skipped without stat-ing
                # their contents. On a large archive (this recording root can hold
                # terabytes across hundreds of folders) that turns a full-tree
                # crawl every poll into a handful of directory reads.
                stack = [root_dir]
                while stack:
                    current = stack.pop()
                    with os.scandir(current) as it:
                        for entry in it:
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    if is_today(entry.stat().st_mtime):
                                        stack.append(entry.path)
                                elif entry.name.lower().endswith(exts):
                                    st = entry.stat()
                                    if is_today(st.st_mtime):
                                        clips += 1
                                        total += st.st_size
                            except OSError:
                                continue
            except Exception:
                pass
            try:
                self.root.after(0, lambda: self._apply_disk_stats(
                    clips, total, free_txt, drive, usage_pair))
            except RuntimeError:
                pass  # window torn down while the scan was still running

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(300000, self._poll_disk_stats)  # 5 min; it's a slow-moving stat

    def _apply_disk_stats(self, clips, total, free_txt, drive, usage_pair=None):
        self.bg.itemconfigure(self._stat_today_val,
                              text=f"{clips} clip" + ("" if clips == 1 else "s"))
        self.bg.itemconfigure(self._stat_today_sub,
                              text=f"{_format_bytes(total)} recorded" if clips else "nothing yet")
        # Disk free is not a tile any more - 6.3: "Disk free belongs in the rail
        # footer with its bar, not in this row - it is already there in 2a."
        # The rail card is filled from usage_pair just below.

        # The rail storage card. Left blank until a real reading arrives - an
        # empty bar beats a bar sitting at zero, which would read as "disk full".
        if usage_pair:
            self._disk_usage = usage_pair
            free, capacity = usage_pair
            used_frac = 0.0 if not capacity else max(0.0, min(1.0, (capacity - free) / capacity))
            x0, bar_y, full_w, bar_h = self._store_bar_rect
            self.bg.coords(self._store_bar,
                           x0, bar_y, x0 + full_w * used_frac, bar_y + bar_h)
            self._refresh_forecast()

    # ---- storage forecast (7c) ----
    # "Replaces the rail's bare percentage bar. States a date, not a ratio."
    # The maths lives in obsauto/forecast.py, which the spec pins down
    # precisely; everything here is presentation.
    def _refresh_forecast(self):
        usage = getattr(self, "_disk_usage", None)
        if not usage or getattr(self, "_store_pct", None) is None:
            return
        free, capacity = usage
        try:
            data = forecast.forecast(free, capacity)
        except Exception:
            return
        self._forecast = data

        days = data["days_left"]
        critical = days is not None and days < 1
        warn_at = self.config.get("disk_warn_days", 3)

        if data["ready"]:
            # "States a date, not a ratio."
            self.bg.itemconfigure(
                self._store_pct, text=forecast.days_left_label(days) + " left",
                fill=EMBER if critical or (warn_at and days <= warn_at) else FAINT)
            rate = data["gb_per_hour"]
            self.bg.itemconfigure(
                self._store_free,
                text=f"{_format_bytes(free)} free  ·  {rate:.1f} GB/h")
        else:
            # "Not enough history - first 3 days." Say what's missing rather
            # than showing a forecast nobody should trust.
            self.bg.itemconfigure(self._store_pct, text="", fill=FAINT)
            need = data["days_needed"]
            self.bg.itemconfigure(
                self._store_free,
                text=(f"{_format_bytes(free)} free of {_format_bytes(capacity)}"
                      if capacity else _format_bytes(free)))
            self.bg.itemconfigure(
                self._store_path,
                text=self._elide(self.config.get("recording_root", ""), 22))
            self._forecast_note(f"Forecast needs {forecast.MIN_HISTORY_DAYS} days "
                                f"of history — {need} to go" if need else "")
            return
        self._forecast_note("")

        # "One toast at disk_warn_days, once per day maximum."
        if warn_at and days is not None and days <= warn_at:
            today = time.strftime("%Y-%m-%d")
            if getattr(self, "_disk_warned_on", None) != today:
                self._disk_warned_on = today
                self._toast_replace(
                    "error", f"Disk fills in {forecast.days_left_label(days)}")
                self._log(f"[Storage] {forecast.days_left_label(days)} left at "
                          f"{data['gb_per_hour']:.1f} GB/h.")

    def _forecast_note(self, text):
        if getattr(self, "_store_note", None) is not None:
            self.bg.itemconfigure(self._store_note, text=text)

    def can_start_recording(self):
        """"Below disk_block_below_gb the hero card refuses to start."

        Returns (ok, reason). Refusing beats a recording that dies mid-session.
        """
        usage = getattr(self, "_disk_usage", None)
        floor_gb = self.config.get("disk_block_below_gb", 20)
        if not usage or not floor_gb:
            return True, ""
        free_gb = usage[0] / forecast.GB
        if free_gb >= floor_gb:
            return True, ""
        return False, (f"Only {free_gb:.0f} GB free — under the {floor_gb} GB "
                       "floor. Cull some clips first.")

    # ---- titlebar status updaters ----
    def _set_obs_status(self, text, color):
        """Update the OBS readout in the titlebar.

        Frame 2a draws ``OBS 30.2 · localhost:4455``. The version is real
        (GetVersion); until it arrives we show the transitional status string
        (connecting / disconnected / …). v3 has only two hues, so this reads
        accent for anything healthy or in-flight and ember only for a real
        disconnection — "the only place the ember hue leads" (frame 2h).
        """
        disconnected = color in (EMBER, RED)
        role = "plugs" if disconnected else "plugs-connected"
        hostport = (f"{self.config.get('obs_host', 'localhost')}:"
                    f"{self.config.get('obs_port', 4455)}")
        if not disconnected and self._obs_version:
            label = f"OBS {self._obs_version} \u00b7 {hostport}"
        else:
            # Keep the host:port visible so a disconnect still names the target.
            label = f"OBS {text} \u00b7 {hostport}"
        self.bg.itemconfigure(self._obs_card_dot,
                              text=ICON_GLYPHS[role],
                              fill=EMBER if disconnected else ACCENT_LIGHT)
        self.bg.itemconfigure(self._obs_card_title, text=label,
                              fill=EMBER if disconnected else MUTED)
        # Re-anchor the plugs glyph just left of the label (labels vary a lot).
        ox = WIDTH - dv.TITLEBAR_PAD_RIGHT - 120
        tw = self._text_w(label, dv.type_font("meta"))
        self.bg.coords(self._obs_card_dot, ox - tw - 14, TITLEBAR_HEIGHT / 2)
        self._refresh_settings_obs_footer()

    def _set_monitoring(self, on):
        self._monitoring_on = on
        self.bg.itemconfigure(self._mon_label,
                              text="Monitoring on" if on else "Monitoring off",
                              fill=NAV_ACTIVE_TEXT if on else TEXT_SOFT)
        self.bg.itemconfigure(self._mon_icon, fill=ACCENT if on else FAINT)
        self._sync_replay_arming()

    def _sync_replay_arming(self):
        """Arm or disarm the buffer from the two switches 7a names.

        "StartReplayBuffer on game detected, or with monitoring" /
        "StopReplayBuffer: monitoring off, or non-game focus". Runs on a worker
        because every one of those is a blocking socket round-trip, and this is
        called from state changes on the Tk thread.
        """
        if not getattr(self, "replay", None) or not self.replay.enabled:
            return
        want = bool(self._monitoring_on) and self.obs.connected
        if want and self.config.get("replay_only_for_games", True):
            want = bool(self._current_game)
        if not self.config.get("replay_arm_with_monitoring", True):
            want = want and bool(self._current_game)
        if want == self.replay.armed:
            return
        game = self._current_game
        threading.Thread(
            target=(lambda: self.replay.arm(game)) if want else self.replay.disarm,
            daemon=True).start()

    # ---- logging ----
    def _log(self, message):
        try:
            print(message)
        except (UnicodeEncodeError, AttributeError, OSError):
            # Some Steam game titles contain characters Windows' legacy
            # console codepage can't represent (e.g. fullwidth punctuation) -
            # printing to console is just a debug convenience, so swallow
            # this rather than crashing the monitor thread that logged it.
            pass
        log_to_file(message)
        # Two things happen here, both cheap and thread-safe (this is called
        # from the monitor/offload/sync worker threads): keep a bounded history
        # for the dashboard activity panel to replay, and buffer the line for
        # the UI. The actual textbox write is coalesced onto the Tk thread by
        # _flush_log, so a burst of hundreds of lines becomes one textbox update
        # per ~80ms instead of one window composite per line (which pegged the
        # UI under a log flood), and Tk is only ever touched from the main thread.
        with self._log_lock:
            self._log_lines.append(message)
            if len(self._log_lines) > LOG_HISTORY:
                del self._log_lines[:-LOG_HISTORY]
            self._log_pending.append(message)
            schedule = not self._log_flush_scheduled
            self._log_flush_scheduled = True
        if schedule:
            try:
                self.root.after(80, self._flush_log)
            except RuntimeError:
                with self._log_lock:
                    self._log_flush_scheduled = False

    def _flush_log(self):
        """Drain the pending buffer into the activity textbox in one batch. Runs
        on the Tk thread (scheduled by _log)."""
        with self._log_lock:
            pending = self._log_pending
            self._log_pending = []
            self._log_flush_scheduled = False
        if not pending:
            return
        # Under a burst, more lines can queue in one flush window than the log
        # even keeps - anything older than the last LOG_HISTORY has already
        # scrolled out of the bounded history, so there's no point rendering it.
        if len(pending) > LOG_HISTORY:
            pending = pending[-LOG_HISTORY:]
        # The console belongs to the Activity module, and 6.8's catalogue lets
        # that module be removed - which destroys the widget while this timer
        # carries on every ~80ms. Writing to it then is a TclError ("invalid
        # command name") on every log line, into a stderr that doesn't exist
        # under pythonw. The history is still kept, so putting the module back
        # replays it.
        box = getattr(self, "console", None)
        if box is None:
            return
        try:
            if not box.winfo_exists():
                return
        except Exception:
            return
        self._append_log_batch(box, pending)

    def _prepare_log_tags(self, box):
        """Colour-code the [Subsystem] prefix and set up 6.4's three columns.

        Reaches into CTkTextbox's underlying tk.Text (private but stable across
        ctk 5.x) since CTkTextbox doesn't proxy tag configuration - guarded so a
        ctk update can't crash the app.
        """
        try:
            tb = box._textbox
            for tag, color in LOG_TAG_COLORS.items():
                tb.tag_config(f"t_{tag}", foreground=color)
            tb.tag_config("t_time", foreground=dv.TEXT_EYEBROW)
            # "Older rows opacity .5 past the 5th entry." Canvas and Tk text
            # have no alpha, so the row is composited at .5 against the panel
            # instead - the same thing the browser would end up painting.
            tb.tag_config("t_old", foreground=dv.over(MUTED, 0.5, dv.PANEL))
            # "Columns: time 58 · tag 74 · message flex", as tab stops. Aligning
            # by tab means a long game name can't push the message column out.
            tb.configure(
                spacing1=5, spacing3=5,            # "Row pad-y 5"
                tabs=(f"{self._S(self.ACTIVITY_COL_TIME)}",
                      f"{self._S(self.ACTIVITY_COL_TIME + self.ACTIVITY_COL_TAG)}"),
                wrap="none")
        except Exception:
            pass

    def _log_row(self, message):
        """(time, tag, message) for one log line, whatever shape it arrives in."""
        stamp = time.strftime("%H:%M:%S")
        m = re.match(r"\[(\w+)\]\s*", message)
        if m:
            return stamp, m.group(1), message[m.end():]
        return stamp, "", message

    def _append_log_batch(self, box, messages):
        """Write many log lines with a single state toggle, newest at the top.

        6.4: "Order: newest at top, no auto-scroll jump." Inserting at 1.0
        rather than appending is also what removes the jump - there is nothing
        to scroll to, so a burst of lines can't yank the view while you are
        reading it.
        """
        box.configure(state="normal")
        try:
            tb = box._textbox
        except Exception:
            tb = None
        active = getattr(self, "_log_filter", None)
        for message in messages:
            stamp, tag, rest = self._log_row(message)
            if active and tag != active:
                continue
            # One insert for the whole row, then tag by column offset. Inserting
            # the three parts separately at "1.0"/"1.0 lineend" looks right and
            # isn't: "1.0" prepends *into* the existing first line, so every
            # entry after the first merged into the one above it.
            cell = f"[{tag}]" if tag else ""
            row = f"{stamp}\t{cell}\t{rest}\n"
            if tb is None:
                box.insert("1.0", row)
                continue
            tb.insert("1.0", row)
            tb.tag_add("t_time", "1.0", f"1.{len(stamp)}")
            if tag in LOG_TAG_COLORS:
                start = len(stamp) + 1
                tb.tag_add(f"t_{tag}", f"1.{start}", f"1.{start + len(cell)}")
        # Dim everything past the fifth row, and keep the widget bounded - a
        # long session's textbox otherwise grows without limit and every insert
        # gets slower. Newest-first means the trim is from the *bottom*.
        if tb is not None:
            try:
                tb.tag_remove("t_old", "1.0", "end")
                tb.tag_add("t_old", f"{self.ACTIVITY_FULL_ROWS + 1}.0", "end")
                line_count = int(tb.index("end-1c").split(".")[0])
                if line_count > LOG_HISTORY:
                    tb.delete(f"{LOG_HISTORY + 1}.0", "end")
            except Exception:
                pass
        box.configure(state="disabled")

    def _cycle_log_filter(self):
        """Step through the tags actually present, then back to all of them.

        The frame draws a dropdown labelled "All tags"; a canvas-hosted menu is
        a lot of machinery for a five-item list, so this cycles in place and
        the button always says which filter is live.
        """
        tags = [t for t in LOG_TAG_COLORS
                if any(self._log_row(m)[1] == t for m in self._log_lines)]
        order = [None] + sorted(tags)
        current = getattr(self, "_log_filter", None)
        nxt = order[(order.index(current) + 1) % len(order)] if current in order else None
        self._log_filter = nxt
        self._activity_filter_btn.configure(text=nxt or "All tags")
        try:
            self.console.configure(state="normal")
            self.console.delete("1.0", "end")
            self.console.configure(state="disabled")
        except Exception:
            return
        # History is oldest-first; the panel is newest-first, so replay reversed.
        self._append_log_batch(self.console,
                               list(reversed(self._log_lines[-LOG_HISTORY:])))

    def _copy_log(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(self._log_lines))
            self._log("[Nebula] Activity log copied to the clipboard.")
        except Exception as exc:
            self._log(f"[Nebula] Couldn't copy the log: {exc}")

    # ---- recording indicator (pulsing dot + elapsed timer + live storage) ----
    def _update_bitrate(self, duration_ms, written_bytes):
        """Fill the Bitrate readout from two successive GetRecordStatus polls.

        The frame draws "14.2 Mb/s". OBS's status carries no bitrate field, so
        rather than print a plausible number this derives the real one from how
        many bytes actually landed between polls. Until there are two samples
        far enough apart to be meaningful it shows nothing - an honest blank,
        not a made-up figure (see CLAUDE.md's no-fabricated-data rule).
        """
        prev = getattr(self, "_bitrate_sample", None)
        self._bitrate_sample = (duration_ms, written_bytes)
        if not prev:
            return
        d_ms = duration_ms - prev[0]
        d_bytes = written_bytes - prev[1]
        # A short or backwards interval (a paused recording, a restarted file)
        # gives a meaningless rate; wait for the next pair instead.
        if d_ms < 500 or d_bytes < 0:
            return
        mbits = (d_bytes * 8.0) / (d_ms / 1000.0) / 1_000_000.0
        self.bg.itemconfigure(self._readouts["bitrate"][1], text=f"{mbits:.1f} Mb/s")
        # 7a's RAM estimate is (bitrate / 8) x seconds x 1.1, and this is the
        # only place a real bitrate exists. Until a recording has produced one,
        # the module shows no estimate rather than one from a guessed bitrate.
        self._last_bitrate_mbps = mbits
        self._refresh_replay_module()

    def _poll_obs_status(self):
        """Source of truth for the timer/storage/pulse is OBS's own
        GetRecordStatus, not a client-side timestamp taken when the monitor
        merely *decided* to record - if OBS is disconnected or a start
        request silently failed, a client-side timer would keep counting
        even though nothing is actually being recorded."""
        is_recording = False
        is_paused = False
        if self.obs.connected:
            try:
                status = self.obs.get_record_status()
                is_recording = bool(status.get("outputActive"))
                is_paused = bool(status.get("outputPaused"))
                if is_recording:
                    total_seconds = status.get("outputDuration", 0) // 1000
                    hh, rem = divmod(total_seconds, 3600)
                    mm, ss = divmod(rem, 60)
                    self._tray_elapsed = f"{hh:02d}:{mm:02d}:{ss:02d}"
                    written = status.get("outputBytes", 0)
                    # The tray tooltip and the mini overlay still want these,
                    # so they're computed regardless - only the hero's own
                    # canvas items need the card to exist.
                    if self._hero_present():
                        self.bg.itemconfigure(self.timer_label_id, text=self._tray_elapsed)
                        self.bg.itemconfigure(self.storage_label_id,
                                              text=_format_bytes(written))
                        self._update_bitrate(status.get("outputDuration", 0), written)
            except OBSError:
                pass

        was = (self._is_recording, self._is_paused, self._obs_connected)
        self._is_paused = is_paused
        self._is_recording = is_recording
        self._obs_connected = bool(self.obs.connected)
        if was != (is_recording, is_paused, self._obs_connected):
            self._update_tray_tooltip()   # icon + tooltip follow the real state

        if not is_recording:
            self._bitrate_sample = None
            self._tray_elapsed = ""
        if self._mini:
            self._mini_update()

        # The hero card owns the badge/border/readout visibility; pick the state
        # that matches what OBS and the monitor are actually doing right now.
        if not self.obs.connected:
            state = "disconnected"
        elif is_recording and is_paused:
            state = "paused"
        elif is_recording:
            state = "recording"
        else:
            state = "watching"
        if state != self._hero_state:
            self._set_hero_state(state)

        # Only enablement here - the label, binding and emphasis belong to
        # _set_hero_state, which is the one place the state enum is expressed.
        # "Retry now" has to stay clickable precisely when OBS is unreachable.
        # Not while customising: "Content while editing: pointer-events:none".
        # The poll would otherwise re-enable the hero's button a beat after
        # edit mode had deliberately made it inert.
        if not getattr(self, "_customising", False) and self._hero_present():
            self._set_enabled(self.record_toggle_btn,
                              self.obs.connected or state == "disconnected",
                              text_color=self._hero_primary_text)

        # A second is right when you're watching the timer tick; while hidden in
        # the tray nothing renders it, so back off. The monitor thread drives the
        # actual recording independently of this poll.
        self._poll_job = self.root.after(
            1000 if self._visible else 5000, self._poll_obs_status)

    def _poll_now(self):
        """Bring the next status poll forward without starting a second chain.

        _poll_obs_status reschedules itself, so calling it directly would leave
        two self-perpetuating timers running - the same mistake that once made
        the toast drain at double speed. Cancel the pending one first.
        """
        job = getattr(self, "_poll_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            self._poll_job = None
        self._poll_obs_status()

    # ---- transport: the hero buttons, the tray menu and the mini overlay ----
    #
    # These used to branch on self._is_recording / self._is_paused. Those flags
    # come from a poll that runs once a second (once every five while the
    # window is hidden), so they are stale for up to a second - long enough to
    # press Stop and then Pause before the state catches up. Not hypothetical:
    #
    #     23:05:07 [Manual] Recording stopped.
    #     23:05:08 [Manual] Recording paused.
    #     23:05:24 [OBS] Failed to resume: ResumeRecord failed: unknown error
    #
    # That is PauseRecord sent to a recording which had already ended, logged
    # as a success, leaving the card offering a Resume that OBS then refused.
    #
    # So every transport command re-reads GetRecordStatus and decides from
    # that, and the log line says what actually happened rather than what was
    # asked for. It runs on a worker because each call is a blocking socket
    # round-trip; OBSClient serialises them against the poll internally.

    def _toggle_record(self):
        """Manual override, independent of auto-detection. A stop arms hold-off
        so the monitor does not bounce straight back into StartRecord; a start
        clears that hold-off."""
        self._transport("record")

    def _toggle_pause(self):
        """Pause/resume the in-progress recording. The monitor also pauses on
        idle by itself; this is the manual equivalent from the hero card."""
        self._transport("pause")

    def _transport(self, action):
        if getattr(self, "_transport_busy", False):
            return
        # 7c: "Below disk_block_below_gb the hero card refuses to start and
        # offers the cull - better than a failed recording."
        if action == "record" and not self._is_recording:
            ok, reason = self.can_start_recording()
            if not ok:
                self._log(f"[Storage] Refused to start: {reason}")
                self._toast_replace("error", reason)
                return
        self._transport_busy = True
        # Capture hold-off context on the Tk thread before the worker runs.
        prior_target = self.monitor._recording_target
        hold_basename = prior_target[1] if prior_target else None
        hold_name = prior_target[2] if prior_target else None

        def worker():
            result = {"action": action, "stopped": False,
                      "event": None, "outcome": None, "problem": None,
                      "hold_basename": hold_basename, "hold_name": hold_name}
            try:
                status = self.obs.get_record_status()
                recording = bool(status.get("outputActive"))
                paused = bool(status.get("outputPaused"))
                if action == "record":
                    if recording:
                        self.obs.stop_record()
                        result.update(stopped=True, event="stop",
                                      outcome="Recording stopped.")
                    elif (self.monitor._hold_off
                          and self.monitor._hold_off_pending is not None):
                        # Accept the re-record toast without a free StartRecord
                        # into whatever directory OBS currently has set.
                        self.monitor.accept_record_prompt()
                        result.update(event="start",
                                      outcome="Recording started.")
                    else:
                        self.obs.start_record()
                        result.update(event="start", outcome="Recording started.")
                elif not recording:
                    # Nothing to pause. Say so, rather than sending PauseRecord
                    # into the void and reporting it as a success.
                    result["outcome"] = "Nothing is recording - nothing to pause."
                elif paused:
                    self.obs.resume_record()
                    result.update(event="resume", outcome="Recording resumed.")
                else:
                    self.obs.pause_record()
                    result.update(event="pause", outcome="Recording paused.")
            except OBSError as exc:
                # Bind before the closure: `exc` is unbound the moment this
                # except block exits, so a lambda that captured it would die
                # with NameError inside the Tk callback (CLAUDE.md).
                result["problem"] = str(exc)
            self.root.after(0, lambda r=result: self._transport_done(r))

        threading.Thread(target=worker, daemon=True).start()

    def _transport_done(self, result):
        self._transport_busy = False
        if result["problem"]:
            verb = "start/stop" if result["action"] == "record" else "pause/resume"
            self._log(f"[Manual] Could not {verb} recording: {result['problem']}")
            self._toast_replace("error", f"OBS refused the {verb} command")
        else:
            self._log(f"[Manual] {result['outcome']}")
            if result["stopped"]:
                self.monitor._recording_target = None
                self.monitor.note_manual_stop(
                    result.get("hold_basename"), result.get("hold_name"))
                # "Refresh: on launch, on rec_stop, every 15 min."
                self._refresh_forecast()
                self._refresh_ribbon()
                self._refresh_stat_tiles()
                name = result.get("hold_name") or "Recording"
                self._toast_replace("stop", name)
            elif result.get("event") == "start":
                # Manual Record clears hold-off so auto-monitor can take over.
                self.monitor.clear_hold_off()
        # Don't make the card wait up to a second to catch up with a button the
        # user just pressed - that lag is what made double-presses possible.
        self._poll_now()

    def _on_record_prompt(self, basename, display_name, reason, target):
        """Monitor thread → ask whether to start recording under hold-off."""
        # Bind locals before the closure (deferred-callback trap).
        b, n, r, t = basename, display_name, reason, target
        self._ui(lambda: self._show_record_prompt(b, n, r, t))

    def _show_record_prompt(self, basename, display_name, reason, target):
        if reason == "same":
            title = "Record again?"
            sub = display_name or basename or "this game"
        else:
            title = "Record this game?"
            sub = display_name or basename or "this game"
        # Keep references the button handlers need; accept reads pending from Monitor.
        def accept():
            toast = getattr(self, "_toast", None)
            if toast is not None:
                toast["on_timeout"] = None
            self.monitor.accept_record_prompt()
            self._toast_dismiss_now()
            self._poll_now()

        def dismiss():
            toast = getattr(self, "_toast", None)
            if toast is not None:
                toast["on_timeout"] = None
            self.monitor.dismiss_record_prompt(basename)
            self._toast_dismiss_now()

        self._toast_replace(
            "prompt", sub, {"title": title},
            actions=[("Record", accept), ("Not now", dismiss)],
            on_timeout=dismiss,
        )

    def _toast_dismiss_now(self):
        toast = getattr(self, "_toast", None)
        if not toast:
            return
        try:
            if toast["popup"].winfo_exists():
                toast["dismissing"] = True
                toast["remaining"] = 0
                self._toast_fade_out(toast)
        except Exception:
            self._toast = None

    def _flash_status_card(self):
        """A brief brighter-border pulse on the status card glass panel
        whenever the detected game changes, so a switch is visually
        confirmed even if you're not staring at the timer/name text."""
        x, y, w, h = self._status_card_geom
        steps = [1.0, 0.6, 0.25, 0.0]
        border = dv.HERO_STATES.get(self._hero_state, {}).get("tint") or CARD_BORDER

        def step(i=0):
            if i >= len(steps):
                # Settle back on the border the current hero state owns, not the
                # generic default - otherwise a flash would wash out the state tint.
                self._regen_hero_shell(x, y, w, h, border, 70)
                return
            border_alpha = int(70 + (230 - 70) * steps[i])
            self._regen_hero_shell(x, y, w, h, border, min(border_alpha, 255))
            self.root.after(110, lambda: step(i + 1))

        step()

    # ---- notifications ----
    # ---- the toast (frame 2i) ----
    # The spec calls this one of "the three surfaces the last build got wrong"
    # and its first rule is the architecture, not the look:
    #
    #   "One toast, ever. A new event replaces the current one in place -
    #    never a stack, never a queue."
    #
    # So there is exactly one Toplevel for the whole process life. The first
    # event builds it; every later event *mutates* it and resets the drain.
    # The build order in the spec is explicit that this path comes first:
    # "Build the replace path before the visuals."
    #
    # v2 destroyed and rebuilt the window per event, which is a queue of one
    # with extra steps - and it flickered, because a fresh Toplevel maps at the
    # new position rather than updating the one already on screen.
    #
    # Unlike the main window, animating here is free: a Toplevel is its own
    # surface, so a fade or a 16px rise never composites the dashboard.

    TOAST_W, TOAST_H = dv.TOAST_W, dv.TOAST_H
    TOAST_PROMPT_W, TOAST_PROMPT_H = dv.TOAST_PROMPT_W, dv.TOAST_PROMPT_H

    def _monitor_workarea(self, primary=False):
        """Work area of the primary monitor, or the monitor under the pointer.

        Returns (left, top, right, bottom) in physical pixels. The work area
        already excludes the taskbar.
        """
        try:
            from ctypes import windll, byref, sizeof, Structure, c_long, c_ulong, c_wchar

            class POINT(Structure):
                _fields_ = [("x", c_long), ("y", c_long)]

            class RECT(Structure):
                _fields_ = [("left", c_long), ("top", c_long),
                            ("right", c_long), ("bottom", c_long)]

            class MONITORINFOEXW(Structure):
                _fields_ = [("cbSize", c_ulong), ("rcMonitor", RECT),
                            ("rcWork", RECT), ("dwFlags", c_ulong),
                            ("szDevice", c_wchar * 32)]

            if primary:
                # MONITOR_DEFAULTTOPRIMARY — toast always on the main screen.
                monitor = windll.user32.MonitorFromPoint(POINT(0, 0), 1)
            else:
                pt = POINT()
                windll.user32.GetCursorPos(byref(pt))
                monitor = windll.user32.MonitorFromPoint(pt, 2)  # NEAREST
            info = MONITORINFOEXW()
            info.cbSize = sizeof(MONITORINFOEXW)
            if windll.user32.GetMonitorInfoW(monitor, byref(info)):
                r = info.rcWork
                return r.left, r.top, r.right, r.bottom
        except Exception:
            pass
        return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48)

    def _toast_workarea(self):
        """Primary-monitor work area — toast never follows a secondary screen."""
        return self._monitor_workarea(primary=True)

    def _toast_content(self, event, display_name, details):
        """Everything the toast renders, resolved from an event name."""
        tint = dv.TOAST_TINTS.get(event, ACCENT)
        role = {"start": "start", "stop": "square", "pause": "pause",
                "resume": "resume", "error": "disconnected",
                "prompt": "start"}.get(event, "start")
        glyph = ICON_GLYPHS[dv.ICONS[role]] if role in dv.ICONS else ICON_GLYPHS[role]
        title = {
            "start": "Recording started", "stop": "Recording stopped",
            "pause": "Recording paused", "resume": "Recording resumed",
            "error": "Something went wrong",
            "prompt": "Record again?",
        }.get(event, str(event))
        if event == "pause" and details and details.get("reason") == "session":
            title = "Stream ended — paused"
        if details and details.get("title"):
            title = details["title"]

        parts = []
        if details:
            duration = details.get("duration")
            if duration is not None:
                mm, ss = divmod(int(duration), 60)
                parts.append(f"{mm:02d}:{ss:02d}")
            size = details.get("size")
            if size is not None:
                parts.append(_format_bytes(size))
        return {"tint": tint, "glyph": glyph, "title": title,
                "sub": display_name, "detail": " · ".join(parts),
                "event": event}

    def _show_notification(self, event, display_name, details=None):
        """Entry point - called from the monitor's thread, so it marshals."""
        details = details or {}
        if event == "pause" and "reason" in details:
            self._pause_reason = details.get("reason")
        elif event in ("resume", "stop", "start"):
            self._pause_reason = None

        def apply():
            # Refresh the paused eyebrow as soon as the reason lands - don't
            # wait for the next GetRecordStatus poll to re-enter _set_hero_state.
            if event in ("pause", "resume") and self._hero_present():
                self._set_hero_state(self._hero_state)
            self._toast_replace(event, display_name, details)
            self._update_tray_tooltip()

        self._ui(apply)

    def _toast_replace(self, event, display_name, details=None, actions=None,
                       on_timeout=None):
        """The replace path. Builds the single toast on first use, then only
        ever updates it. `actions` is an optional list of (label, callback)
        for confirmation toasts (hold-off re-record prompts)."""
        content = self._toast_content(event, display_name, details)
        content["actions"] = list(actions or [])
        want_prompt = bool(content["actions"])
        toast = self._toast
        need_rebuild = (
            toast is None
            or not toast["popup"].winfo_exists()
            or bool(toast.get("actions")) != want_prompt
        )
        was_dismissing = bool(toast and toast.get("dismissing"))
        reused = not need_rebuild
        if need_rebuild:
            if toast is not None:
                try:
                    toast["popup"].destroy()
                except Exception:
                    pass
                self._toast = None
            toast = self._toast = self._toast_build(prompt=want_prompt)
        self._toast_apply(toast, content)

        # Reset the life regardless of where it was - "Replacing an event
        # resets the line to full." Prompt toasts linger longer so the user
        # can actually tap a button.
        life = dv.TOAST_PROMPT_LIFE_MS if want_prompt else dv.TOAST_LIFE_MS
        toast["life"] = life
        toast["remaining"] = life
        toast["actions"] = content["actions"]
        toast["on_timeout"] = on_timeout
        if was_dismissing:
            # Rescued mid-fade — play the entrance again rather than snapping.
            toast["dismissing"] = False
            self._toast_rise_in(toast)
        elif reused:
            # Same window, new event — soft opacity pulse so it doesn't hard-cut.
            self._toast_swap_pulse(toast)
        if not toast["ticking"]:
            toast["ticking"] = True
            self._toast_tick(toast)

    def _toast_pill_photo(self, sw, sh, radius, chromakey=True):
        """Nebula crop + two-layer glass, masked to a capsule.

        When `chromakey` is True (Windows), outside the pill is TOAST_KEY so
        `-transparentcolor` can punch true rounded ends. Otherwise the outside
        stays fully transparent in the RGBA buffer and we composite onto the
        canvas ground colour — no green flash on Linux/mac.
        """
        key = tuple(int(dv.TOAST_KEY.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        surface = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))

        crop = (self.nebula.resize((sw, sh))
                if self.nebula.size != (sw, sh)
                else self.nebula.copy())
        if crop.mode != "RGBA":
            crop = crop.convert("RGBA")
        mask = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, sw - 1, sh - 1], radius=radius, fill=255)
        surface.paste(crop, (0, 0), mask)

        # No drawn stroke on the shell — chromakey + the pill mask already
        # silhouette the capsule; a border reads as a grey rectangular frame
        # once DWM composites the toplevel.
        shell = make_glass_tile(
            sw, sh, CARD_TINT, tint_alpha=210, radius=radius,
            border_hex=CARD_BORDER, border_alpha=0)
        surface = Image.alpha_composite(surface, shell)

        pad = self._S(dv.TOAST_PAD)
        core_w, core_h = max(1, sw - 2 * pad), max(1, sh - 2 * pad)
        core_r = max(1, radius - pad)
        core = make_glass_tile(
            core_w, core_h, CARD_CORE, tint_alpha=200, radius=core_r,
            border_hex=EDGE, border_alpha=0)
        layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        layer.paste(core, (pad, pad), core)
        surface = Image.alpha_composite(surface, layer)

        if chromakey:
            # Flatten: Tk chromakey needs opaque key pixels, not alpha zeros.
            flat = Image.new("RGB", (sw, sh), key)
            flat.paste(surface.convert("RGB"), mask=surface.split()[3])
            return to_photo(flat)
        return to_photo(surface)

    def _toast_canvas_pill(self, canvas, x, y, w, h, fill, tags=()):
        """Draw a filled capsule (oval caps + body) in design units."""
        r = h / 2.0
        ids = [
            canvas.create_oval(
                x, y, x + h, y + h, fill=fill, outline="", tags=tags),
            canvas.create_oval(
                x + w - h, y, x + w, y + h, fill=fill, outline="", tags=tags),
            canvas.create_rectangle(
                x + r, y, x + w - r, y + h, fill=fill, outline="", tags=tags),
        ]
        return ids

    def _toast_draw_action_pill(self, canvas, x, y, w, h, label,
                                primary=True, tag="toast_btn"):
        """Nested pill CTA — outer shell + inner core (Nebula two-layer)."""
        # Outer shell: hairline wash so the button reads as machined, not flat.
        shell_fill = EDGE
        shell = self._toast_canvas_pill(
            canvas, x, y, w, h, shell_fill, tags=(tag,))
        inset = 2
        if primary:
            # Stronger wash than ACCENT_TINT so the primary CTA reads on the
            # dark capsule core (flat tint was disappearing into the glass).
            core_fill = dv.over(dv.ACCENT, 0.32, dv.CARD_CORE)
            text_fill = TEXT
        else:
            core_fill = dv.over(dv.TEXT, 0.045, dv.CARD_CORE)
            text_fill = MUTED
        core = self._toast_canvas_pill(
            canvas, x + inset, y + inset, w - 2 * inset, h - 2 * inset,
            core_fill, tags=(tag,))
        text = canvas.create_text(
            x + w / 2, y + h / 2, text=label, fill=text_fill,
            font=dv.font(12, 500), tags=(tag,))
        return shell, core, text

    def _toast_build(self, prompt=False):
        w = self.TOAST_PROMPT_W if prompt else self.TOAST_W
        h = self.TOAST_PROMPT_H if prompt else self.TOAST_H
        sw, sh = self._S(w), self._S(h)
        # Standard toasts are true capsules (r = H/2). Prompt toasts are taller
        # for stacked copy + actions — full H/2 there reads as a bulb. Soft
        # squircle keeps the family resemblance without the peanut silhouette.
        radius = sh // 2 if not prompt else self._S(dv.CARD_LAYERS["tray"][0])
        key = dv.TOAST_KEY

        popup = ctk.CTkToplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.0)
        try:
            popup.configure(fg_color=key)
        except Exception:
            pass

        left, top, right, bottom = self._toast_workarea()
        margin = self._S(dv.TOAST_MARGIN)
        x = right - sw - margin
        y_end = bottom - sh - margin
        popup.geometry(f"{sw}x{sh}+{x}+{y_end + self._S(dv.TOAST_IN_RISE)}")
        # Do NOT apply_rounded_corners here. DWM's rounded HWND draws a grey
        # rectangular silhouette around the chromakey pill — the outline we
        # want gone. The pill mask + transparentcolor is the silhouette.

        canvas = ScaledCanvas(
            tk.Canvas(popup, width=sw, height=sh, highlightthickness=0, bd=0,
                      bg=BASE_BG),
            self.scale)
        canvas.pack(fill="both", expand=True)
        # Chromakey only on Windows - elsewhere `-transparentcolor` is a no-op
        # and the key colour would show as a neon green fringe.
        keyed = sys.platform == "win32"
        if keyed:
            try:
                popup.configure(fg_color=key)
                canvas._c.configure(bg=key)
                popup.wm_attributes("-transparentcolor", key)
            except Exception:
                keyed = False
                try:
                    popup.configure(fg_color=BASE_BG)
                    canvas._c.configure(bg=BASE_BG)
                except Exception:
                    pass
            else:
                # Force sharp HWND corners so DWM doesn't stroke a frame.
                self._toast_donot_round(popup)
        else:
            try:
                popup.configure(fg_color=BASE_BG)
            except Exception:
                pass

        photo = self._toast_pill_photo(sw, sh, radius, chromakey=keyed)
        self._keep_image(photo)
        canvas.create_image(0, 0, anchor="nw", image=photo)

        # Prompt: same strip as status — chip + stacked copy, pills on the right.
        if prompt:
            cy = h / 2
        else:
            cy = h / 2
        chip_r = 14
        chip_cx, chip_cy = (28, cy) if prompt else (28, cy)
        chip = canvas.create_oval(
            chip_cx - chip_r, chip_cy - chip_r,
            chip_cx + chip_r, chip_cy + chip_r,
            fill=ACCENT_TINT, outline="")
        icon = canvas.create_text(
            chip_cx, chip_cy, text="", fill=ACCENT, font=(ICON_FONT, -13))
        title_y = (cy - 9) if prompt else cy
        sub_y = (cy + 10) if prompt else cy
        text_x = 54
        title = canvas.create_text(
            text_x, title_y, anchor="w", text="", fill=TEXT, font=dv.font(14, 500))
        sep = canvas.create_text(
            text_x, cy, anchor="w", text="·", fill=FAINT, font=dv.font(14, 500),
            state="hidden")
        sub = canvas.create_text(
            text_x, sub_y, anchor="w", text="", fill=MUTED, font=dv.type_font("meta"))
        detail = canvas.create_text(
            text_x, cy, anchor="w", text="", fill=FAINT,
            font=dv.font(12, mono=True), state="hidden")

        # Soft Nebula dust near the chip - event-tint, motion on the tick.
        dust_items = []
        dust_base = []
        dust_home = []
        for dx, dy, r, alpha in dv.TOAST_DUST:
            d = canvas.create_oval(
                chip_cx + dx - r, chip_cy + dy - r,
                chip_cx + dx + r, chip_cy + dy + r,
                fill=dv.over(ACCENT, alpha, CARD_CORE), outline="",
                tags=("toast_dust",))
            dust_items.append(d)
            dust_base.append(alpha)
            dust_home.append((dx, dy, r))

        # Action pills on the right — same strip as status, not a second row.
        btn_items = []
        if prompt:
            bh = dv.TOAST_PROMPT_BTN_H
            specs = [
                ("Record", dv.TOAST_PROMPT_PRIMARY_W, True),
                ("Not now", dv.TOAST_PROMPT_SECONDARY_W, False),
            ]
            total_bw = sum(bw for _l, bw, _p in specs) + dv.TOAST_PROMPT_BTN_GAP * (len(specs) - 1)
            bx = w - dv.TOAST_TEXT_INSET - total_bw
            by = (h - bh) / 2
            for i, (label, bw, primary) in enumerate(specs):
                tag = f"toast_btn_{i}"
                shell, core, text = self._toast_draw_action_pill(
                    canvas, bx, by, bw, bh, label, primary=primary, tag=tag)
                btn_items.append({
                    "shell": shell, "core": core, "text": text, "tag": tag,
                    "x": bx, "y": by, "w": bw, "h": bh, "primary": primary,
                })
                bx += bw + dv.TOAST_PROMPT_BTN_GAP

        # 2px drain, inset, left-anchored (spec: scaleX 1→0, origin left).
        track_x0, track_x1 = 22, w - 22
        bar_y = h - 9
        canvas.create_rectangle(
            track_x0, bar_y, track_x1, bar_y + dv.TOAST_DRAIN_H,
            fill=EDGE, outline="")
        drain = canvas.create_rectangle(
            track_x0, bar_y, track_x1, bar_y + dv.TOAST_DRAIN_H,
            fill=ACCENT, outline="")

        toast = {
            "popup": popup, "canvas": canvas, "chip": chip, "icon": icon,
            "title": title, "sep": sep, "sub": sub, "detail": detail,
            "drain": drain, "dust": dust_items, "dust_base": dust_base,
            "dust_home": dust_home, "dust_origin": (chip_cx, chip_cy),
            "dust_style": "drift", "dust_phase": [], "dust_speed": 1.0,
            "dust_amp": 1.0, "dust_t0": time.time(),
            "track": (track_x0, track_x1, bar_y), "geom": (sw, sh, x, y_end),
            "row_y": cy, "title_y": title_y, "sub_y": sub_y, "text_x": text_x,
            "remaining": dv.TOAST_LIFE_MS, "life": dv.TOAST_LIFE_MS,
            "hovering": False, "ticking": False, "dismissing": False,
            "has_detail": False, "actions": [], "buttons": btn_items,
            "prompt": prompt, "on_timeout": None, "tint": ACCENT,
            "event": "start",
        }

        def on_enter(_e):
            toast["hovering"] = True          # "Hover freezes the drain"

        def on_leave(_e):
            toast["hovering"] = False

        def on_click(e):
            if toast.get("actions"):
                try:
                    items = canvas.find_overlapping(e.x, e.y, e.x, e.y)
                except Exception:
                    items = ()
                for i, btn in enumerate(toast["buttons"]):
                    tags = set()
                    for item in items:
                        tags.update(canvas.gettags(item))
                    if btn["tag"] in tags and i < len(toast["actions"]):
                        _label, callback = toast["actions"][i]
                        try:
                            callback()
                        except Exception as exc:
                            self._log(f"[Toast] Action failed: {exc}")
                        return
                return  # body click does nothing on prompt toasts
            self.show()                        # "Click anywhere focuses the window"

        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<Button-1>", on_click)

        self._toast_rise_in(toast)
        return toast

    def _toast_layout_row(self, toast):
        """Pack title · sub · detail on one baseline; ellipsize to the pill.

        Duration / size (detail) outranks the game name when space is tight —
        a stop toast that keeps "Helldivers 2" but drops "01:35 · 420 MB" is
        the wrong trade. Prompt toasts use the stacked layout instead.
        """
        if toast.get("prompt"):
            self._toast_layout_prompt(toast)
            return
        canvas = toast["canvas"]
        x = toast["text_x"]
        y = toast["row_y"]
        gap = 8
        detail_text = toast.get("detail_text") or ""
        # Keep text clear of the capsule's curved ends (radius ≈ H/2).
        w = self.TOAST_PROMPT_W if toast.get("prompt") else self.TOAST_W
        max_x = w - dv.TOAST_TEXT_INSET

        def _right(item):
            try:
                bbox = canvas.bbox(item)
                return (bbox[2] / self.scale) if bbox else x
            except Exception:
                return x

        def _width(item):
            try:
                bbox = canvas.bbox(item)
                if not bbox:
                    return 0.0
                return (bbox[2] - bbox[0]) / self.scale
            except Exception:
                return 0.0

        def _ellipsize(item, text, left, limit):
            """Trim from the end until the item's right edge is ≤ limit."""
            if not text:
                canvas.itemconfigure(item, text="", state="hidden")
                return
            candidate = text
            while True:
                shown = candidate if candidate == text else (candidate.rstrip() + "…")
                canvas.itemconfigure(item, text=shown, state="normal")
                canvas.coords(item, left, y)
                if _right(item) <= limit or len(candidate) <= 1:
                    if _right(item) > limit:
                        canvas.itemconfigure(item, text="", state="hidden")
                    return
                candidate = candidate[:-1]

        title_text = canvas.itemcget(toast["title"], "text") or ""
        sub_text = canvas.itemcget(toast["sub"], "text") or ""
        has_detail = bool(toast.get("has_detail") and detail_text)

        canvas.itemconfigure(toast["sep"], state="hidden")
        canvas.itemconfigure(toast["sub"], text="", state="hidden")
        canvas.itemconfigure(toast["detail"], text="", state="hidden")

        _ellipsize(toast["title"], title_text, x, max_x)
        tx = _right(toast["title"]) + gap
        if tx + 12 > max_x:
            return

        # Reserve room for the full detail string on the right when present.
        # Include the middot prefix we'll add when a sub is also shown.
        detail_w = 0.0
        detail_reserve = ""
        if has_detail:
            detail_reserve = (("·  " if sub_text else "") + detail_text)
            canvas.itemconfigure(toast["detail"], text=detail_reserve, state="normal")
            canvas.coords(toast["detail"], tx, y)
            detail_w = _width(toast["detail"])
            # If detail alone cannot fit after the title, drop the sub and
            # ellipsize detail against the remaining width.
            if tx + detail_w > max_x and not sub_text:
                _ellipsize(toast["detail"], detail_text, tx, max_x)
                return
            if tx + detail_w > max_x and sub_text:
                # Prefer full meta over any game name when they cannot coexist.
                sub_text = ""
                detail_reserve = detail_text
                canvas.itemconfigure(toast["detail"], text=detail_reserve)
                detail_w = _width(toast["detail"])
                if tx + detail_w > max_x:
                    _ellipsize(toast["detail"], detail_text, tx, max_x)
                    return

        if sub_text:
            canvas.itemconfigure(toast["sep"], state="normal")
            canvas.coords(toast["sep"], tx, y)
            tx = _right(toast["sep"]) + gap
            # Sub fills the middle; leave gap + detail_w for the trailing meta.
            sub_limit = max_x - ((detail_w + gap) if has_detail else 0)
            if tx < sub_limit:
                _ellipsize(toast["sub"], sub_text, tx, sub_limit)
                shown = canvas.itemcget(toast["sub"], "text") or ""
                # A 1–3 glyph stub ("He…") reads as broken — hide it instead.
                bare = shown.rstrip("…").strip()
                if canvas.itemcget(toast["sub"], "state") == "hidden" or len(bare) < 4:
                    canvas.itemconfigure(toast["sep"], state="hidden")
                    canvas.itemconfigure(toast["sub"], text="", state="hidden")
                    tx = _right(toast["title"]) + gap
                else:
                    tx = _right(toast["sub"]) + gap
            else:
                canvas.itemconfigure(toast["sep"], state="hidden")
                canvas.itemconfigure(toast["sub"], text="", state="hidden")
                tx = _right(toast["title"]) + gap
        else:
            canvas.itemconfigure(toast["sep"], state="hidden")

        if has_detail:
            shown_sub = canvas.itemcget(toast["sub"], "state") != "hidden" and (
                canvas.itemcget(toast["sub"], "text") or "")
            text = (("·  " if shown_sub else "") + detail_text)
            canvas.itemconfigure(toast["detail"], text=text, state="normal")
            if shown_sub:
                left = max(tx, max_x - _width(toast["detail"]))
                canvas.coords(toast["detail"], left, y)
                if _right(toast["detail"]) > max_x + 0.5:
                    # Sub ate the reservation — drop sub, keep full meta.
                    canvas.itemconfigure(toast["sep"], state="hidden")
                    canvas.itemconfigure(toast["sub"], text="", state="hidden")
                    tx = _right(toast["title"]) + gap
                    _ellipsize(toast["detail"], detail_text, tx, max_x)
            else:
                _ellipsize(toast["detail"], detail_text, tx, max_x)

    def _toast_layout_prompt(self, toast):
        """Stacked title over game name — no middot collision, full game name."""
        canvas = toast["canvas"]
        x = toast["text_x"]
        title_y = toast.get("title_y", toast["row_y"] - 9)
        sub_y = toast.get("sub_y", toast["row_y"] + 12)
        max_x = self.TOAST_PROMPT_W - dv.TOAST_TEXT_INSET

        def _fit(item, text, left, y, limit):
            if not text:
                canvas.itemconfigure(item, text="", state="hidden")
                return
            candidate = text
            while True:
                shown = (candidate if candidate == text
                         else (candidate.rstrip() + "…"))
                canvas.itemconfigure(item, text=shown, state="normal")
                canvas.coords(item, left, y)
                try:
                    bbox = canvas.bbox(item)
                    right = (bbox[2] / self.scale) if bbox else left
                except Exception:
                    right = left
                if right <= limit or len(candidate) <= 1:
                    if right > limit:
                        canvas.itemconfigure(item, text="", state="hidden")
                    return
                candidate = candidate[:-1]

        canvas.itemconfigure(toast["sep"], state="hidden")
        canvas.itemconfigure(toast["detail"], text="", state="hidden")
        title_text = canvas.itemcget(toast["title"], "text") or ""
        sub_text = canvas.itemcget(toast["sub"], "text") or ""
        _fit(toast["title"], title_text, x, title_y, max_x)
        _fit(toast["sub"], sub_text, x, sub_y, max_x)

    def _toast_apply(self, toast, content):
        canvas = toast["canvas"]
        tint = content["tint"]
        toast["tint"] = tint
        toast["event"] = content.get("event") or "start"
        canvas.itemconfigure(toast["chip"], fill=_tint_for(tint))
        canvas.itemconfigure(toast["icon"], text=content["glyph"], fill=tint)
        canvas.itemconfigure(toast["title"], text=content["title"])
        canvas.itemconfigure(toast["sub"], text=content["sub"] or "")
        toast["detail_text"] = content["detail"] or ""
        toast["has_detail"] = bool(toast["detail_text"])
        actions = content.get("actions") or []
        toast["actions"] = actions
        for i, btn in enumerate(toast.get("buttons") or []):
            label = actions[i][0] if i < len(actions) else ""
            state = "normal" if i < len(actions) else "hidden"
            canvas.itemconfigure(btn["text"], text=label, state=state)
            for part in list(btn.get("shell") or []) + list(btn.get("core") or []):
                canvas.itemconfigure(part, state=state)
            if btn.get("rect") is not None:
                canvas.itemconfigure(btn["rect"], state=state)
        canvas.itemconfigure(toast["drain"], fill=tint)
        self._toast_layout_row(toast)
        self._toast_set_drain(toast, 1.0)
        self._toast_seed_dust(toast)
        self._toast_animate_dust(toast, force=True)
        # Re-assert topmost: another window may have been raised over it while
        # the toast sat idle between events.
        try:
            toast["popup"].attributes("-topmost", True)
        except Exception:
            pass

    def _toast_donot_round(self, window):
        """Tell DWM not to round this HWND — rounded preference paints a grey
        rectangular frame around a chromakey pill."""
        try:
            window.update_idletasks()
            hwnd = (ctypes.windll.user32.GetParent(window.winfo_id())
                    or window.winfo_id())
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWC_DONOTROUND = 1
            value = ctypes.c_int(DWMWC_DONOTROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

    def _toast_seed_dust(self, toast):
        """Fresh motion recipe each show: event flavour + random seed."""
        event = toast.get("event") or "start"
        style = dv.TOAST_DUST_STYLE.get(event, "drift")
        # Rare spice so a string of the same event isn't locked to one dance.
        if random.random() < 0.08:
            style = random.choice(tuple(set(dv.TOAST_DUST_STYLE.values())))
        n = len(toast.get("dust") or [])
        anchor = dv.TOAST_DUST_ANCHOR.get(style, "left")
        toast["dust_style"] = style
        toast["dust_anchor"] = anchor
        toast["dust_t0"] = time.time()
        # Quieter than the first busy pass, but still clearly alive.
        toast["dust_speed"] = random.uniform(0.7, 1.15)
        toast["dust_amp"] = random.uniform(0.65, 1.15)
        toast["dust_phase"] = [random.uniform(0, math.tau) for _ in range(n)]
        toast["dust_spin"] = [random.choice((-1.0, 1.0)) for _ in range(n)]
        # Soften at most one dot so the constellation stays readable.
        toast["dust_gain"] = [
            random.uniform(0.7, 0.9) if random.random() < 0.2 else 1.0
            for _ in range(n)
        ]
        w = self.TOAST_PROMPT_W if toast.get("prompt") else self.TOAST_W
        cy = toast.get("row_y") or (self.TOAST_H / 2)
        if anchor == "right":
            # Fan inward from the trailing end so dots stay inside the pill.
            toast["dust_origin"] = (w - 28, cy)
            toast["dust_mirror"] = -1.0
        else:
            toast["dust_origin"] = (24, cy)
            toast["dust_mirror"] = 1.0

    def _toast_animate_dust(self, toast, force=False):
        """Nebula dust — quieter motion, left or right by style.

        Toast is its own toplevel, so this never composites the dashboard.
        """
        dust = toast.get("dust") or []
        home = toast.get("dust_home") or []
        if not dust or len(home) != len(dust):
            return
        tint = toast.get("tint") or ACCENT
        ox, oy = toast.get("dust_origin") or (22, 28)
        mirror = float(toast.get("dust_mirror") or 1.0)
        style = toast.get("dust_style") or "drift"
        speed = float(toast.get("dust_speed") or 1.0)
        amp = float(toast.get("dust_amp") or 1.0)
        phases = toast.get("dust_phase") or [0.0] * len(dust)
        spins = toast.get("dust_spin") or [1.0] * len(dust)
        gains = toast.get("dust_gain") or [1.0] * len(dust)
        t = (time.time() - float(toast.get("dust_t0") or time.time())) * speed
        canvas = toast["canvas"]

        for i, item in enumerate(dust):
            dx0, dy0, r = home[i]
            dx0 = dx0 * mirror
            base = toast["dust_base"][i] * (gains[i] if i < len(gains) else 1.0)
            phase = phases[i] if i < len(phases) else i * 1.7
            spin = spins[i] if i < len(spins) else 1.0
            dist = math.hypot(dx0, dy0) or 1.0
            ux, uy = dx0 / dist, dy0 / dist

            if force:
                ox_i, oy_i = dx0, dy0
                wave = 0.9
            elif style == "burst":
                pulse = 0.5 + 0.5 * math.sin(t * 2.8 + phase)
                reach = (1.8 + 3.6 * pulse) * amp
                ox_i = dx0 + ux * reach
                oy_i = dy0 + uy * reach
                wave = 0.5 + 0.45 * pulse
            elif style == "sink":
                settle = min(1.0, t * 0.5)
                ox_i = dx0 * (1.0 - 0.28 * settle) + 1.0 * amp * math.sin(t + phase)
                oy_i = dy0 * (1.0 - 0.15 * settle) + settle * (2.8 * amp)
                wave = 0.65 - 0.2 * settle + 0.12 * math.sin(t * 1.2 + phase)
            elif style == "drift":
                ox_i = dx0 + amp * 3.0 * math.sin(t * 1.05 + phase)
                oy_i = dy0 + amp * 1.8 * math.sin(t * 0.7 + phase * 0.6)
                wave = 0.55 + 0.4 * (0.5 + 0.5 * math.sin(t * 1.7 + phase))
            elif style == "rise":
                lift = min(1.0, t * 0.7)
                ox_i = dx0 + amp * 1.2 * math.sin(t * 1.4 + phase)
                oy_i = dy0 - lift * (3.2 + 2.2 * amp) * (0.5 + 0.5 * math.sin(t + phase))
                wave = 0.5 + 0.45 * (0.4 + 0.6 * lift)
            elif style == "scatter":
                ox_i = dx0 + amp * 3.4 * math.sin(t * 4.0 * spin + phase)
                oy_i = dy0 + amp * 2.8 * math.cos(t * 3.2 * spin + phase * 1.3)
                wave = 0.4 + 0.5 * abs(math.sin(t * 4.5 + phase))
            else:  # orbit
                ang = phase + t * 1.15 * spin
                radius = dist * (0.88 + 0.18 * amp)
                ox_i = math.cos(ang) * radius
                oy_i = math.sin(ang) * radius * 0.72
                wave = 0.55 + 0.4 * (0.5 + 0.5 * math.sin(t * 1.5 + phase))

            alpha = max(0.08, min(0.95, base * wave))
            try:
                canvas.coords(
                    item,
                    ox + ox_i - r, oy + oy_i - r,
                    ox + ox_i + r, oy + oy_i + r)
                canvas.itemconfigure(item, fill=dv.over(tint, alpha, CARD_CORE))
            except Exception:
                pass

    def _toast_twinkle(self, toast, force=False):
        """Back-compat alias — dust now moves, not only twinkles."""
        self._toast_animate_dust(toast, force=force)

    def _toast_set_drain(self, toast, fraction):
        x0, x1, bar_y = toast["track"]
        try:
            toast["canvas"].coords(toast["drain"], x0, bar_y,
                                   x0 + (x1 - x0) * max(0.0, min(1.0, fraction)),
                                   bar_y + dv.TOAST_DRAIN_H)
        except Exception:
            pass

    def _toast_alpha(self, toast, value):
        try:
            toast["popup"].attributes("-alpha", max(0.0, min(1.0, value)))
        except Exception:
            pass

    def _toast_rise_in(self, toast):
        """Toast in: rise + fade, ease-out — readable, not an instant pop."""
        sw, sh, x, y_end = toast["geom"]
        rise = self._S(dv.TOAST_IN_RISE)
        steps = max(1, dv.TOAST_IN_MS // 16)
        toast["entering"] = True

        def step(i=0):
            if not toast["popup"].winfo_exists():
                toast["entering"] = False
                return
            if toast.get("dismissing"):
                toast["entering"] = False
                return
            t = min(1.0, i / steps)
            # Spec easing cubic-bezier(.32,.72,0,1) ≈ ease-out cubic here.
            eased = 1 - (1 - t) ** 3
            try:
                toast["popup"].geometry(
                    f"{sw}x{sh}+{x}+{int(y_end + rise * (1 - eased))}")
            except Exception:
                toast["entering"] = False
                return
            self._toast_alpha(toast, eased)
            if t < 1.0:
                toast["popup"].after(16, lambda: step(i + 1))
            else:
                toast["entering"] = False

        step()

    def _toast_swap_pulse(self, toast):
        """In-place replace: brief dim then settle, so content doesn't hard-cut."""
        if toast.get("dismissing") or toast.get("entering"):
            return
        steps = max(1, 180 // 16)

        def step(i=0):
            if not toast["popup"].winfo_exists() or toast.get("dismissing"):
                return
            t = min(1.0, i / steps)
            # Dip to ~0.45 then ease back to 1.
            if t < 0.35:
                alpha = 1.0 - (t / 0.35) * 0.55
            else:
                u = (t - 0.35) / 0.65
                alpha = 0.45 + 0.55 * (1 - (1 - u) ** 2)
            self._toast_alpha(toast, alpha)
            if t < 1.0:
                toast["popup"].after(16, lambda: step(i + 1))
            else:
                self._toast_alpha(toast, 1.0)

        step()

    def _toast_tick(self, toast):
        if not toast["popup"].winfo_exists():
            toast["ticking"] = False
            self._toast = None
            return
        if not toast["hovering"] and not toast["dismissing"]:
            toast["remaining"] -= 50
        if toast["remaining"] <= 0 and not toast["dismissing"]:
            toast["dismissing"] = True
            self._toast_fade_out(toast)
            return
        life = float(toast.get("life") or dv.TOAST_LIFE_MS)
        self._toast_set_drain(toast, toast["remaining"] / life)
        self._toast_animate_dust(toast)
        toast["popup"].after(50, lambda: self._toast_tick(toast))

    def _toast_fade_out(self, toast):
        """Toast out: fade + soft drop so exit mirrors the entrance."""
        steps = max(1, dv.TOAST_OUT_MS // 16)
        sw, sh, x, y_end = toast["geom"]
        drop = self._S(max(12, dv.TOAST_IN_RISE // 2))

        def step(i=0):
            if not toast["popup"].winfo_exists():
                toast["ticking"] = False
                return
            if not toast["dismissing"]:
                # A new event arrived and took the slot back; resume ticking.
                self._toast_tick(toast)
                return
            t = min(1.0, i / steps)
            eased = t * t  # ease-in — accelerates as it leaves
            self._toast_alpha(toast, 1.0 - eased)
            try:
                toast["popup"].geometry(
                    f"{sw}x{sh}+{x}+{int(y_end + drop * eased)}")
            except Exception:
                pass
            if t >= 1.0:
                toast["ticking"] = False
                timed_out = toast.get("on_timeout")
                toast["on_timeout"] = None
                if self._toast is toast:
                    self._toast = None
                try:
                    toast["popup"].destroy()
                except Exception:
                    pass
                if timed_out:
                    try:
                        timed_out()
                    except Exception as exc:
                        self._log(f"[Toast] Timeout handler failed: {exc}")
                return
            toast["popup"].after(16, lambda: step(i + 1))

        step()

    # ---- mini overlay (frame 2k) ----
    # "296x54, frameless, always-on-top, drag anywhere on the body. Snaps to the
    #  nearest screen corner within 32px; remembers position per monitor. Drops
    #  to 55% opacity after 3s without the pointer; full opacity on hover.
    #  Collapse restores the main window; it never appears while idle."
    #
    # Like the toast, this is its own Toplevel, so moving and fading it never
    # composites the dashboard.
    def _mini_state_allows(self):
        """The overlay exists to watch a running recording. "Never while idle"
        means exactly that: no recording, no overlay."""
        return self._hero_state in ("recording", "paused")

    def show_mini(self):
        if not self._mini_state_allows():
            self._log("[Manual] Mini overlay only appears while recording.")
            return
        if self._mini is None or not self._mini["popup"].winfo_exists():
            self._mini = self._mini_build()
        self._hide()                       # collapse the main window behind it
        self._mini_update()
        try:
            self._mini["popup"].deiconify()
        except Exception:
            pass

    def hide_mini(self, restore=False):
        mini = self._mini
        self._mini = None
        if mini and mini["popup"].winfo_exists():
            try:
                mini["popup"].destroy()
            except Exception:
                pass
        if restore:
            self.show()

    def _mini_build(self):
        w, h = dv.MINI_W, dv.MINI_H
        sw, sh = self._S(w), self._S(h)
        popup = ctk.CTkToplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)

        x, y = self._mini_saved_position(sw, sh)
        popup.geometry(f"{sw}x{sh}+{x}+{y}")
        apply_rounded_corners(popup)

        canvas = ScaledCanvas(
            tk.Canvas(popup, width=sw, height=sh, highlightthickness=0, bd=0),
            self.scale)
        canvas.pack(fill="both", expand=True)
        crop = (self.nebula.crop((0, 0, sw, sh))
                if self.nebula.size[0] >= sw and self.nebula.size[1] >= sh
                else self.nebula.resize((sw, sh)))
        photo = to_photo(crop)
        self._keep_image(photo)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        tile = make_glass_tile(sw, sh, CARD_TINT, tint_alpha=225,
                               radius=self._S(dv.RADIUS_TILE),
                               border_hex=CARD_BORDER, border_alpha=80)
        tile_photo = to_photo(tile)
        self._keep_image(tile_photo)
        canvas.create_image(0, 0, anchor="nw", image=tile_photo)

        dot = canvas.create_text(16, h / 2, text=ICON_GLYPHS["record"],
                                 fill=EMBER, font=(ICON_FONT, -9))
        timer = canvas.create_text(30, h / 2 - 8, anchor="w", text="00:00:00",
                                   fill=TEXT, font=dv.font(19, mono=True))
        game = canvas.create_text(30, h / 2 + 12, anchor="w", text="",
                                  fill=MUTED, font=dv.type_font("meta"))
        collapse = canvas.create_text(
            w - 18, h / 2, text=ICON_GLYPHS[dv.ICONS["collapse_mini"]],
            fill=FAINT, font=(ICON_FONT, -13))

        # --- transport buttons: a deliberate deviation from 2k --------------
        # The frame draws timer + game + collapse and nothing else. Anthony
        # asked for it "nicer and more fleshed out with buttons", which is a
        # change to the spec rather than an implementation of it, so it is
        # recorded as such: the shell keeps every rule 2k does state (296x54,
        # frameless, always-on-top, drag anywhere, corner snap, 55% fade after
        # 3s, never while idle) and gains the three actions that are otherwise
        # unreachable without restoring the whole window - which is the thing
        # the overlay exists to avoid.
        actions = []
        bx = w - 40
        for role, glyph_role, command in (
                ("mark", "mark_clip", self._mark_clip),
                ("stop", "square", self._toggle_record),
                ("pause", "pause", self._toggle_pause)):
            glyph = ICON_GLYPHS.get(glyph_role) or ICON_GLYPHS[dv.ICONS[glyph_role]]
            item = canvas.create_text(bx, h / 2, text=glyph, fill=MUTED,
                                      font=(ICON_FONT, -12))
            canvas.tag_bind(item, "<Button-1>", lambda _e, c=command: c())
            canvas.tag_bind(item, "<Enter>",
                            lambda _e, i=item: canvas._c.itemconfigure(i, fill=TEXT))
            canvas.tag_bind(item, "<Leave>",
                            lambda _e, i=item: canvas._c.itemconfigure(i, fill=MUTED))
            actions.append((role, item))
            bx -= 26

        mini = {"popup": popup, "canvas": canvas, "dot": dot, "timer": timer,
                "game": game, "faded": False, "fade_job": None, "drag": None,
                "actions": dict(actions), "collapse": collapse}

        canvas.tag_bind(collapse, "<Button-1>", lambda _e: self.hide_mini(restore=True))

        controls = {collapse, *mini["actions"].values()}

        def press(event):
            # Ignore a press on any control, so "drag anywhere on the body"
            # doesn't swallow the click that was meant for a button.
            if controls & set(canvas.find_withtag("current")):
                return
            mini["drag"] = (event.x_root - popup.winfo_x(), event.y_root - popup.winfo_y())

        def drag(event):
            if not mini["drag"]:
                return
            dx, dy = mini["drag"]
            popup.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

        def release(_event):
            if not mini["drag"]:
                return
            mini["drag"] = None
            self._mini_snap(mini)

        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", release)
        canvas.bind("<Enter>", lambda _e: self._mini_fade(mini, False))
        canvas.bind("<Leave>", lambda _e: self._mini_schedule_fade(mini))

        self._mini_schedule_fade(mini)
        return mini

    def _mini_monitor_key(self, x, y):
        """Which monitor a point is on - the key positions are remembered under.

        "Remembers position per monitor": storing one x/y would put the overlay
        off-screen the next time the laptop is docked to a different display.
        """
        try:
            from ctypes import windll, byref, sizeof, Structure, c_long, c_ulong, c_wchar

            class POINT(Structure):
                _fields_ = [("x", c_long), ("y", c_long)]

            class RECT(Structure):
                _fields_ = [("left", c_long), ("top", c_long),
                            ("right", c_long), ("bottom", c_long)]

            class MONITORINFOEXW(Structure):
                _fields_ = [("cbSize", c_ulong), ("rcMonitor", RECT), ("rcWork", RECT),
                            ("dwFlags", c_ulong), ("szDevice", c_wchar * 32)]

            monitor = windll.user32.MonitorFromPoint(POINT(int(x), int(y)), 2)
            info = MONITORINFOEXW()
            info.cbSize = sizeof(MONITORINFOEXW)
            if windll.user32.GetMonitorInfoW(monitor, byref(info)):
                r = info.rcWork
                return f"{r.left},{r.top},{r.right},{r.bottom}", (r.left, r.top, r.right, r.bottom)
        except Exception:
            pass
        return "primary", (0, 0, self.root.winfo_screenwidth(),
                           self.root.winfo_screenheight())

    def _mini_saved_position(self, sw, sh):
        left, top, right, bottom = self._monitor_workarea(primary=False)
        key, _rect = self._mini_monitor_key((left + right) / 2, (top + bottom) / 2)
        saved = (self.config.get("mini_overlay_positions") or {}).get(key)
        if saved and len(saved) == 2:
            x, y = int(saved[0]), int(saved[1])
            # Clamp back inside, in case the resolution changed since.
            x = max(left, min(x, right - sw))
            y = max(top, min(y, bottom - sh))
            return x, y
        margin = self._S(dv.TOAST_MARGIN)
        return right - sw - margin, bottom - sh - margin

    def _mini_snap(self, mini):
        """Snap to the nearest corner within 32px, then remember the position."""
        popup = mini["popup"]
        sw, sh = self._S(dv.MINI_W), self._S(dv.MINI_H)
        x, y = popup.winfo_x(), popup.winfo_y()
        key, (left, top, right, bottom) = self._mini_monitor_key(x + sw / 2, y + sh / 2)
        snap = self._S(dv.MINI_SNAP_PX)
        if abs(x - left) <= snap:
            x = left
        elif abs((x + sw) - right) <= snap:
            x = right - sw
        if abs(y - top) <= snap:
            y = top
        elif abs((y + sh) - bottom) <= snap:
            y = bottom - sh
        popup.geometry(f"+{x}+{y}")

        positions = dict(self.config.get("mini_overlay_positions") or {})
        positions[key] = [x, y]
        self.config["mini_overlay_positions"] = positions
        self._save_settings()

    def _mini_schedule_fade(self, mini):
        if mini["fade_job"]:
            try:
                mini["popup"].after_cancel(mini["fade_job"])
            except Exception:
                pass
        mini["fade_job"] = mini["popup"].after(
            dv.MINI_FADE_AFTER_MS, lambda: self._mini_fade(mini, True))

    def _mini_fade(self, mini, faded):
        if not mini["popup"].winfo_exists():
            return
        if faded and mini["fade_job"]:
            mini["fade_job"] = None
        if not faded:
            self._mini_schedule_fade(mini)
        if mini["faded"] == faded:
            return
        mini["faded"] = faded
        try:
            mini["popup"].attributes("-alpha", dv.MINI_FADED_OPACITY if faded else 1.0)
        except Exception:
            pass

    def _mini_update(self):
        """Mirror the hero's timer and game onto the overlay, once a second.

        Driven from _poll_obs_status rather than its own timer, so there is one
        clock in the app and the overlay can never disagree with the dashboard.
        """
        mini = self._mini
        if not mini or not mini["popup"].winfo_exists():
            return
        if not self._mini_state_allows():
            self.hide_mini()               # recording ended - "never while idle"
            return
        paused = self._hero_state == "paused"
        mini["canvas"].itemconfigure(mini["timer"],
                                     text=self._tray_elapsed or "00:00:00")
        mini["canvas"].itemconfigure(mini["game"], text=self._current_game or "Recording")
        mini["canvas"].itemconfigure(mini["dot"], fill=ACCENT if paused else EMBER)
        # The pause button says which way it goes, like the hero's does.
        pause_item = mini.get("actions", {}).get("pause")
        if pause_item is not None:
            role = "resume" if paused else "pause"
            mini["canvas"].itemconfigure(
                pause_item,
                text=ICON_GLYPHS.get(role) or ICON_GLYPHS[dv.ICONS[role]])

    def _on_state(self, **kwargs):
        def apply():
            if "game" in kwargs:
                game = kwargs["game"]
                self.bg.itemconfigure(
                    self.game_label_id,
                    text=game or "No game detected",
                    fill=TEXT if game else MUTED,  # empty state whispers, active state speaks
                )
                self._tray_game = game
                self._current_game = game
                # The replay buffer follows the detected game: it files into
                # that game's folder, and "replay_only_for_games" keeps it from
                # holding the desktop in RAM.
                self.replay.set_game(game)
                self._sync_replay_arming()
                # Refresh the hero so the scene caption picks up the new title,
                # and pull the status poll forward rather than re-applying the
                # state we already had. The monitor announces the game the
                # instant it starts recording, so re-applying meant the card
                # read "IDLE - WATCHING" *with a game name under it* until the
                # next heartbeat - which is exactly what it looked like:
                # broken.
                self._set_hero_state(self._hero_state)
                self._flash_status_card()
                if game:
                    self._poll_now()
                # The timer/storage/pulsing dot are driven by _poll_obs_status
                # from OBS's own GetRecordStatus, not from this event - that
                # way they reflect whether OBS is *actually* recording, not
                # just whether the monitor decided a game should be recorded.
            if "foreground" in kwargs:
                # 6.6: the watching hero names what it is looking at -
                # "Foreground: chrome.exe - classified as not a game."
                self._foreground_exe = kwargs["foreground"]
                if self._hero_state == "watching":
                    self._set_hero_state("watching")
            if "idle" in kwargs:
                # Idle no longer has its own pill - it reads as the hero card's
                # "PAUSED" state, which _poll_obs_status derives from OBS itself.
                self._tray_idle = kwargs["idle"]
            self._update_tray_tooltip()
        self.root.after(0, apply)

    # ---- tray (frame 2j) ----
    def tray_status(self):
        """Everything the tray menu and tooltip need, in one snapshot.

        Called from pystray's thread each time the menu is opened, so it only
        reads plain attributes - no Tk calls, nothing that could block.
        """
        if not self._obs_connected:
            state = "disconnected"
        elif self._is_recording and self._is_paused:
            state = "paused"
        elif self._is_recording:
            state = "recording"
        else:
            state = "idle"

        heading = {
            "recording": "Recording",
            "paused": ("Paused — stream ended"
                       if getattr(self, "_pause_reason", None) == "session"
                       else "Paused"),
            "idle": "Watching for a game",
            "disconnected": "OBS disconnected",
        }[state]

        game = self._current_game or self._tray_game
        elapsed = getattr(self, "_tray_elapsed", "")
        if state in ("recording", "paused") and game:
            detail = f"{game} · {elapsed}" if elapsed else game
            if state == "paused" and getattr(self, "_pause_reason", None) == "session":
                detail = f"{detail} · stream ended" if detail else "stream ended"
        elif state == "disconnected":
            detail = f"{self.config.get('obs_host', 'localhost')}:{self.config.get('obs_port', 4455)}"
        elif game:
            detail = game
        else:
            detail = "No game in focus"

        # Quiet offload wait signal when the tray is otherwise idle-ish and
        # clips are stuck behind an unreachable NAS.
        pending = getattr(self, "_offload_pending", 0)
        reach = getattr(self, "_offload_reachability", None)
        if pending and reach and str(reach).startswith("nas_down"):
            wait = f"{pending} clip{'s' if pending != 1 else ''} waiting on NAS"
            if state == "idle" and detail == "No game in focus":
                detail = wait
            elif state == "idle":
                detail = f"{detail} · {wait}"

        return {
            "state": state,
            "heading": heading,
            "detail": detail,
            "monitoring": self._monitoring_on,
        }

    def _update_tray_tooltip(self):
        """Tooltip and icon both follow the state - "tooltip = game + elapsed"."""
        if not self.tray_icon:
            return
        status = self.tray_status()
        # The tray icon's three states collapse paused into recording: the
        # spec names idle / recording / disconnected, and a paused recording is
        # still a live one as far as the tray is concerned.
        icon_state = "recording" if status["state"] in ("recording", "paused") else (
            "disconnected" if status["state"] == "disconnected" else "idle")
        try:
            if getattr(self, "_tray_icon_state", None) != icon_state:
                # tray_app owns the swap so the recording arc has one
                # implementation for both renderers - see set_tray_state.
                from .tray_app import set_tray_state
                set_tray_state(self.tray_icon, icon_state)
                self._tray_icon_state = icon_state
        except Exception:
            pass
        text = f"Nebula — {status['heading']}"
        if status["detail"] and status["state"] != "disconnected":
            text += f"\n{status['detail']}"
        try:
            self.tray_icon.title = text[:127]  # Windows tray tooltip length limit
        except Exception:
            pass

    def _on_timeout_change(self, value):
        """Kept for the hotkey/tray paths; the dashboard slider is gone.

        6.3: "The current build put a live slider inside the Idle timeout tile.
        A stat tile shows one number and one caption. It never contains a
        control - those live in Settings." idle_timeout_seconds is already a
        declared field in settings_spec, so nothing was lost by removing it
        from the dashboard.
        """
        self.config["idle_timeout_seconds"] = int(value)
        if getattr(self, "_stat_idle_sub", None) is not None:
            self.bg.itemconfigure(self._stat_idle_sub,
                                  text=f"after {int(value)}s idle")
        from .config import save_config
        save_config(self.config)

    # ---- actions ----
    def _start(self):
        # OBS takes several seconds to actually boot once launched, so an
        # immediate connect attempt right after ensure_obs_running() would
        # reliably fail on the first click - reuse autostart()'s retry loop
        # (launch-if-needed, connect, retry every 10s) instead of a one-shot
        # attempt that pops a discouraging error dialog while OBS is still
        # mid-launch.
        self._set_obs_status("connecting…", AMBER)
        self.autostart()

    def _on_connected(self):
        self._set_obs_status("connected", GREEN)
        self._set_monitoring(True)
        self.monitor.start()

    def autostart(self):
        """Called once at launch, and again on retry, so the app starts
        recording-ready on its own (e.g. when run from Windows startup)
        without requiring a manual click - launches OBS itself if it isn't
        already running, and retries quietly rather than popping a blocking
        error dialog. Once monitor.start() runs, the monitor's own loop takes
        over reconnecting if OBS later crashes/closes."""
        if self.obs.connected and self.monitor._running:
            return
        if self._connecting:
            return
        self._connecting = True
        self._abort_connect = False
        # Drop stale version/handshake so the titlebar doesn't keep advertising
        # a live OBS while the socket is still coming up.
        self._clear_obs_meta()
        self._set_obs_status("connecting…", AMBER)

        # Runs off the Tk thread. ensure_obs_running() may launch OBS, and
        # obs.connect() blocks for up to its 5s socket timeout - which is the
        # normal case at startup, since we've usually just launched OBS and it
        # is still booting. Done inline (as it used to be) that froze the whole
        # window for seconds on launch, and again on every 10s retry.
        def worker():
            meta = {}
            try:
                ensure_obs_running(self.config.get("obs_path"), log=self._log)
                self.obs.connect()
                # Fetch once on the worker — never on the Tk thread. These are
                # the real sources for the titlebar version, the res/fps chip
                # and the Settings handshake line (handoff §2.2).
                meta = self._fetch_obs_meta()
            except Exception as exc:
                # Deliberately broad: anything escaping here would strand
                # _connecting=True and permanently block every future
                # reconnect attempt. websocket's own errors aren't all OSError.
                #
                # `exc` is unbound the instant this block exits (Python 3
                # deletes the except target), and this callback runs later on
                # the Tk thread - so bind it to a normal local first.
                error = exc
                self._ui(lambda: self._connect_failed(error))
                return
            finally:
                # Cleared here, in the worker, rather than only in the UI
                # callbacks: _ui() drops its callback if Tk won't accept a
                # cross-thread after() (window tearing down, or no mainloop
                # running yet). A _connecting left stuck at True would block
                # every future reconnect for the life of the process.
                self._connecting = False
            self._ui(lambda m=meta: self._connect_succeeded(m))

        threading.Thread(target=worker, daemon=True).start()

    def _fetch_obs_meta(self):
        """Read version / video / scene from OBS. Call from a worker only."""
        meta = {
            "handshake_ms": self.obs.last_handshake_ms,
            "version": "",
            "video_label": "",
            "scene": "",
        }
        try:
            meta["version"] = short_obs_version(self.obs.get_version())
        except OBSError:
            pass
        try:
            meta["video_label"] = format_video_label(self.obs.get_video_settings())
        except OBSError:
            pass
        try:
            meta["scene"] = self.obs.get_current_program_scene() or ""
        except OBSError:
            pass
        return meta

    def _apply_obs_meta(self, meta):
        """Paint cached OBS metadata onto the titlebar / hero / Settings."""
        if not meta:
            return
        self._handshake_ms = meta.get("handshake_ms")
        self._obs_version = meta.get("version") or ""
        self._video_label = meta.get("video_label") or ""
        self._scene_name = meta.get("scene") or ""
        # Re-apply the current hero state so the preview chip / caption pick up
        # the new scene and video label without inventing a fifth state.
        if self._hero_state:
            self._set_hero_state(self._hero_state)
        self._refresh_settings_obs_footer()

    def _ui(self, fn):
        """Marshal `fn` onto the Tk thread, tolerating a torn-down window."""
        try:
            self.root.after(0, fn)
        except RuntimeError:
            pass

    def _connect_failed(self, error):
        if self._abort_connect:
            return
        # Distinguish the two very different failures that both surface as a
        # refused socket: OBS isn't running at all, vs OBS IS running but its
        # WebSocket server isn't listening (server disabled in OBS, or the
        # setting was changed without restarting). The second one is a
        # dead-end retry loop unless the user does something in OBS, so say so
        # clearly rather than looping "not available" forever.
        try:
            delay_s = float(self.config.get("reconnect_interval_seconds") or 10)
        except (TypeError, ValueError):
            delay_s = 10.0
        delay_s = max(1.0, min(delay_s, 30.0))
        delay_ms = int(delay_s * 1000)
        if is_obs_running():
            self._log("[Monitor] OBS is running but its WebSocket server isn't "
                      "accepting connections. In OBS: Tools -> WebSocket Server "
                      "Settings -> tick 'Enable WebSocket server' (or restart OBS). "
                      "Retrying in %.0fs..." % delay_s)
            self._set_obs_status("enable WS in OBS", AMBER)
        else:
            self._log(f"[Monitor] OBS not available yet ({error}); retrying in {delay_s:.0f}s...")
            self._set_obs_status("disconnected", RED)
        self.root.after(delay_ms, self.autostart)

    def _connect_succeeded(self, meta=None):
        if self._abort_connect:
            # Monitoring was stopped while this attempt was still in flight -
            # don't quietly restart it behind the user's back.
            self.obs.disconnect()
            self._clear_obs_meta()
            self._set_obs_status("disconnected", RED)
            return
        self._apply_obs_meta(meta or {})
        self._on_connected()
        self._log("[Monitor] Auto-started.")

    def _clear_obs_meta(self):
        self._obs_version = ""
        self._handshake_ms = None
        self._video_label = ""
        self._scene_name = ""
        if getattr(self, "_preview_video_id", None):
            self.bg.itemconfigure(self._preview_video_id, text="", state="hidden")
        if getattr(self, "_preview_scene_chip", None):
            self.bg.itemconfigure(self._preview_scene_chip, text="OBS scene")
        self._refresh_settings_obs_footer()

    def _on_connection_change(self, connected):
        # _obs_connected was declared in __init__ and then never assigned - it
        # sat False for the whole run. Nothing read it until the v3 tray needed
        # a "disconnected" state, at which point a permanently-false flag would
        # have pinned the tray icon to the slashed variant forever. Keep it in
        # step here and in _poll_obs_status, which is the other place the truth
        # is observed.
        self._obs_connected = bool(connected)
        if connected:
            # Monitor reconnected off-thread — refresh meta the same way as
            # the initial connect, never on the Tk thread.
            def refresh():
                try:
                    meta = self._fetch_obs_meta()
                except Exception:
                    meta = {}

                def apply():
                    self._apply_obs_meta(meta)
                    self._set_obs_status("connected", GREEN)
                    self._update_tray_tooltip()

                self._ui(apply)

            threading.Thread(target=refresh, daemon=True).start()
        else:
            self._clear_obs_meta()
            self.root.after(0, lambda: self._set_obs_status("reconnecting…", RED))
            self.root.after(0, self._update_tray_tooltip)

    def _stop(self):
        self._abort_connect = True  # cancel any connect attempt still in flight
        self.monitor.stop()
        self.obs.disconnect()
        self._clear_obs_meta()
        self._set_obs_status("disconnected", RED)
        self._set_monitoring(False)
        self._set_hero_state("disconnected")

    def _register_hotkey(self):
        """(Re)bind all three global keys, taking the old hooks down first.

        Every handle is kept. Dropping them meant a rebind *added* a hook
        rather than replacing one: editing the toggle key four times left
        fifteen live hooks, the stale suppress=True ones still swallowing the
        old key system-wide - which is precisely the failure hotkey.unregister
        exists to prevent, and it was never being called.
        """
        for handle in getattr(self, "_hotkey_handles", ()):
            hotkey.unregister(handle, on_log=self._log)
        self._hotkey_handles = []

        def keep(handle):
            if handle:
                self._hotkey_handles.append(handle)

        def on_press():
            # keyboard's callback fires on its own thread - bounce onto the
            # Tk thread before touching any widgets/monitor state.
            self.root.after(0, self._toggle_monitoring)

        keep(hotkey.register(
            self.config.get("toggle_hotkey"), on_press, suppress=True,
            on_log=self._log,
            scancode=self.config.get("toggle_hotkey_scancode")))

        # 7a's save key. Bound by scan code for the same reason as the toggle:
        # a character can resolve to several scan codes, and pinning it is what
        # stops the hook swallowing the wrong key system-wide.
        if self.config.get("replay_enabled", True):
            keep(hotkey.register(
                self.config.get("replay_hotkey", "f9"),
                lambda: self.root.after(0, self._save_replay),
                suppress=False, on_log=self._log,
                scancode=self.config.get("replay_hotkey_scancode")))

        # 7e: "Global hotkey: palette_hotkey, default ctrl+k" - and it has to
        # be global, because the palette's whole point is opening over a game.
        palette_key = self.config.get("palette_hotkey", "ctrl+k")
        if palette_key:
            keep(hotkey.register(
                palette_key, lambda: self.root.after(0, self.show_palette),
                suppress=False, on_log=self._log))

    def _mark_clip(self):
        """Drop a mark on the running recording.

        Two things happen, and only one of them needs OBS. The mark is written
        to sessions.jsonl unconditionally - that is what 7b's ember ticks
        render and what the ribbon's "N marks" counts - and OBS is *also* asked
        for a real chapter, which only newer builds with a supported container
        accept. A refusal is logged, not surfaced: the mark still exists.
        """
        if not self._is_recording:
            self._toast_replace("error", "Nothing to mark — no recording running")
            return
        session_log.append("mark", game=self._current_game)
        self._log(f"[Manual] Marked {self._current_game or 'the recording'}.")
        self._refresh_ribbon()

        def worker():
            try:
                self.obs.call("CreateRecordChapter", {"chapterName": time.strftime("%H:%M:%S")})
            except Exception as exc:
                # Bind before the closure - `exc` dies with the block.
                reason = str(exc)
                self.root.after(0, lambda: self._log(
                    f"[OBS] Chapter not created ({reason}). The mark is still recorded."))

        threading.Thread(target=worker, daemon=True).start()

    def _save_replay(self):
        """Save the last N seconds. Wired to the hotkey, tray and overlay."""
        if not self.replay.save():
            self._toast_replace("error", "Nothing to save — the buffer isn't armed")

    def _on_replay_saved(self, path, game):
        """Called from OBS's receive thread once the file has landed."""
        self._ui(lambda: self._replay_saved_ui(path, game))

    def _replay_saved_ui(self, path, game):
        # "Confirmation toast - 360 wide: Last 30s saved / <game>/Replays/<file>"
        shown = os.path.join(game, self.replay.subfolder, os.path.basename(path))
        self._toast_replace("start", f"Last {self.replay.seconds}s saved", None)
        self._log(f"[Replay] {shown}")
        self._refresh_replay_module()

    def _on_replay_state(self, armed):
        self._ui(self._refresh_replay_module)

    def _toggle_monitoring(self):
        """Flip monitoring on/off - the fan-key action. Turning it OFF stops
        the monitor (and any in-progress recording) so it won't auto-record
        games you don't want; turning it back ON reconnects and resumes
        auto-detection. Shows a notification either way so there's clear
        feedback without needing the window open."""
        if self.monitor._running:
            self._stop()
            self._show_notification("pause", "Monitoring disabled")
            self._log("[Hotkey] Monitoring disabled.")
        else:
            self.autostart()
            self._show_notification("start", "Monitoring enabled")
            self._log("[Hotkey] Monitoring enabled.")

    def _animate_scanning(self, n=0):
        if not self._scanning:
            return
        self.rescan_btn.configure(text="Scanning" + "." * (n % 4))
        self.root.after(350, lambda: self._animate_scanning(n + 1))

    def _rescan_steam(self):
        """Runs off the Tkinter thread - this walks every installed Steam
        game's folder plus a network call per uncached app, which used to
        freeze the whole GUI for the entire scan when run inline."""
        self.rescan_btn.configure(state="disabled")
        self._scanning = True
        self._animate_scanning()

        def worker():
            try:
                registered = self.classifier.register_all_steam_games()
                # "0 game(s) registered" is ambiguous: it reads like a failure
                # when the usual cause is simply having no Steam games
                # installed. Say which it is - a machine whose games all come
                # from HoYoPlay / Roblox / CurseForge has an empty Steam
                # library, and the classifier is meant to learn those by
                # watching instead.
                from .steam_scanner import scan_app_manifests
                if registered:
                    message = f"[Steam] Rescan complete - {len(registered)} game(s) registered."
                elif not scan_app_manifests():
                    message = ("[Steam] No Steam games installed - nothing to import. "
                               "Non-Steam games are learned as you play them.")
                else:
                    message = ("[Steam] Rescan complete - no new games; "
                               "everything installed is already classified.")
                self.root.after(0, lambda: self._log(message))
            except Exception as exc:
                # Same late-binding trap as the connect worker: `exc` is gone by
                # the time Tk runs this callback, so capture it in a local.
                error = exc
                self.root.after(0, lambda: self._log(f"[Steam] Rescan failed: {error}"))
            finally:
                self._scanning = False
                self.root.after(0, lambda: self.rescan_btn.configure(state="normal", text=self._rescan_label))

        threading.Thread(target=worker, daemon=True).start()

    def _open_game_data(self):
        # Read classifier_module.DATA_FILE live (not imported as a bare name)
        # - main.py's _apply_sync_folder() repoints this to the OneDrive path
        # *after* gui.py's imports already ran, so a plain `from .classifier
        # import DATA_FILE` would have permanently captured the stale
        # pre-sync path and this button would never find the real file.
        data_file = classifier_module.DATA_FILE
        if os.path.exists(data_file):
            os.startfile(data_file)
        else:
            tkinter.messagebox.showwarning("Missing", f"{data_file} not found yet.")

    def _dialog_bg(self, dialog, width, height):
        """Nebula + glass backdrop for a dialog, matching the main window.
        width/height are base design units; the backdrop is rendered at the
        scaled pixel size and drawing on the returned canvas uses base units."""
        sw, sh = self._S(width), self._S(height)
        canvas = ScaledCanvas(
            tk.Canvas(dialog, width=sw, height=sh, highlightthickness=0, bd=0),
            self.scale,
        )
        canvas.place(x=0, y=0)
        crop = self.nebula.resize((sw, sh))
        photo = to_photo(crop)
        self._keep_image(photo)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        tile = make_glass_tile(sw, sh, CARD_TINT, tint_alpha=225, radius=self._S(18), border_hex=CARD_BORDER, border_alpha=80)
        tile_photo = to_photo(tile)
        self._keep_image(tile_photo)
        canvas.create_image(0, 0, anchor="nw", image=tile_photo)
        return canvas

    def _ask_yes_no_cancel(self, title, exe_count):
        """A standalone, always-on-top Toplevel instead of tkinter.messagebox.
        messagebox's dialog is parented to the (usually withdrawn/hidden)
        main window and on Windows can end up never actually shown to the
        user - it just silently sits there, un-answerable, forever. This
        forces itself to the front regardless of the main window's state.
        Text is drawn straight onto the canvas (not embedded CTkLabels in a
        "transparent" frame) - that gave a mismatched black box in an
        earlier version, since transparent CTk widgets don't composite with
        arbitrary canvas art beneath them."""
        result = {"value": None}
        width, height = 440, 230
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Unrecognized app")
        dialog.overrideredirect(True)
        dialog.geometry(f"{self._S(width)}x{self._S(height)}")
        dialog.attributes("-topmost", True)
        apply_rounded_corners(dialog)
        canvas = self._dialog_bg(dialog, width, height)

        canvas.create_text(
            width / 2, 36, anchor="center", text=title, fill=TEXT,
            font=dv.type_font("pane_title"), width=380, justify="center",
        )
        detail = (
            f"This app ({exe_count} executables) isn't in the game list yet.\n"
            "Is it a game you want auto-recorded to its own folder?"
            if exe_count > 1 else
            "This app is running and isn't in the game list yet.\n"
            "Is it a game you want auto-recorded to its own folder?"
        )
        canvas.create_text(
            width / 2, 94, anchor="center", text=detail, fill=MUTED,
            font=dv.type_font("row_small"), width=380, justify="center",
        )

        def choose(value):
            result["value"] = value
            dialog.destroy()

        def dialog_bg_at(dx, dy):
            # The dialog backdrop is the whole nebula resized down, seen
            # through its glass tint - map the dialog point back to nebula
            # coordinates for the corner-blend sample.
            return self._bg_at(dx / width * WIDTH, dy / height * HEIGHT, CARD_TINT, 225)

        btn_y = height - 58
        yes_btn = ctk.CTkButton(
            dialog, text="Yes, it's a game", command=lambda: choose(True),
            fg_color=GREEN_TINT, hover_color=GREEN_TINT_HOVER, text_color=GREEN,
            bg_color=dialog_bg_at(113, btn_y + 17),
            border_width=1, border_color=EDGE, corner_radius=10,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        canvas.create_window(46, btn_y, anchor="nw", window=yes_btn, width=134, height=34)
        no_btn = ctk.CTkButton(
            dialog, text="No", command=lambda: choose(False),
            fg_color=RED_TINT, hover_color=RED_TINT_HOVER, text_color=RED,
            bg_color=dialog_bg_at(230, btn_y + 17),
            border_width=1, border_color=EDGE, corner_radius=10,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        canvas.create_window(190, btn_y, anchor="nw", window=no_btn, width=80, height=34)
        later_btn = ctk.CTkButton(
            dialog, text="Ask me later", command=lambda: choose(None),
            fg_color=SURFACE, hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=dialog_bg_at(337, btn_y + 17),
            border_width=1, border_color=EDGE, corner_radius=10,
            font=ctk.CTkFont(size=12),
        )
        canvas.create_window(280, btn_y, anchor="nw", window=later_btn, width=114, height=34)

        dialog.lift()
        dialog.focus_force()
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result["value"]

    def _ask_display_name(self, basename, suggestion=None):
        # The picker passes the app's own window title, which names the game
        # far better than the exe stem does ("Zenless Zone Zero" vs "ZZZ").
        suggestion = suggestion or suggest_display_name(basename)
        result = {"value": suggestion}
        width, height = 400, 184
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Folder name")
        dialog.overrideredirect(True)
        dialog.geometry(f"{self._S(width)}x{self._S(height)}")
        dialog.attributes("-topmost", True)
        apply_rounded_corners(dialog)
        canvas = self._dialog_bg(dialog, width, height)

        canvas.create_text(
            24, 34, anchor="w", text="Folder / display name for this game:",
            fill=TEXT, font=dv.type_font("body"),
        )
        def dialog_bg_at(dx, dy):
            return self._bg_at(dx / width * WIDTH, dy / height * HEIGHT, CARD_TINT, 225)

        entry = ctk.CTkEntry(
            dialog, width=320, height=34, fg_color=LOG_BG, border_color=EDGE,
            text_color=TEXT, corner_radius=10, bg_color=dialog_bg_at(200, 77),
        )
        entry.insert(0, suggestion)
        canvas.create_window(40, 60, anchor="nw", window=entry, width=320, height=34)

        def confirm(_=None):
            result["value"] = entry.get().strip() or suggestion
            dialog.destroy()

        ok_btn = ctk.CTkButton(
            dialog, text="OK", command=confirm, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#171233", corner_radius=10, font=ctk.CTkFont(size=12, weight="bold"),
            bg_color=dialog_bg_at(200, 137),
        )
        canvas.create_window(width / 2 - 50, 120, anchor="nw", window=ok_btn, width=100, height=34)
        entry.bind("<Return>", confirm)

        dialog.lift()
        dialog.focus_force()
        entry.focus_set()
        entry.select_range(0, "end")
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result["value"]

    def _animate_taskbar_icon(self):
        """Slowly rotates the taskbar/Alt-Tab icon while the window is mapped.

        Deliberately slow. `iconphoto` is a window-level change, and on this
        window those are expensive (see the note above _glass) - at the old 80ms
        it was 12 window updates a second for an icon most people never look at.
        A withdrawn window has no taskbar button at all, so it idles then."""
        if not self._visible:
            self.root.after(IDLE_TICK_MS, self._animate_taskbar_icon)
            return
        try:
            self.root.iconphoto(False, self._taskbar_icon_frames[self._taskbar_icon_index % len(self._taskbar_icon_frames)])
        except Exception:
            pass
        self._taskbar_icon_index += 1
        self.root.after(ICON_TICK_MS, self._animate_taskbar_icon)

    def _poll_manual_review(self):
        for key, basenames, suggested_name in self.classifier.pop_pending_reviews():
            answer = self._ask_yes_no_cancel(suggested_name or key, len(basenames))
            if answer is None:
                self.classifier.finish_review(key)
                continue  # ask again another time
            if answer:
                # Steam-sourced groups already have a real name (e.g.
                # "Wallpaper Engine") - only prompt for a name when we
                # genuinely don't have one (a single unrecognized exe).
                display_name = suggested_name or self._ask_display_name(key)
                self.classifier.resolve_review(basenames, True, display_name)
            else:
                self.classifier.resolve_review(basenames, False)
            self.classifier.finish_review(key)
        self.root.after(2000, self._poll_manual_review)

    # ---- window visibility (tray integration) ----
    def _fade(self, start, end, duration_ms=160, steps=10, on_done=None):
        step_delay = max(duration_ms // steps, 1)

        def step(i=0):
            try:
                self.root.attributes("-alpha", start + (end - start) * (i / steps))
            except Exception:
                pass
            if i < steps:
                self.root.after(step_delay, lambda: step(i + 1))
            elif on_done:
                on_done()

        step()

    def _hide(self):
        def after_fade():
            self.root.withdraw()
            self.on_close_to_tray()
        self._fade(1.0, 0.0, on_done=after_fade)

    def show(self):
        def _do_show():
            self.root.attributes("-alpha", 0.0)
            self.root.deiconify()
            self.root.lift()
            # Briefly force topmost then release it - deiconify()+lift() alone
            # can leave an overrideredirect window re-mapped but still behind
            # whatever else has focus (a game, OBS, a browser), which looked
            # like "nothing happened" when clicking Show window from the tray.
            self.root.attributes("-topmost", True)
            self.root.after(10, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
            self._fade(0.0, 1.0)
        self.root.after(0, _do_show)

    def run(self):
        self.root.mainloop()

    def quit(self):
        self.monitor.stop()
        self.obs.disconnect()
        self.root.after(0, self.root.destroy)
