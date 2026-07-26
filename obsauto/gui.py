import ctypes
import math
import os
import random
import re
import shutil
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
from . import settings_spec
from .obs_client import OBSClient, OBSError
from .monitor import Monitor, ensure_obs_running, is_obs_running
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
    "record": 0xE7C8,               # filled circle
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
    "hourglass-medium": 0xE823,     # Recorded tile (History / hourglass stand-in)
    "funnel-simple": 0xE71C,        # Activity tag filter
    "copy-simple": 0xE8C8,          # Copy log
    "microphone": 0xE720,           # Mic label on the hero info row
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

# The rail's five destinations (frame 2a). Activity is a dashboard block only —
# no standalone Activity pane (mockup has none).
RAIL_VIEWS = list(dv.PANES)

VIEW_TITLES = {
    "dashboard": "Dashboard",
    "clips": "Clips",
    "games": "Games",
    "macropad": "Macropad",
    "settings": "Settings",
}
VIDEO_EXTS = (".mkv", ".mp4", ".mov", ".flv", ".ts", ".m4v")
LOG_HISTORY = 500  # lines kept for the dashboard Activity block

# Rearrangeable dashboard blocks. Heights are fixed so reordering is a pure
# translation of each block - no rebuilding, nothing to resize.
DEFAULT_BLOCKS = ("hero", "stats", "activity")
BLOCK_LABELS = {"hero": "Now recording", "stats": "Stats", "activity": "Activity"}
BLOCK_GAP = 18
GRID_COL_GAP = 18
# Frame 2a: 404-wide 16:9 preview + pads/bezel → ~330px hero footprint.
HERO_H = 330
# Fixed footprint heights per (block, span). span 2 = full width; span 1 = half
# width (stats reflows to 2x2, so it's taller). Heights are fixed so laying the
# grid out is pure arithmetic - no measuring, nothing to resize. Activity's 246
# includes its 22px header.
BLOCK_HEIGHTS = {
    "hero": {2: HERO_H, 1: HERO_H},   # hero is full-width only; 1 is never used
    "stats": {2: 92, 1: 198},
    "activity": {2: 246, 1: 246},
}
# The dashboard layout is an ordered list of {"name", "span"}. Consecutive
# half-span blocks pair left-to-right into one row; anything else takes a full
# row. Persisted to config as "dashboard_grid".
DEFAULT_GRID = [{"name": b, "span": 2} for b in DEFAULT_BLOCKS]


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
            offloader=offloader,
        )
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
        self._images = []  # keeps PhotoImage refs alive - Tk GCs them otherwise
        self._glass_cache = {}  # (size, tint, alpha, radius, border...) -> PhotoImage
        self._dragging = False
        self._scanning = False
        self._connecting = False      # a connect attempt is in flight on a worker
        self._abort_connect = False   # set when monitoring is stopped mid-connect
        self._monitoring_on = False   # reflected in the sidebar toggle
        self._obs_connected = False   # reflected in the sidebar OBS card
        self._hero_state = "disconnected"  # disconnected | watching | recording | paused
        self._bitrate_sample = None   # (duration_ms, bytes) from the previous poll
        self._current_game = None
        self._current_exe = None      # basename for the hero source line (frame 2a)
        self._obs_version = None      # e.g. "30.2" from GetVersion
        self._video_label = None      # e.g. "2560×1440 · 60 fps" from GetVideoSettings
        self._scene_name = None       # current program scene
        self._handshake_ms = None     # last successful connect duration (Settings 2c)
        self._eq_bars = []            # legacy; preview no longer animates bars
        self._preview_items = []      # canvas ids hidden while idle / disconnected
        self._log_lines = []          # history for the dashboard Activity block
        self._log_pending = []        # buffered lines awaiting a coalesced flush
        self._log_flush_scheduled = False
        self._log_lock = threading.Lock()
        self._log_filter_tag = None   # None = All tags
        self.console = None           # set by _build_activity
        self._clips_total = None      # rail badge; filled after a clips/disk scan

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
        self.nebula = generate_backdrop_v3(self._S(WIDTH), self._S(HEIGHT))
        self.bg = ScaledCanvas(
            tk.Canvas(self.root, width=self._S(WIDTH), height=self._S(HEIGHT),
                      highlightthickness=0, bd=0),
            self.scale,
        )
        self.bg.pack(fill="both", expand=True)

        bg_photo = to_photo(self.nebula)
        self._images.append(bg_photo)
        self._backdrop_id = self.bg.create_image(0, 0, anchor="nw", image=bg_photo)

        # Truth source for widget corner-blending. An embedded CTk widget paints
        # the area its rounded corners cut away with a single flat bg_color, so
        # that colour has to match the real pixels behind it or you get a square
        # fringe inside the rounded panel. Approximating it (nebula tint + alpha)
        # broke once the glass tiles gained their sheen gradient. Instead keep a
        # real composite - the nebula exactly as it sits behind the window, with
        # each glass panel pasted in as it's drawn - and sample that.
        self._composite = self.nebula.convert("RGB")

        self.bg.bind("<ButtonPress-1>", self._start_move)
        self.bg.bind("<B1-Motion>", self._on_move)

        self._build_titlebar()
        self._build_sidebar()
        self._build_topbar()
        self._build_views()

        self._poll_manual_review()
        self._poll_obs_status()
        self._poll_disk_stats()
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
    def _glass(self, x, y, w, h, tint=CARD_TINT, radius=18, tint_alpha=150, border_hex=None, border_alpha=55):
        tile = make_glass_tile(
            self._S(w), self._S(h), tint, tint_alpha=tint_alpha, radius=self._S(radius),
            border_hex=border_hex or CARD_BORDER, border_alpha=border_alpha,
        )
        # Keep the sample source true: any widget placed on this panel afterwards
        # reads its bg_color from the composite, sheen and all.
        self._composite.paste(tile, (self._S(x), self._S(y)), tile)
        photo = to_photo(tile)
        self._images.append(photo)
        return self.bg.create_image(x, y, anchor="nw", image=photo)

    def _regen_glass(self, item_id, x, y, w, h, tint=CARD_TINT, radius=18, tint_alpha=150, border_hex=None, border_alpha=55):
        """Swap an existing glass panel's image (e.g. for a brief highlight
        flash, or a hero state change) without creating a duplicate canvas item.

        Results are cached by their visual parameters. Regenerating the hero
        panel costs ~35ms, and it's re-rendered on every state change plus five
        times per flash - so a game switch used to stall the UI for ~200ms and
        leak a PhotoImage per frame. The set of distinct tiles is tiny and
        fixed, so caching makes every repeat instant and bounds the memory."""
        key = (self._S(w), self._S(h), tint, tint_alpha, self._S(radius),
               border_hex or CARD_BORDER, border_alpha)
        photo = self._glass_cache.get(key)
        if photo is None:
            tile = make_glass_tile(
                key[0], key[1], tint, tint_alpha=tint_alpha, radius=key[4],
                border_hex=key[5], border_alpha=border_alpha,
            )
            photo = to_photo(tile)
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
        self._images.append(photo)
        self.bg.create_image(cx - size / 2, cy - size / 2, anchor="nw", image=photo)

    # ---- left nav rail (frame 2a) ----
    # The v3 rail hangs *below* the full-width titlebar rather than running the
    # whole window height, and its foot carries the storage card - the OBS
    # connection readout and the monitoring toggle both moved up into the
    # titlebar. Rail metrics: w 232, pad 16/12, item h 38, gap 3.
    def _build_sidebar(self):
        # Faint divider between rail and content. A hairline, never a solid
        # grey, and it fades at both ends like every other rule in the system.
        self._fading_rule(SIDEBAR_W, CONTENT_Y0, HEIGHT - CONTENT_Y0, vertical=True)

        # Section eyebrow.
        self.bg.create_text(dv.RAIL_PAD_X, CONTENT_Y0 + 22, anchor="w",
                            text=self._track("Session"), fill=FAINT,
                            font=dv.type_font("eyebrow"))

        # Frame 2a: Clips badge = total clips (filled once a scan lands);
        # Games badge = pending reviews, not the classified total.
        nav = [
            ("dashboard", "Dashboard", None),
            ("clips", "Clips", self._clips_badge()),
            ("games", "Games", self._games_pending_badge()),
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
        self._images.append(photo)
        return self.bg.create_image(a, b, anchor="nw", image=photo)

    def _game_count(self):
        """How many distinct games the classifier knows about.

        Kept for Settings / Games pane copy; the rail badge uses
        ``_games_pending_badge`` (frame 2a's pending pill), not this total.
        """
        try:
            games = self.classifier._data.get("games", {})
            names = {
                (v.get("display_name") or k) if isinstance(v, dict) else k
                for k, v in games.items()
            }
            return str(len(names)) if names else None
        except Exception:
            return None

    def _games_pending_badge(self):
        """Frame 2a Games rail pill — count awaiting classification, or None."""
        try:
            pending = self.classifier.peek_pending_reviews()
            return str(len(pending)) if pending else None
        except Exception:
            return None

    def _clips_badge(self):
        """Frame 2a Clips rail count — real total once a scan has landed."""
        total = self._clips_total
        return str(total) if total is not None else None

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
        cx, cw = dv.RAIL_PAD_Y, SIDEBAR_W - dv.RAIL_PAD_Y * 2
        oy = HEIGHT - 92
        self._glass(cx, oy, cw, 74, tint=CARD_TINT, radius=dv.RADIUS_TILE,
                    tint_alpha=110, border_hex=CARD_BORDER, border_alpha=26)

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
        cy = TITLEBAR_HEIGHT / 2
        pad_l, pad_r = dv.TITLEBAR_PAD_LEFT, dv.TITLEBAR_PAD_RIGHT

        self._draw_logo(pad_l + 10, cy, 21)
        self.bg.create_text(pad_l + 27, cy, anchor="w", text="Nebula",
                            fill=TEXT, font=dv.font(14, 500))

        # Version badge - reads obsauto.__version__, not a drawn-in string.
        from . import __version__
        bx = pad_l + 27 + 48
        self._glass(bx, cy - 8, 34, 16, tint=ACCENT, radius=5, tint_alpha=34,
                    border_hex=ACCENT, border_alpha=0)
        self.bg.create_text(bx + 17, cy, text=__version__, fill=ACCENT_LIGHT,
                            font=dv.font(9.5, mono=True))

        # Monitoring toggle - same action as the hotkey.
        mx = bx + 50
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
            self.bg.tag_bind(item, "<Leave>", lambda _e: self.bg.configure(cursor=""))

        # ---- right side: OBS connection, then the window controls ----
        self._make_circle_button(WIDTH - pad_r - 15, cy, 13, SURFACE, EMBER,
                                 ICON_GLYPHS["x"], self._hide, font=(ICON_FONT, -9))
        self._make_circle_button(WIDTH - pad_r - 47, cy, 13, SURFACE, SURFACE_HOVER,
                                 ICON_GLYPHS["minus"], self._hide, font=(ICON_FONT, -9))
        # Collapse to the mini overlay (2k). It refuses while idle, which is why
        # this is a normal button rather than one that gets hidden - the refusal
        # says why, where a vanishing control would just be confusing.
        self._make_circle_button(
            WIDTH - pad_r - 79, cy, 13, SURFACE, SURFACE_HOVER,
            ICON_GLYPHS[dv.ICONS["collapse_mini"]], self.show_mini,
            font=(ICON_FONT, -9))

        ox = WIDTH - pad_r - 106   # clears the three circle buttons
        # One-line readout (frame 2a): fill-dot + "OBS 30.2 · host:port".
        # _obs_card_sub kept as a no-op slot for older call sites.
        self._obs_card_title = self.bg.create_text(
            ox, cy, anchor="e", text="OBS disconnected",
            fill=MUTED, font=dv.type_font("meta"))
        self._obs_card_sub = self.bg.create_text(
            ox, cy, anchor="e", text="", fill=FAINT, font=dv.font(10.5, mono=True))
        self._obs_card_dot = self.bg.create_text(
            ox - 210, cy, anchor="e", text=ICON_GLYPHS["record"],
            fill=FAINT, font=(ICON_FONT, -7))

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
        # Frame 2a header actions are only Open folder + Rescan Steam.
        # Customise (dashboard rearrange) stays available via double-click on
        # the pane title so the layout system isn't deleted — just off the
        # chrome the mockup draws.
        self.customise_btn = ctk.CTkButton(
            self.root, text="Customise", command=self._toggle_customise,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(WIDTH - 390, cy), border_width=1, border_color=EDGE,
            corner_radius=dv.RADIUS_CONTROL, font=ctk.CTkFont(size=12),
        )
        self._customise_win = self.bg.create_window(
            WIDTH - dv.PANE_HEADER_PAD_X - 352, cy - 15, anchor="nw",
            window=self.customise_btn, width=100, height=30)
        self.bg.itemconfigure(self._customise_win, state="hidden")
        self.bg.tag_bind(self._topbar_title, "<Double-Button-1>",
                         lambda _e: self._toggle_customise())

    def _draw_keycap(self, cx, cy, label):
        """A small rounded keycap chip on the canvas - the sampled-corner
        glass technique, drawn as a tinted rounded tile with the key text."""
        pad_x = 5 + len(label) * 4
        w, h = pad_x * 2, 18
        tile = make_glass_tile(self._S(w), self._S(h), SURFACE, tint_alpha=235,
                               radius=self._S(5), border_hex=EDGE, border_alpha=200)
        photo = to_photo(tile)
        self._images.append(photo)
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
        self._current_view = None
        self._show_view("dashboard")

    def _show_view(self, name):
        if name == self._current_view:
            return
        for view in self._views:
            self.bg.itemconfigure(f"view_{view}",
                                  state="normal" if view == name else "hidden")
        self._current_view = name
        self.bg.itemconfigure(self._topbar_title, text=VIEW_TITLES[name])
        # Frame 2a has no Customise chrome. Double-click the pane title to
        # enter rearrange mode; the button only appears while that mode is on.
        show_customise = (name == "dashboard" and getattr(self, "_customising", False))
        self.bg.itemconfigure(self._customise_win,
                              state="normal" if show_customise else "hidden")
        if name != "dashboard" and getattr(self, "_customising", False):
            self._set_customise(False)
        for nav_name, parts in self._nav.items():
            self._set_nav_active(parts, nav_name == name)
        if name == "dashboard":
            # Showing the whole tag un-hides items the dashboard deliberately
            # keeps hidden (the timer/size readout and Pause button when nothing
            # is recording, and the customise grips), so re-apply their own
            # visibility rules on top.
            self._set_hero_state(self._hero_state)
            self._set_customise(self._customising)
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
        """The grid layout from config, defended against a hand-edited or
        older-format file. Unknown blocks dropped, missing ones appended full-
        width, so a bad file can never lose a panel."""
        def normalise(items, span_of):
            cleaned, seen = [], set()
            for it in items:
                name = it if isinstance(it, str) else (it or {}).get("name")
                if name in BLOCK_HEIGHTS and name not in seen:
                    span = 2 if name == "hero" else span_of(it)
                    cleaned.append({"name": name, "span": span})
                    seen.add(name)
            for b in DEFAULT_BLOCKS:
                if b not in seen:
                    cleaned.append({"name": b, "span": 2})
            return cleaned

        grid = self.config.get("dashboard_grid")
        if isinstance(grid, list):
            return normalise(grid, lambda it: 1 if isinstance(it, dict) and it.get("span") == 1 else 2)
        # migrate the older name-only "dashboard_layout"
        old = self.config.get("dashboard_layout")
        if isinstance(old, list):
            return normalise(old, lambda it: 2)
        return [dict(it) for it in DEFAULT_GRID]

    def _compute_grid(self, layout):
        """Map an ordered layout to {name: (x, y, w, h)}. Full-span blocks take a
        row; two consecutive half-span blocks share one."""
        x0 = self._content_x0()
        cw = WIDTH - MARGIN - x0
        half_w = (cw - GRID_COL_GAP) / 2
        rects = {}
        y = self._content_y0()
        i, n = 0, len(layout)
        while i < n:
            name = layout[i]["name"]
            span = 2 if name == "hero" else layout[i].get("span", 2)
            partner = None
            if span == 1 and i + 1 < n:
                pn = layout[i + 1]["name"]
                if pn != "hero" and layout[i + 1].get("span", 2) == 1:
                    partner = layout[i + 1]["name"]
            if partner:
                hl, hr = BLOCK_HEIGHTS[name][1], BLOCK_HEIGHTS[partner][1]
                rects[name] = (x0, y, half_w, hl)
                rects[partner] = (x0 + half_w + GRID_COL_GAP, y, half_w, hr)
                y += max(hl, hr) + BLOCK_GAP
                i += 2
            else:
                h = BLOCK_HEIGHTS[name][2]  # a lone half falls back to full width
                rects[name] = (x0, y, cw, h)
                y += h + BLOCK_GAP
                i += 1
        return rects

    def _render_dashboard(self):
        self._dashboard_widgets = []
        rects = self._compute_grid(self._grid_layout)
        self._grid_rects = rects
        builders = {"hero": lambda r: self._build_hero(r[0], r[1], r[2]),
                    "stats": lambda r: self._build_stats(r[0], r[1], r[2]),
                    "activity": lambda r: self._build_activity(r[0], r[1], r[2], r[3])}
        for name in ("hero", "stats", "activity"):
            before = set(self.bg.find_all())
            builders[name](rects[name])
            for item in set(self.bg.find_all()) - before:
                self.bg.addtag_withtag(f"blk_{name}", item)
        self._build_customise_controls(rects)

    def _relayout_grid(self, new_layout):
        """Apply a new layout by tearing the dashboard down and rebuilding it at
        the new rects. Only ever runs on a user action (drag / width toggle), so
        the rebuild cost is irrelevant."""
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
        self._render_dashboard()
        for item in set(self.bg.find_all()) - before:
            self.bg.addtag_withtag("view_dashboard", item)
        self._composite = self._base_composite
        self._persist_grid(self._grid_layout)
        self._set_hero_state(self._hero_state)
        self._set_customise(self._customising)
        self._log("[Manual] Dashboard layout changed.")

    def _persist_grid(self, layout):
        self.config["dashboard_grid"] = [dict(it) for it in layout]
        self.config.pop("dashboard_layout", None)  # retire the old key
        from .config import save_config
        save_config(self.config)

    def _build_customise_controls(self, rects):
        """A drag grip on each block plus a Full/Half toggle, hidden until
        Customise is on. Built into the dashboard so they tag/relayout with it."""
        self._grips = {}
        for it in self._grid_layout:
            name = it["name"]
            x, y, w, _h = rects[name]
            tile = self._glass(x, y, w, 26, tint=ACCENT, radius=8, tint_alpha=70,
                               border_hex=ACCENT, border_alpha=90)
            label = self.bg.create_text(
                x + 12, y + 13, anchor="w", text=f"{ICON_GLYPHS[dv.ICONS['scene']]}  {BLOCK_LABELS[name]}",
                fill=NAV_ACTIVE_TEXT, font=dv.font(11, 500))
            for item in (tile, label):
                self.bg.tag_bind(item, "<ButtonPress-1>",
                                 lambda e, n=name: self._grip_press(e, n))
                self.bg.tag_bind(item, "<B1-Motion>", self._grip_drag)
                self.bg.tag_bind(item, "<ButtonRelease-1>", self._grip_release)
            parts = {"tile": tile, "label": label}
            if name != "hero":  # hero is full-width only
                chip_w = 52
                cx = x + w - chip_w - 8
                chip = self._glass(cx, y + 4, chip_w, 18, tint=BASE_BG, radius=6,
                                   tint_alpha=140, border_alpha=0)
                ctext = self.bg.create_text(
                    cx + chip_w / 2, y + 13,
                    text="Full" if it["span"] == 2 else "Half",
                    fill=ACCENT_LIGHT, font=dv.font(10, 500))
                for item in (chip, ctext):
                    self.bg.tag_bind(item, "<Button-1>",
                                     lambda e, n=name: self._toggle_block_span(n))
                parts["chip"] = chip
                parts["ctext"] = ctext
            for item in parts.values():
                self.bg.addtag_withtag(f"blk_{name}", item)
            self._grips[name] = parts
        self._set_customise(getattr(self, "_customising", False))

    def _set_customise(self, on):
        self._customising = on
        for parts in self._grips.values():
            for item in parts.values():
                self.bg.itemconfigure(item, state="normal" if on else "hidden")
        if hasattr(self, "customise_btn"):
            self.customise_btn.configure(
                text="Done" if on else "Customise",
                text_color=ACCENT_LIGHT if on else MUTED)
        if hasattr(self, "_customise_win"):
            show = on and self._current_view == "dashboard"
            self.bg.itemconfigure(self._customise_win,
                                  state="normal" if show else "hidden")

    def _toggle_customise(self):
        self._set_customise(not self._customising)

    def _toggle_block_span(self, name):
        if name == "hero" or not self._customising:
            return
        layout = [dict(it) for it in self._grid_layout]
        for it in layout:
            if it["name"] == name:
                it["span"] = 1 if it["span"] == 2 else 2
        self._relayout_grid(layout)

    def _grip_press(self, event, name):
        if not self._customising:
            return
        self._drag_block = name
        self._drag_last_y = event.y / self.scale
        self._drag_live_y = self._grid_rects[name][1]

    def _grip_drag(self, event):
        if not getattr(self, "_drag_block", None):
            return
        now = event.y / self.scale
        delta = now - self._drag_last_y
        self.bg.move(f"blk_{self._drag_block}", 0, delta)  # live feedback only
        self._drag_live_y += delta
        self._drag_last_y = now

    def _grip_release(self, _event):
        name = getattr(self, "_drag_block", None)
        if not name:
            return
        self._drag_block = None

        def centre(bn):
            r = self._grid_rects[bn]
            top = self._drag_live_y if bn == name else r[1]
            return top + r[3] / 2

        # Stable sort by vertical centre: a side-by-side pair shares a centre, so
        # their left-right order (list order) is preserved.
        new_layout = sorted(self._grid_layout, key=lambda it: centre(it["name"]))
        self._relayout_grid(new_layout)

    def _reset_dashboard(self):
        self._relayout_grid([dict(it) for it in DEFAULT_GRID])

    # ---- shared building blocks for the secondary views ----
    def _view_panel(self, title, subtitle):
        """Full-height glass panel with a heading, used by every non-dashboard
        view. Returns (x, y, w, h) of the area left for content below the head,
        plus the canvas id of the subtitle so it can be updated live."""
        x0, y = self._content_x0(), self._content_y0()
        w, h = WIDTH - MARGIN - x0, HEIGHT - MARGIN - y
        self._glass(x0, y, w, h, tint=LOG_TINT, radius=16, tint_alpha=170)
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
        self._images.append(photo)
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

    def _list_row(self, parent, title, detail, meta, command=None):
        row = ctk.CTkFrame(parent, fg_color=CARD_TINT, corner_radius=9)
        row.pack(fill="x", padx=2, pady=3)
        ctk.CTkLabel(row, text=title, text_color=TEXT, anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(row, text=detail, text_color=MUTED, anchor="w",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(0, 8))
        if meta:
            ctk.CTkLabel(row, text=meta, text_color=FAINT,
                         font=ctk.CTkFont(size=11)).place(relx=1.0, rely=0.5,
                                                          anchor="e", x=-12)
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
        self._dashboard_widgets.append(self._clip_search)

        self._clip_sort = ctk.CTkOptionMenu(
            self.root, values=["Newest", "Oldest", "Largest"],
            command=lambda _v: self._render_clips_rows(),
            fg_color=SURFACE, button_color=SURFACE, button_hover_color=SURFACE_HOVER,
            text_color=MUTED, corner_radius=dv.RADIUS_CONTROL,
            font=ctk.CTkFont(size=12), width=110, height=30)
        self.bg.create_window(x + w - 130, y + 20, anchor="nw",
                              window=self._clip_sort, width=110, height=30)

        # Left: By game. Right: the clip table.
        side_w = 224
        body_y = y + 96
        body_h = h - 96 - 34
        self.bg.create_text(x + 16, y + 82, anchor="w", text=self._track("By game"),
                            fill=FAINT, font=dv.type_font("eyebrow"))
        self.bg.create_text(x + 16 + side_w + 16, y + 82, anchor="w",
                            text=self._track("Clip"), fill=FAINT,
                            font=dv.type_font("eyebrow"))
        for label, dx in (("Size", w - 300), ("Recorded", w - 210), ("Actions", w - 96)):
            self.bg.create_text(x + dx, y + 82, anchor="w", text=self._track(label),
                                fill=FAINT, font=dv.type_font("eyebrow"))

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
        self._clips_total = len(clips)
        self.bg.itemconfigure(
            self._rec_sub,
            text=f"{len(clips)} clip{'' if len(clips) == 1 else 's'}  ·  "
                 f"{_format_bytes(total)}")
        self._render_clips_rows()

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

    def _clip_row(self, clip):
        row = ctk.CTkFrame(self._rec_list, fg_color=CARD_TINT, corner_radius=dv.RADIUS_CONTROL)
        row.pack(fill="x", padx=2, pady=3)

        ctk.CTkLabel(row, text=self._initials(clip["game"]), width=34, height=34,
                     fg_color=ACCENT_TINT, corner_radius=8, text_color=ACCENT_LIGHT,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(
            side="left", padx=(8, 10), pady=6)

        # Actions: Play · Reveal · Delete (Length/thumbs need ffmpeg — omitted)
        for glyph, command in (
            (ICON_GLYPHS[dv.ICONS["trash"]], lambda c=clip: self._delete_clip(c)),
            (ICON_GLYPHS[dv.ICONS["reveal"]],
             lambda c=clip: self._open_path(os.path.dirname(c["path"]))),
            (ICON_GLYPHS["play"], lambda c=clip: self._open_path(c["path"])),
        ):
            btn = ctk.CTkButton(
                row, text=glyph, width=28, height=28,
                fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
                corner_radius=8, font=ctk.CTkFont(family=ICON_FONT, size=13),
                command=command)
            btn.pack(side="right", padx=2)

        ctk.CTkLabel(row, text=self._recorded_label(clip["mtime"]), width=90, anchor="e",
                     text_color=MUTED, font=ctk.CTkFont(size=11)).pack(side="right", padx=6)
        ctk.CTkLabel(row, text=_format_bytes(clip["size"]), width=80, anchor="e",
                     text_color=TEXT_SOFT, font=ctk.CTkFont(size=11)).pack(side="right")

        # Title: "Game — YYYY-MM-DD HH:MM" per frame 2b
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(clip["mtime"]))
        title = f"{clip['game']} — {when}"
        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(text, text=title, anchor="w",
                     text_color=TEXT, font=ctk.CTkFont(size=12)).pack(anchor="w")
        ctk.CTkLabel(text, text=clip["rel"], anchor="w", text_color=FAINT,
                     font=ctk.CTkFont(family="Consolas", size=10)).pack(anchor="w")

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
        # Frame 2d header action is Rescan library only (Game data → Settings/sync).
        self._view_button(x + w - 150, y + 20, 130, "Rescan library", self._rescan_steam)

        col_w = (w - 48) / 2
        # Frame 2d unclassified card sits above the two lists.
        top_h = 128
        self._games_pending = self._scroll_list(x + 16, y + 78, w - 32, top_h)

        list_y = y + 78 + top_h + 26
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
                            text="Right-click a row to move it back to Games.",
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

        pending_names = []
        next_review = None
        try:
            pending_names = self.classifier.peek_pending_reviews()
            next_review = self.classifier.peek_next_review()
        except Exception:
            pass
        if next_review:
            self._games_unclassified_card(next_review, len(pending_names))
        elif pending_names:
            # Modal already holds the only item (_in_review) — don't double-offer.
            self._empty_note(
                self._games_pending,
                "A classify prompt is open — answer it there.")
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

        awaiting = (f"{len(pending_names)} awaiting your call   ·   "
                    if pending_names else "")
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
                self._list_row(self._games_list, name, exes, entry["source"] or "manual")

        if not non_games:
            self._empty_note(self._nongames_list, "Nothing ignored yet.")
            return
        keep_alive = {p.lower() for p in self.config.get("keep_alive_audio_processes", [])}
        for basename in sorted(non_games, key=str.lower):
            row = self._list_row(
                self._nongames_list, basename,
                "keep-alive" if basename.lower() in keep_alive else "", "ignored")
            self._bind_promote(row, basename)

    def _games_unclassified_card(self, review, pending_count):
        """Frame 2d candidate card with It's a game / Not a game.

        ``review`` is ``(key, basenames, suggested_name)`` from
        ``peek_next_review``. Buttons call ``take_pending_review`` so the modal
        poll cannot race the same item.
        """
        key, basenames, suggested = review
        title = suggested or suggest_display_name(key)
        exe_line = basenames[0] if basenames else key
        more = max(0, pending_count - 1)
        sub = f"{exe_line}  ·  not classified yet"
        if more:
            sub += f"  ·  +{more} more waiting"

        card = ctk.CTkFrame(self._games_pending, fg_color=CARD_TINT,
                            corner_radius=dv.RADIUS_CARD)
        card.pack(fill="x", padx=4, pady=4)
        inner = ctk.CTkFrame(card, fg_color=CARD_CORE, corner_radius=dv.RADIUS_TILE)
        inner.pack(fill="x", padx=5, pady=5)

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=14)

        chip = ctk.CTkLabel(
            row, text="?", width=44, height=44, fg_color=SURFACE,
            corner_radius=12, text_color=ACCENT_LIGHT,
            font=ctk.CTkFont(size=18, weight="bold"))
        chip.pack(side="left", padx=(0, 14))

        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(text, text=self._track("Unclassified"), anchor="w",
                     text_color=ACCENT_LIGHT,
                     font=ctk.CTkFont(size=10)).pack(anchor="w")
        ctk.CTkLabel(text, text=title, anchor="w", text_color=TEXT,
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(text, text=sub, anchor="w", text_color=FAINT,
                     font=ctk.CTkFont(family="Consolas", size=11)).pack(anchor="w")

        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(side="right", padx=(12, 0))
        yes = ctk.CTkButton(
            actions, text="It's a game", width=120, height=36,
            fg_color=GREEN_TINT, hover_color=GREEN_TINT_HOVER,
            text_color=ACCENT_LIGHT, border_width=1, border_color=ACCENT,
            corner_radius=999, font=ctk.CTkFont(size=12),
            command=lambda k=key: self._decide_pending(k, True))
        yes.pack(side="left", padx=(0, 8))
        no = ctk.CTkButton(
            actions, text="Not a game", width=110, height=36,
            fg_color="transparent", hover_color=SURFACE_HOVER,
            text_color=MUTED, border_width=1, border_color=EDGE,
            corner_radius=999, font=ctk.CTkFont(size=12),
            command=lambda k=key: self._decide_pending(k, False))
        no.pack(side="left")

    def _decide_pending(self, key, is_game):
        """Resolve one unclassified app from the Games card (frame 2d)."""
        taken = self.classifier.take_pending_review(key)
        if not taken:
            self._refresh_games()
            return False
        key, basenames, suggested = taken
        try:
            if is_game:
                display = suggested or self._ask_display_name(key)
                if not display:
                    # User cancelled the name prompt — put it back.
                    self.classifier.finish_review(key)
                    self.classifier.queue_for_manual_review(basenames[0])
                    self._refresh_games()
                    return False
                self.classifier.resolve_review(basenames, True, display)
                self._log(f"[Manual] {basenames[0]} -> game ({display})")
            else:
                self.classifier.resolve_review(basenames, False)
                self._log(f"[Manual] {basenames[0]} -> not a game")
        finally:
            self.classifier.finish_review(key)
        self._refresh_games()
        self._push_game_data()
        return True

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
        self.classifier.mark_game(basename, suggest_display_name(basename))
        self._log(f"[Manual] {basename} -> game")
        self._refresh_games()
        self._push_game_data()
        return True

    def _push_game_data(self):
        """Mirror a manual reclassification to the shared game list."""
        if not (self.gamesync and self.gamesync.enabled):
            return
        try:
            snapshot = self.classifier.snapshot()
        except Exception:
            return
        threading.Thread(target=lambda: self.gamesync.push(snapshot), daemon=True).start()

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
        # Step 7 / frame 2e: honest empty until HID + scan-code bindings exist.
        # Never draw a fabricated "connected" pad or HID id.
        (x, y, w, h), sub = self._view_panel(
            "Macropad", "No pad connected")
        self.bg.itemconfigure(sub, text="3×3 pad · not connected")

        self._glass(x + 24, y + 90, w - 48, 200, tint=CARD_TINT,
                    radius=dv.RADIUS_CARD, tint_alpha=110,
                    border_hex=CARD_BORDER, border_alpha=26)
        self._glass(x + 29, y + 95, w - 58, 190, tint=CARD_CORE,
                    radius=dv.RADIUS_TILE, tint_alpha=180, border_alpha=0)
        self.bg.create_text(
            x + 48, y + 120, anchor="nw", width=w - 96,
            text="No device layer yet.\n\n"
                 "Frame 2e draws a connected HID pad with a live key map. That "
                 "subsystem is not in this build — bindings must be by scan code, "
                 "and there is no HID input code in obsauto/.\n\n"
                 "This page stays empty on purpose until that layer exists.",
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
        self._settings_geom = (x, y, w, h)

        # Frame 2c header shows Saved timestamp; Reveal lives in the section rail.
        self._settings_group = settings_spec.GROUPS[0][0]
        self._settings_nav = {}
        ny = y + 78
        for key, title, _blurb in settings_spec.GROUPS:
            self._settings_nav[key] = self._settings_nav_item(x + 20, ny, 172, 34, title, key)
            ny += 38

        # Config file card at the foot of the section rail (frame 2c).
        from .paths import APP_DIR
        cfg_path = os.path.join(APP_DIR, "config.json")
        card_h = 88
        cy = y + h - card_h - 12
        self._glass(x + 16, cy, 180, card_h, tint=CARD_TINT, radius=dv.RADIUS_TILE,
                    tint_alpha=100, border_hex=CARD_BORDER, border_alpha=26)
        self.bg.create_text(x + 28, cy + 16, anchor="w", text=self._track("Config file"),
                            fill=FAINT, font=dv.type_font("eyebrow"))
        shown = cfg_path if len(cfg_path) < 28 else ("…" + cfg_path[-24:])
        self.bg.create_text(x + 28, cy + 38, anchor="w", text=shown, fill=MUTED,
                            font=dv.font(10.5, mono=True), width=156)
        self._view_button(x + 28, cy + 56, 90, "Reveal", self._open_config_file)

        bx, by = x + 208, y + 76
        bw, bh = w - 232, h - 92
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
            self.bg.tag_bind(item, "<Leave>", lambda _e: self.bg.configure(cursor=""))
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

        blurb = next((b for k, _t, b in settings_spec.GROUPS if k == self._settings_group), "")
        if blurb:
            ctk.CTkLabel(self._settings_host, text=blurb, anchor="w", justify="left",
                         wraplength=520, text_color=FAINT,
                         font=ctk.CTkFont(size=11)).pack(anchor="w", padx=12, pady=(10, 2))
        for field in settings_spec.fields_in(self._settings_group):
            self._settings_field(field)
        if self._settings_group == "obs":
            self._settings_connection_footer()

    def _settings_connection_footer(self):
        """Frame 2c Connection footer: status + handshake ms + Test again."""
        foot = ctk.CTkFrame(self._settings_host, fg_color=GREEN_TINT,
                            corner_radius=dv.RADIUS_TILE, border_width=1,
                            border_color=ACCENT)
        foot.pack(fill="x", padx=12, pady=(18, 12))
        row = ctk.CTkFrame(foot, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=10)

        if self.obs.connected:
            ver = self._obs_version or ""
            hs = (f" — handshake {self._handshake_ms} ms"
                  if self._handshake_ms is not None else "")
            status = f"Connected to OBS{(' ' + ver) if ver else ''}{hs}"
            color = ACCENT_LIGHT
            glyph = ICON_GLYPHS["plugs-connected"]
        else:
            status = "Not connected to OBS"
            color = MUTED
            glyph = ICON_GLYPHS["plugs"]

        ctk.CTkLabel(row, text=glyph, text_color=color,
                     font=ctk.CTkFont(family=ICON_FONT, size=14)).pack(side="left")
        self._settings_conn_label = ctk.CTkLabel(
            row, text=status, anchor="w", text_color=color,
            font=ctk.CTkFont(size=12))
        self._settings_conn_label.pack(side="left", padx=10, fill="x", expand=True)

        test = ctk.CTkButton(
            row, text="Test again", width=110, height=34,
            fg_color="transparent", hover_color=SURFACE_HOVER,
            text_color=TEXT, border_width=1, border_color=ACCENT,
            corner_radius=999, font=ctk.CTkFont(size=12),
            command=self._test_obs_connection)
        test.pack(side="right")
        self._focus_ring(test, resting_border=ACCENT)

    def _test_obs_connection(self):
        """Settings 2c 'Test again' — reconnect on a worker, time the handshake."""
        if self._connecting:
            self._log("[Manual] A connect attempt is already in flight.")
            return
        self._connecting = True
        self._abort_connect = False
        self._set_obs_status("Connecting...", AMBER)
        if hasattr(self, "_settings_conn_label"):
            self._settings_conn_label.configure(text="Testing connection…",
                                                text_color=MUTED)

        def worker():
            t0 = time.perf_counter()
            error = None
            ms = None
            try:
                if self.obs.connected:
                    self.obs.disconnect()
                ensure_obs_running(self.config.get("obs_path"), log=self._log)
                self.obs.connect()
                ms = int((time.perf_counter() - t0) * 1000)
            except Exception as exc:
                error = exc

            def apply():
                self._connecting = False
                if self._abort_connect:
                    return
                if error is not None:
                    err = error
                    self._handshake_ms = None
                    self._log(f"[Manual] Test connection failed: {err}")
                    self._set_obs_status("Disconnected", RED)
                    if hasattr(self, "_settings_conn_label"):
                        self._settings_conn_label.configure(
                            text=f"Failed — {err}", text_color=EMBER)
                    return
                self._handshake_ms = ms
                self._refresh_obs_meta()
                self._set_obs_status("Connected", GREEN)
                self._obs_connected = True
                if not self.monitor._running:
                    self.monitor.start()
                    self._set_monitoring(True)
                self._log(f"[Manual] Test connection ok — handshake {ms} ms")
                if self._settings_group == "obs":
                    self._render_settings_group()

            self._ui(apply)

        threading.Thread(target=worker, daemon=True).start()

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
            if key in ("toggle_hotkey", "toggle_hotkey_scancode"):
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
        h = HERO_H
        pad = dv.HERO_PAD
        bezel = 5

        # Double bezel: "tray 5 · r22 / r17". A flat card is a bug.
        self._status_card_geom = (x, y, w, h)
        self._status_card_item = self._glass(x, y, w, h, radius=dv.RADIUS_CORE,
                                             tint=CARD_TINT, tint_alpha=110)
        self._hero_core_geom = (x + bezel, y + bezel, w - bezel * 2, h - bezel * 2)
        self._glass(*self._hero_core_geom, radius=dv.RADIUS_CARD, tint=CARD_CORE,
                    tint_alpha=196, border_alpha=0)

        left_x = x + bezel + pad
        preview_w = dv.PREVIEW_W
        preview_h = int(preview_w * 9 / 16)
        preview_x = x + w - bezel - pad - preview_w
        preview_y = y + bezel + pad
        left_w = preview_x - 22 - left_x
        self._hero_left = (left_x, y + bezel, left_w)

        # Eyebrow badge (state pill)
        self._hero_badge_geom = (left_x, y + bezel + pad, 128, 22)
        self._hero_badge_item = self._glass(left_x, y + bezel + pad, 128, 22,
                                            tint=ACCENT, radius=11, tint_alpha=40,
                                            border_alpha=0)
        self.rec_dot_id = self.bg.create_text(
            left_x + 13, y + bezel + pad + 11, text=ICON_GLYPHS["record"],
            fill=ACCENT, font=(ICON_FONT, -7))
        self._hero_badge_text = self.bg.create_text(
            left_x + 26, y + bezel + pad + 11, anchor="w",
            text=self._track("Watching"), fill=ACCENT_LIGHT,
            font=dv.type_font("eyebrow"))
        self._hero_sub_id = self.bg.create_text(
            left_x + 142, y + bezel + pad + 11, anchor="w", text="", fill=MUTED,
            font=dv.type_font("meta"))

        # Controller chip + game title + source line (frame 2a — no folder chip)
        title_y = y + bezel + pad + 38
        chip = 44
        self._glass(left_x, title_y, chip, chip, tint=SURFACE, radius=12,
                    tint_alpha=220, border_hex=CARD_BORDER, border_alpha=40)
        self.bg.create_text(
            left_x + chip / 2, title_y + chip / 2,
            text=ICON_GLYPHS[dv.ICONS["games"]], fill=ACCENT_LIGHT,
            font=(ICON_FONT, -18))
        self.game_label_id = self.bg.create_text(
            left_x + chip + 13, title_y + 8, anchor="w", text="No game in focus",
            fill=MUTED, font=dv.type_font("game_title"), width=left_w - chip - 16)
        self._hero_source_id = self.bg.create_text(
            left_x + chip + 13, title_y + 34, anchor="w", text="", fill=FAINT,
            font=dv.font(11.5, mono=True), width=left_w - chip - 16)
        # Legacy alias — folder chip removed; keep an id so old call sites no-op.
        self.folder_label_id = self._hero_source_id

        # Elapsed / File size / Bitrate — real values only
        readout_y = title_y + chip + 22
        self._readouts = {}
        col_w = left_w / 3.0
        for i, (key, label) in enumerate((("elapsed", "Elapsed"),
                                          ("size", "File size"),
                                          ("bitrate", "Bitrate"))):
            rx = left_x + i * col_w
            cap = self.bg.create_text(rx, readout_y, anchor="w", text=self._track(label),
                                      fill=FAINT, font=dv.type_font("eyebrow"))
            val = self.bg.create_text(
                rx, readout_y + 24, anchor="w", text="--",
                fill=TEXT, font=dv.font(dv.TYPE["timer"]["size"] if key == "elapsed" else 19,
                                        mono=True))
            self._readouts[key] = (cap, val)
        self.timer_label_id = self._readouts["elapsed"][1]
        self.storage_label_id = self._readouts["size"][1]
        self._elapsed_label_id = self._readouts["elapsed"][0]
        self._size_label_id = self._readouts["size"][0]

        self._hero_hint_id = self.bg.create_text(
            left_x, readout_y + 12, anchor="w", text="", fill=FAINT,
            font=dv.type_font("body"), width=left_w)

        # Transport — Mark clip omitted (no backend). Relabelled per state.
        bt_y = y + h - bezel - pad - 40
        self._hero_primary_cmd = self._toggle_record
        self._hero_primary_text = ACCENT_LIGHT
        self._hero_secondary_cmd = self._toggle_pause
        self.record_toggle_btn = ctk.CTkButton(
            self.root, text="Record now", command=lambda: self._hero_primary_cmd(),
            state="disabled",
            fg_color=GREEN_TINT, hover_color=GREEN_TINT_HOVER, text_color=ACCENT_LIGHT,
            bg_color=self._bg_at(left_x + 78, bt_y + 20), border_width=1,
            border_color=ACCENT, corner_radius=999,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._focus_ring(self.record_toggle_btn, resting_border=ACCENT)
        self._record_btn_win = self.bg.create_window(
            left_x, bt_y, anchor="nw", window=self.record_toggle_btn,
            width=180, height=dv.CONTROL_PILL_H)
        self._dashboard_widgets.append(self.record_toggle_btn)
        self.pause_btn = ctk.CTkButton(
            self.root, text="Pause", command=lambda: self._hero_secondary_cmd(),
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(left_x + 174 + 60, bt_y + 20), border_width=1,
            border_color=EDGE, corner_radius=999,
            font=ctk.CTkFont(size=13),
        )
        self._focus_ring(self.pause_btn)
        self._pause_btn_win = self.bg.create_window(
            left_x + 190, bt_y, anchor="nw", window=self.pause_btn, width=150,
            height=dv.CONTROL_PILL_H)
        self._dashboard_widgets.append(self.pause_btn)

        # Right column: 16:9 preview + scene/mic row (hidden while idle)
        self._preview_items = []
        self._build_preview(preview_x, preview_y, preview_w, preview_h)
        self._preview_geom = (preview_x, preview_y, preview_w, preview_h)
        info_y = preview_y + preview_h + 11
        info = self._glass(preview_x, info_y, preview_w, 40, tint=CARD_TINT,
                           radius=dv.RADIUS_TILE, tint_alpha=120,
                           border_hex=CARD_BORDER, border_alpha=26)
        self._preview_items.append(info)
        scene_icon = self.bg.create_text(
            preview_x + 14, info_y + 20, anchor="w",
            text=ICON_GLYPHS[dv.ICONS["scene"]], fill=MUTED, font=(ICON_FONT, -14))
        self._preview_info_id = self.bg.create_text(
            preview_x + 34, info_y + 20, anchor="w",
            text="Scene — —", fill=TEXT_SOFT, font=dv.type_font("row"))
        mic_x = preview_x + preview_w - 72
        mic_icon = self.bg.create_text(
            mic_x, info_y + 20, anchor="e",
            text=ICON_GLYPHS["microphone"], fill=FAINT, font=(ICON_FONT, -12))
        mic_lbl = self.bg.create_text(
            mic_x + 4, info_y + 20, anchor="w", text="Mic", fill=FAINT,
            font=dv.type_font("meta"))
        # Static mic track (no live meter — that would be a per-poll canvas mutate)
        bar_bg = self.bg.create_rectangle(
            preview_x + preview_w - 48, info_y + 18,
            preview_x + preview_w - 12, info_y + 21,
            fill=dv.over(dv.TEXT, 0.10, dv.CARD_CORE), outline="")
        bar_fg = self.bg.create_rectangle(
            preview_x + preview_w - 48, info_y + 18,
            preview_x + preview_w - 28, info_y + 21,
            fill=ACCENT, outline="")
        self._preview_items.extend([
            scene_icon, self._preview_info_id, mic_icon, mic_lbl, bar_bg, bar_fg,
        ])

        self._set_hero_state("disconnected")

    def _build_preview(self, x, y, w, h):
        """16:9 stand-in for the OBS scene (frame 2a). Live screenshots are
        omitted — each canvas image swap is a full-window composite."""
        tile = self._make_preview_tile(w, h)
        photo = to_photo(tile)
        self._images.append(photo)
        img = self.bg.create_image(x, y, anchor="nw", image=photo)
        self._preview_items.append(img)

        # Live chip (top-left) — ember, per the mockup
        live_chip = self._glass(x + 12, y + 12, 58, 22, tint=BASE_BG, radius=7,
                                tint_alpha=180, border_alpha=0)
        self._preview_dot_id = self.bg.create_text(
            x + 22, y + 23, anchor="w", text=ICON_GLYPHS["record"],
            fill=EMBER, font=(ICON_FONT, -7))
        live_txt = self.bg.create_text(
            x + 34, y + 23, anchor="w", text=self._track("Live"),
            fill="#FFA3B4", font=dv.type_font("eyebrow"))

        # Resolution / fps chip (bottom-right) — filled from GetVideoSettings
        self._preview_res_id = self.bg.create_text(
            x + w - 12, y + h - 14, anchor="e", text="",
            fill=ACCENT_LIGHT, font=dv.font(10, mono=True))
        # Caption
        cap = self.bg.create_text(
            x + w / 2, y + h / 2, text=self._track("OBS scene preview"),
            fill=dv.over(dv.TEXT, 0.45, "#2E2358"), font=dv.type_font("eyebrow"))
        self._preview_items.extend([
            live_chip, self._preview_dot_id, live_txt, self._preview_res_id, cap,
        ])

    def _make_preview_tile(self, w, h):
        sw, sh = self._S(w), self._S(h)
        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for i in range(sh):
            # Mockup gradient: #241E44 → #2E2358 → #5340A8
            t = i / max(1, sh - 1)
            if t < 0.42:
                col = _blend_hex("#241E44", "#2E2358", t / 0.42)
            else:
                col = _blend_hex("#2E2358", "#5340A8", (t - 0.42) / 0.58)
            r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
            draw.line([(0, i), (sw, i)], fill=(r, g, b, 255))
        bloom = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        ImageDraw.Draw(bloom).ellipse(
            [-sw * 0.2, -sh * 0.4, sw * 0.7, sh * 0.6], fill=(255, 255, 255, 26))
        img = Image.alpha_composite(img, bloom.filter(ImageFilter.GaussianBlur(self._S(30))))
        mask = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, sw - 1, sh - 1], radius=self._S(14), fill=255)
        img.putalpha(mask)
        return img

    def _set_hero_state(self, state):
        """Swap the hero card between the four v3 states from one enum.

        Frames 2a (recording), 2f (watching), 2g (paused), 2h (disconnected).
        Recording and disconnected lead with ember (live + errors); paused uses
        accent; watching is neutral.
        """
        self._hero_state = state
        tint = dv.HERO_STATES[state]["tint"] or CARD_BORDER
        light = "#FFA3B4" if tint is EMBER else ACCENT_LIGHT
        eyebrow = {
            "disconnected": "OBS disconnected",
            "watching": "Idle - watching",
            "recording": "Recording",
            "paused": f"Paused - idle {self.config.get('idle_timeout_seconds', 4)} s",
        }[state]

        badge_label = self._track(eyebrow)
        bx, by, _, bh = self._hero_badge_geom
        bw = 26 + self._text_w(badge_label, dv.type_font("eyebrow")) + 12
        self._hero_badge_geom = (bx, by, bw, bh)
        self._regen_glass(self._hero_badge_item, bx, by, bw, bh, tint=tint,
                          radius=11, tint_alpha=40, border_alpha=0)
        self.bg.itemconfigure(self._hero_badge_text, text=badge_label, fill=light)
        self.bg.itemconfigure(self.rec_dot_id, fill=tint if tint != CARD_BORDER else FAINT)

        # Title / source / hint copy per frame 2f / 2h
        if state == "watching":
            title = "No game in focus"
            source = (f"Foreground: {self._current_exe} — classified as not a game."
                      if self._current_exe else "")
            hint = "Recording starts by itself the moment a game launches."
        elif state == "disconnected":
            title = "Can't reach OBS"
            source = ""
            interval = self.config.get("reconnect_interval_seconds", 10)
            hint = (f"Retrying every {interval}s — launching from obs_path if set.")
        elif state in ("recording", "paused"):
            title = self._current_game or "Recording"
            source = self._hero_source_text()
            hint = ""
        else:
            title, source, hint = self._current_game or "", "", ""

        self.bg.itemconfigure(
            self.game_label_id, text=title,
            fill=TEXT if state in ("recording", "paused") else MUTED)
        self.bg.itemconfigure(self._hero_source_id, text=source)
        # Badge subtitle slot unused for watching (copy lives under the title)
        self.bg.itemconfigure(self._hero_sub_id, text="")

        hx, hy, hw, hh = self._status_card_geom
        self._regen_glass(self._status_card_item, hx, hy, hw, hh, radius=dv.RADIUS_CORE,
                          tint=CARD_TINT, tint_alpha=110,
                          border_hex=tint, border_alpha=70)

        show_readout = state in ("recording", "paused")
        for cap, val in self._readouts.values():
            self.bg.itemconfigure(cap, state="normal" if show_readout else "hidden")
            self.bg.itemconfigure(val, state="normal" if show_readout else "hidden")
        self.bg.itemconfigure(
            self.timer_label_id,
            fill=dv.over(dv.TEXT, dv.PAUSED_TIMER_OPACITY, dv.CARD_CORE)
            if state == "paused" else TEXT)
        self.bg.itemconfigure(
            self._hero_hint_id,
            state="hidden" if show_readout else "normal",
            text=hint)

        # Preview column: 2f — no scene preview while idle / disconnected
        preview_on = state in ("recording", "paused")
        for item in self._preview_items:
            try:
                self.bg.itemconfigure(item, state="normal" if preview_on else "hidden")
            except Exception:
                pass
        if preview_on:
            scene = self._scene_name or "Game Capture"
            self.bg.itemconfigure(
                self._preview_info_id,
                text=f"Scene — {scene}")
            self.bg.itemconfigure(
                self._preview_res_id,
                text=self._video_label or "")

        primary, secondary = {
            "recording":    (("Stop recording", self._toggle_record, True),
                             ("Pause", self._toggle_pause, False)),
            "paused":       (("Resume", self._toggle_pause, False),
                             ("Stop & save", self._toggle_record, False)),
            "watching":     (("Record anyway", self._toggle_record, False),
                             ("Pause monitoring", self._toggle_monitoring, False)),
            "disconnected": (("Retry now", self._start, True),
                             ("Connection settings",
                              lambda: self._show_view("settings"), False)),
        }[state]

        text, command, is_ember = primary
        self._hero_primary_cmd = command
        pill_tint = EMBER if is_ember else ACCENT
        pill_text = EMBER if is_ember else ACCENT_LIGHT
        self._hero_primary_text = pill_text
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
        self.bg.itemconfigure(self._pause_btn_win, state="normal")

    def _hero_source_text(self):
        """Mono source line under the game title — real exe only; no fake AppID."""
        if self._current_exe:
            return self._current_exe
        return ""

    # ---- stat tiles (frame 2a: Clips today · Recorded · Auto-culled · Idle pauses) ----
    def _build_stats(self, x0, y, w):
        gap = 12
        cols = 4 if w >= 480 else 2
        tw = (w - gap * (cols - 1)) / cols
        h = 92

        def cell(i):
            col, row = i % cols, i // cols
            return x0 + col * (tw + gap), y + row * (h + gap)

        # 1) Clips today — disk scan
        tx, ty = cell(0)
        self._stat_tile(tx, ty, tw, h, "film-strip", ACCENT, "Clips today")
        self._stat_today_val = self.bg.create_text(
            tx + 15, ty + 48, anchor="w", text="–", fill=TEXT,
            font=dv.font(24, mono=True))
        self._stat_today_sub = self.bg.create_text(
            tx + 15, ty + 71, anchor="w", text="scanning…", fill=MUTED,
            font=dv.type_font("meta"))

        # 2) Recorded — Monitor.recorded_seconds_today
        tx, ty = cell(1)
        self._stat_tile(tx, ty, tw, h, "hourglass-medium", ACCENT, "Recorded")
        self._stat_recorded_val = self.bg.create_text(
            tx + 15, ty + 48, anchor="w", text="–", fill=TEXT,
            font=dv.font(24, mono=True))
        self._stat_disk_val = self._stat_recorded_val   # legacy alias
        self._stat_disk_sub = self.bg.create_text(
            tx + 15, ty + 71, anchor="w", text="this session's kept clips",
            fill=MUTED, font=dv.type_font("meta"))

        # 3) Auto-culled — Monitor.auto_culled
        tx, ty = cell(2)
        self._stat_tile(tx, ty, tw, h, "trash", ACCENT, "Auto-culled")
        self._stat_culled_val = self.bg.create_text(
            tx + 15, ty + 48, anchor="w", text="0", fill=TEXT,
            font=dv.font(24, mono=True))
        # Idle timeout slider lives in Settings now (mockup 2a has no slider here).
        self.timeout_value_id = self._stat_culled_val

        # 4) Idle pauses — Monitor.idle_pauses
        tx, ty = cell(3)
        self._stat_tile(tx, ty, tw, h, "moon", ACCENT, "Idle pauses")
        self._stat_pauses_val = self.bg.create_text(
            tx + 15, ty + 48, anchor="w", text="0", fill=TEXT,
            font=dv.font(24, mono=True))
        self._stat_sync_sub = self.bg.create_text(
            tx + 15, ty + 71, anchor="w", text="", fill=MUTED,
            font=dv.type_font("meta"))

    def on_offload_state(self, pending):
        """NAS queue status — kept for the offloader callback; no Sync tile now."""
        pass

    @staticmethod
    def _format_recorded(seconds):
        seconds = max(0, int(seconds or 0))
        if seconds < 60:
            return f"{seconds}s"
        hours, rem = divmod(seconds, 3600)
        mins = rem // 60
        if hours:
            return f"{hours}h {mins}m"
        return f"{mins}m"

    def _stat_tile(self, x, y, w, h, role, color, label):
        """One stat tile - two layers, per "a flat card is a bug"."""
        self._glass(x, y, w, h, tint=CARD_TINT, radius=dv.RADIUS_TILE, tint_alpha=120,
                    border_hex=CARD_BORDER, border_alpha=26)
        self._glass(x + 4, y + 4, w - 8, h - 8, tint=CARD_CORE,
                    radius=dv.RADIUS_TILE - 4, tint_alpha=150, border_alpha=0)
        self.bg.create_text(x + 15, y + 20, anchor="w", text=ICON_GLYPHS[role],
                            fill=color, font=(ICON_FONT, -13))
        self.bg.create_text(x + 34, y + 20, anchor="w", text=self._track(label),
                            fill=FAINT, font=dv.type_font("eyebrow"))

    # ---- activity log (frame 2a dashboard block) ----
    def _build_activity(self, x0, y, w, h):
        # Outer shell + header row with All tags / Copy log (mockup 2a).
        self._glass(x0, y, w, h, tint=CARD_TINT, radius=18, tint_alpha=100,
                    border_hex=CARD_BORDER, border_alpha=26)
        inner = self._glass(x0 + 4, y + 4, w - 8, h - 8, tint=dv.GROUND,
                            radius=14, tint_alpha=184, border_alpha=0)
        del inner
        self.bg.create_text(x0 + 20, y + 20, anchor="w", text=self._track("Activity"),
                            fill=FAINT, font=dv.type_font("eyebrow"))

        copy_btn = ctk.CTkButton(
            self.root, text=f"{ICON_GLYPHS['copy-simple']}  Copy log",
            command=self._copy_log,
            fg_color="transparent", hover_color=SURFACE_HOVER, text_color=FAINT,
            bg_color=self._bg_at(x0 + w - 80, y + 22), border_width=0,
            corner_radius=dv.RADIUS_CONTROL, font=ctk.CTkFont(size=11),
            height=24)
        self.bg.create_window(x0 + w - 110, y + 10, anchor="nw",
                              window=copy_btn, width=96, height=24)
        self._dashboard_widgets.append(copy_btn)

        tags = ["All tags"] + sorted(LOG_TAG_COLORS)
        self._log_filter = ctk.CTkOptionMenu(
            self.root, values=tags, command=self._on_log_filter,
            fg_color="transparent", button_color="transparent",
            button_hover_color=SURFACE_HOVER, text_color=FAINT,
            corner_radius=dv.RADIUS_CONTROL, font=ctk.CTkFont(size=11),
            width=100, height=24)
        self._log_filter.set("All tags")
        self.bg.create_window(x0 + w - 220, y + 10, anchor="nw",
                              window=self._log_filter, width=100, height=24)
        self._dashboard_widgets.append(self._log_filter)

        box_x, box_y = x0 + 16, y + 42
        box_w, box_h = w - 32, h - 54
        self.console = ctk.CTkTextbox(
            self.root, state="disabled", wrap="word", fg_color=LOG_BG, corner_radius=0,
            bg_color=LOG_BG,
            font=ctk.CTkFont(family="Consolas", size=11), text_color=MUTED,
        )
        self.bg.create_window(box_x, box_y, anchor="nw", window=self.console,
                              width=box_w, height=box_h)
        self._prepare_log_tags(self.console)
        self._dashboard_widgets.append(self.console)
        self._replay_filtered_log()

    def _on_log_filter(self, value):
        self._log_filter_tag = None if value == "All tags" else value
        self._replay_filtered_log()

    def _copy_log(self):
        text = "\n".join(self._log_lines[-LOG_HISTORY:])
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self._log("[Manual] Activity log copied to clipboard.")
        except Exception as exc:
            self._log(f"[Manual] Couldn't copy log: {exc}")

    def _replay_filtered_log(self):
        if self.console is None:
            return
        lines = list(self._log_lines[-LOG_HISTORY:])
        tag = self._log_filter_tag
        if tag:
            lines = [ln for ln in lines if ln.startswith(f"[{tag}]")]
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        self._append_log_batch(self.console, lines)

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
        # Frame 2a "Clips today" is a bare count; size stays on the sub-line.
        self.bg.itemconfigure(self._stat_today_val, text=str(clips))
        self.bg.itemconfigure(self._stat_today_sub,
                              text=f"{_format_bytes(total)} on disk" if clips else "nothing yet")
        self._refresh_monitor_stats()

        # The rail storage card. Left blank until a real reading arrives.
        if usage_pair:
            free, capacity = usage_pair
            used_frac = 0.0 if not capacity else max(0.0, min(1.0, (capacity - free) / capacity))
            self.bg.itemconfigure(self._store_pct, text=f"{used_frac * 100:.0f}%")
            x0, bar_y, full_w, bar_h = self._store_bar_rect
            self.bg.coords(self._store_bar,
                           x0, bar_y, x0 + full_w * used_frac, bar_y + bar_h)
            self.bg.itemconfigure(
                self._store_free,
                text=f"{_format_bytes(free)} free of {_format_bytes(capacity)}")

    def _refresh_monitor_stats(self):
        """Push Monitor counters into the Recorded / Auto-culled / Idle pauses tiles."""
        m = self.monitor
        if hasattr(self, "_stat_recorded_val"):
            self.bg.itemconfigure(
                self._stat_recorded_val,
                text=self._format_recorded(m.recorded_seconds_today))
        if hasattr(self, "_stat_culled_val"):
            self.bg.itemconfigure(self._stat_culled_val, text=str(m.auto_culled))
        if hasattr(self, "_stat_pauses_val"):
            self.bg.itemconfigure(self._stat_pauses_val, text=str(m.idle_pauses))

    # ---- titlebar status updaters ----
    def _set_obs_status(self, text, color):
        """Update the OBS readout in the titlebar (frame 2a one-liner).

        Connected form: ``OBS 30.2 · localhost:4455`` — version only when
        GetVersion has returned; never invent a build number.
        """
        disconnected = color in (EMBER, RED)
        host = (f"{self.config.get('obs_host', 'localhost')}:"
                f"{self.config.get('obs_port', 4455)}")
        if disconnected:
            label = f"OBS {text.lower()}"
            fill = EMBER
            self.bg.itemconfigure(self._obs_card_dot, text=ICON_GLYPHS["record"],
                                  fill=FAINT)
        else:
            # Frame 2a: "OBS 30.2 · localhost:4455" — omit the version until
            # GetVersion lands so we never invent a build number.
            ver = f" {self._obs_version}" if self._obs_version else ""
            if text.lower() in ("connected", "ok"):
                label = f"OBS{ver} · {host}"
            else:
                label = f"OBS {text.lower()} · {host}"
            fill = MUTED
            self.bg.itemconfigure(self._obs_card_dot, text=ICON_GLYPHS["record"],
                                  fill=ACCENT)
        self.bg.itemconfigure(self._obs_card_title, text=label, fill=fill)
        # Host is folded into the title line now.
        self.bg.itemconfigure(self._obs_card_sub, text="")

    def _set_monitoring(self, on):
        self._monitoring_on = on
        self.bg.itemconfigure(self._mon_label,
                              text="Monitoring on" if on else "Monitoring off",
                              fill=NAV_ACTIVE_TEXT if on else TEXT_SOFT)
        self.bg.itemconfigure(self._mon_icon, fill=ACCENT if on else FAINT)

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
        # for the Activity view to replay, and buffer the line for the UI. The
        # actual textbox write is coalesced onto the Tk thread by _flush_log, so
        # a burst of hundreds of lines becomes one textbox update per ~80ms
        # instead of one window composite per line (which pegged the UI under a
        # log flood), and Tk is only ever touched from the main thread.
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
        """Drain the pending buffer into the log textbox(es) in one batch. Runs
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
        if self._log_filter_tag:
            pending = [ln for ln in pending
                       if ln.startswith(f"[{self._log_filter_tag}]")]
        if self.console is not None and pending:
            self._append_log_batch(self.console, pending)

    def _prepare_log_tags(self, box):
        """Colour-code the [Subsystem] prefix and give lines breathing room.
        Reaches into CTkTextbox's underlying tk.Text (private but stable across
        ctk 5.x) since CTkTextbox doesn't proxy tag configuration - guarded so a
        ctk update can't crash the app."""
        try:
            tb = box._textbox
            for tag, color in LOG_TAG_COLORS.items():
                tb.tag_config(f"t_{tag}", foreground=color)
            tb.configure(spacing1=2, spacing3=2)
        except Exception:
            pass

    def _append_log_batch(self, box, messages):
        """Write many log lines with a single state toggle + one scroll, so the
        cost is per-flush, not per-line."""
        box.configure(state="normal")
        for message in messages:
            tagged = False
            try:
                m = re.match(r"\[(\w+)\]", message)
                if m and m.group(1) in LOG_TAG_COLORS:
                    tb = box._textbox
                    tb.insert("end", m.group(0), (f"t_{m.group(1)}",))
                    tb.insert("end", message[m.end():] + "\n")
                    tagged = True
            except Exception:
                tagged = False
            if not tagged:
                box.insert("end", message + "\n")
        # Keep the widget bounded too, or a long session's textbox grows without
        # limit and every insert gets slower. Trim from the top to LOG_HISTORY.
        try:
            tb = box._textbox
            line_count = int(tb.index("end-1c").split(".")[0])
            if line_count > LOG_HISTORY:
                tb.delete("1.0", f"{line_count - LOG_HISTORY + 1}.0")
        except Exception:
            pass
        box.see("end")
        box.configure(state="disabled")

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
                    self.bg.itemconfigure(self.timer_label_id, text=self._tray_elapsed)
                    written = status.get("outputBytes", 0)
                    self.bg.itemconfigure(self.storage_label_id, text=_format_bytes(written))
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
        self._refresh_monitor_stats()

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
        self._set_enabled(self.record_toggle_btn,
                          self.obs.connected or state == "disconnected",
                          text_color=self._hero_primary_text)

        # A second is right when you're watching the timer tick; while hidden in
        # the tray nothing renders it, so back off. The monitor thread drives the
        # actual recording independently of this poll.
        self.root.after(1000 if self._visible else 5000, self._poll_obs_status)


    def _toggle_record(self):
        """Manual override, independent of auto-detection. Note: if
        monitoring is active and a game is still running, the auto-detector
        may start a new recording again within a couple of seconds after a
        manual stop, since keeping it recording is its whole job - stop
        monitoring first if you want a manual stop to stick."""
        try:
            if self._is_recording:
                self.obs.stop_record()
                self.monitor._recording_target = None
                self._log("[Manual] Recording stopped.")
            else:
                self.obs.start_record()
                self._log("[Manual] Recording started.")
        except OBSError as e:
            tkinter.messagebox.showerror("OBS Error", f"Could not toggle recording: {e}")

    def _toggle_pause(self):
        """Pause/resume the in-progress recording. The monitor also pauses on
        idle by itself; this is the manual equivalent from the hero card."""
        if not self._is_recording:
            return
        try:
            if self._is_paused:
                self.obs.resume_record()
                self._log("[Manual] Recording resumed.")
            else:
                self.obs.pause_record()
                self._log("[Manual] Recording paused.")
        except OBSError as e:
            tkinter.messagebox.showerror("OBS Error", f"Could not pause recording: {e}")

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
                self._regen_glass(self._status_card_item, x, y, w, h,
                                  radius=dv.RADIUS_CORE, tint=CARD_TINT, tint_alpha=110,
                                  border_hex=border, border_alpha=70)
                return
            border_alpha = int(70 + (230 - 70) * steps[i])
            self._regen_glass(self._status_card_item, x, y, w, h,
                              radius=dv.RADIUS_CORE, tint=CARD_TINT, tint_alpha=110,
                              border_hex=border, border_alpha=min(border_alpha, 255))
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

    TOAST_W, TOAST_H = 336, 88          # base design units

    def _toast_workarea(self):
        """The work area of the screen the pointer is on.

        "Bottom-right of the active screen, 24px from both edges, above the
        taskbar." The work area already excludes the taskbar, so "above the
        taskbar" falls out of using it. v2 used winfo_screenwidth(), which is
        the *primary* monitor - on this multi-monitor setup the toast could
        appear on a screen the user wasn't looking at.
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
        # Fall back to the primary screen minus a guess at the taskbar.
        return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48)

    def _toast_content(self, event, display_name, details):
        """Everything the toast renders, resolved from an event name."""
        tint = dv.TOAST_TINTS.get(event, ACCENT)
        role = {"start": "start", "stop": "square", "pause": "pause",
                "resume": "resume", "error": "disconnected"}.get(event, "start")
        glyph = ICON_GLYPHS[dv.ICONS[role]] if role in dv.ICONS else ICON_GLYPHS[role]
        title = {
            "start": "Recording started", "stop": "Recording stopped",
            "pause": "Recording paused", "resume": "Recording resumed",
            "error": "Something went wrong",
        }.get(event, str(event))

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
                "sub": display_name, "detail": "  ·  ".join(parts)}

    def _show_notification(self, event, display_name, details=None):
        """Entry point - called from the monitor's thread, so it marshals."""
        self._ui(lambda: self._toast_replace(event, display_name, details))

    def _toast_replace(self, event, display_name, details=None):
        """The replace path. Builds the single toast on first use, then only
        ever updates it."""
        content = self._toast_content(event, display_name, details)
        toast = self._toast
        if toast is None or not toast["popup"].winfo_exists():
            toast = self._toast = self._toast_build()
        self._toast_apply(toast, content)

        # Reset the life regardless of where it was - "Replacing an event
        # resets the line to full."
        toast["remaining"] = dv.TOAST_LIFE_MS
        if toast["dismissing"]:
            # It was already fading out; bring it straight back to full rather
            # than letting the old fade finish and destroy the window.
            toast["dismissing"] = False
            self._toast_alpha(toast, 1.0)
        if not toast["ticking"]:
            toast["ticking"] = True
            self._toast_tick(toast)

    def _toast_build(self):
        w, h = self.TOAST_W, self.TOAST_H
        sw, sh = self._S(w), self._S(h)
        popup = ctk.CTkToplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.0)

        left, top, right, bottom = self._toast_workarea()
        margin = self._S(dv.TOAST_MARGIN)
        x = right - sw - margin
        y_end = bottom - sh - margin
        popup.geometry(f"{sw}x{sh}+{x}+{y_end + self._S(dv.TOAST_IN_RISE)}")
        apply_rounded_corners(popup)

        canvas = ScaledCanvas(
            tk.Canvas(popup, width=sw, height=sh, highlightthickness=0, bd=0),
            self.scale)
        canvas.pack(fill="both", expand=True)

        # Same backdrop + glass language as the main window.
        crop = (self.nebula.crop((0, 0, sw, sh))
                if self.nebula.size[0] >= sw and self.nebula.size[1] >= sh
                else self.nebula.resize((sw, sh)))
        photo = to_photo(crop)
        self._images.append(photo)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        tile = make_glass_tile(sw, sh, CARD_TINT, tint_alpha=215,
                               radius=self._S(dv.RADIUS_CARD),
                               border_hex=CARD_BORDER, border_alpha=80)
        tile_photo = to_photo(tile)
        self._images.append(tile_photo)
        canvas.create_image(0, 0, anchor="nw", image=tile_photo)

        chip = canvas.create_oval(16, 20, 48, 52, fill=ACCENT_TINT, outline="")
        icon = canvas.create_text(32, 36, text="", fill=ACCENT, font=(ICON_FONT, -13))
        title = canvas.create_text(60, 28, anchor="w", text="", fill=TEXT,
                                   font=dv.font(13, 500))
        sub = canvas.create_text(60, 48, anchor="w", text="", fill=MUTED,
                                 font=dv.type_font("meta"))
        detail = canvas.create_text(60, 66, anchor="w", text="", fill=FAINT,
                                    font=dv.font(11, mono=True), state="hidden")
        # Frame 2i: dismiss X top-right (separate from click-to-focus).
        dismiss = canvas.create_text(
            w - 18, 18, text=ICON_GLYPHS["x"], fill=FAINT, font=(ICON_FONT, -11))

        # The 2px drain. The mockup animates it scaleX(1)->scaleX(0) with the
        # document's one and only `transform-origin: left`, so the bar is
        # anchored at the left and its right edge travels leftward.
        track_x0, track_x1 = 16, w - 16
        bar_y = h - 8
        canvas.create_rectangle(track_x0, bar_y, track_x1, bar_y + dv.TOAST_DRAIN_H,
                                fill=EDGE, outline="")
        drain = canvas.create_rectangle(track_x0, bar_y, track_x1,
                                        bar_y + dv.TOAST_DRAIN_H,
                                        fill=ACCENT, outline="")

        toast = {
            "popup": popup, "canvas": canvas, "chip": chip, "icon": icon,
            "title": title, "sub": sub, "detail": detail, "drain": drain,
            "dismiss": dismiss,
            "track": (track_x0, track_x1, bar_y), "geom": (sw, sh, x, y_end),
            "remaining": dv.TOAST_LIFE_MS, "hovering": False,
            "ticking": False, "dismissing": False, "has_detail": False,
        }

        def on_enter(_e):
            toast["hovering"] = True          # "Hover freezes the drain"
            if toast["has_detail"]:
                canvas.itemconfigure(toast["detail"], state="normal")

        def on_leave(_e):
            toast["hovering"] = False
            canvas.itemconfigure(toast["detail"], state="hidden")

        def on_click(event):
            # X dismisses; anywhere else focuses the main window (frame 2i).
            cur = canvas.find_withtag("current")
            if cur and cur[0] == dismiss:
                if not toast["dismissing"]:
                    toast["dismissing"] = True
                    self._toast_fade_out(toast)
                return
            self.show()

        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<Button-1>", on_click)
        canvas.tag_bind(dismiss, "<Enter>",
                        lambda _e: canvas.itemconfigure(dismiss, fill=TEXT))
        canvas.tag_bind(dismiss, "<Leave>",
                        lambda _e: canvas.itemconfigure(dismiss, fill=FAINT))

        self._toast_rise_in(toast)
        return toast

    def _toast_apply(self, toast, content):
        canvas = toast["canvas"]
        canvas.itemconfigure(toast["chip"], fill=_tint_for(content["tint"]))
        canvas.itemconfigure(toast["icon"], text=content["glyph"], fill=content["tint"])
        canvas.itemconfigure(toast["title"], text=content["title"])
        canvas.itemconfigure(toast["sub"], text=content["sub"])
        canvas.itemconfigure(toast["detail"], text=content["detail"], state="hidden")
        canvas.itemconfigure(toast["drain"], fill=content["tint"])
        toast["has_detail"] = bool(content["detail"])
        self._toast_set_drain(toast, 1.0)
        # Re-assert topmost: another window may have been raised over it while
        # the toast sat idle between events.
        try:
            toast["popup"].attributes("-topmost", True)
        except Exception:
            pass

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
        """"Toast in: rise 16px 320ms" - and fade alongside it."""
        sw, sh, x, y_end = toast["geom"]
        rise = self._S(dv.TOAST_IN_RISE)
        steps = max(1, dv.TOAST_IN_MS // 16)

        def step(i=0):
            if not toast["popup"].winfo_exists():
                return
            t = min(1.0, i / steps)
            eased = 1 - (1 - t) ** 3          # matches the spec's ease-out curve
            try:
                toast["popup"].geometry(
                    f"{sw}x{sh}+{x}+{int(y_end + rise * (1 - eased))}")
            except Exception:
                return
            self._toast_alpha(toast, eased)
            if t < 1.0:
                toast["popup"].after(16, lambda: step(i + 1))

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
        self._toast_set_drain(toast, toast["remaining"] / float(dv.TOAST_LIFE_MS))
        toast["popup"].after(50, lambda: self._toast_tick(toast))

    def _toast_fade_out(self, toast):
        """"Toast out: fade 200ms." No slide - the spec only fades on the way
        out, and a replacement arriving mid-fade cancels it (see
        _toast_replace) rather than racing it."""
        steps = max(1, dv.TOAST_OUT_MS // 16)

        def step(i=0):
            if not toast["popup"].winfo_exists():
                toast["ticking"] = False
                return
            if not toast["dismissing"]:
                # A new event arrived and took the slot back; resume ticking.
                self._toast_tick(toast)
                return
            t = min(1.0, i / steps)
            self._toast_alpha(toast, 1.0 - t)
            if t >= 1.0:
                toast["ticking"] = False
                if self._toast is toast:
                    self._toast = None
                try:
                    toast["popup"].destroy()
                except Exception:
                    pass
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
        self._images.append(photo)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        tile = make_glass_tile(sw, sh, CARD_TINT, tint_alpha=225,
                               radius=self._S(dv.RADIUS_TILE),
                               border_hex=CARD_BORDER, border_alpha=80)
        tile_photo = to_photo(tile)
        self._images.append(tile_photo)
        canvas.create_image(0, 0, anchor="nw", image=tile_photo)

        dot = canvas.create_text(16, h / 2, text=ICON_GLYPHS["record"],
                                 fill=EMBER, font=(ICON_FONT, -9))
        timer = canvas.create_text(30, h / 2 - 8, anchor="w", text="00:00:00",
                                   fill=TEXT, font=dv.font(19, mono=True))
        game = canvas.create_text(30, h / 2 + 12, anchor="w", text="",
                                  fill=MUTED, font=dv.type_font("meta"))
        # Frame 2k: pause + stop + collapse (three 28px buttons)
        collapse = canvas.create_text(
            w - 18, h / 2, text=ICON_GLYPHS[dv.ICONS["collapse_mini"]],
            fill=FAINT, font=(ICON_FONT, -13))
        stop = canvas.create_text(
            w - 48, h / 2, text=ICON_GLYPHS["square"],
            fill=MUTED, font=(ICON_FONT, -11))
        pause = canvas.create_text(
            w - 78, h / 2, text=ICON_GLYPHS["pause"],
            fill=MUTED, font=(ICON_FONT, -12))

        mini = {"popup": popup, "canvas": canvas, "dot": dot, "timer": timer,
                "game": game, "pause": pause, "stop": stop,
                "faded": False, "fade_job": None, "drag": None}

        canvas.tag_bind(collapse, "<Button-1>", lambda _e: self.hide_mini(restore=True))
        canvas.tag_bind(stop, "<Button-1>",
                        lambda _e: self.root.after(0, self._toggle_record))
        canvas.tag_bind(pause, "<Button-1>",
                        lambda _e: self.root.after(0, self._toggle_pause))

        def press(event):
            # Ignore presses on the action glyphs so dragging can't eat the click.
            cur = canvas.find_withtag("current")
            if cur and cur[0] in (collapse, stop, pause):
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
        left, top, right, bottom = self._toast_workarea()
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
        if "pause" in mini:
            mini["canvas"].itemconfigure(
                mini["pause"],
                text=ICON_GLYPHS["play"] if paused else ICON_GLYPHS["pause"])

    def _on_state(self, **kwargs):
        def apply():
            if "game" in kwargs:
                game = kwargs["game"]
                self._tray_game = game
                self._current_game = game
                self._set_hero_state(self._hero_state)
                self._flash_status_card()
            if "exe" in kwargs:
                self._current_exe = kwargs["exe"]
                self._set_hero_state(self._hero_state)
            if "idle" in kwargs:
                self._tray_idle = kwargs["idle"]
                self._refresh_monitor_stats()
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
            "paused": "Paused",
            "idle": "Watching for a game",
            "disconnected": "OBS disconnected",
        }[state]

        game = self._current_game or self._tray_game
        elapsed = getattr(self, "_tray_elapsed", "")
        if state in ("recording", "paused") and game:
            detail = f"{game} · {elapsed}" if elapsed else game
        elif state == "disconnected":
            detail = f"{self.config.get('obs_host', 'localhost')}:{self.config.get('obs_port', 4455)}"
        elif game:
            detail = game
        else:
            detail = "No game in focus"

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
            icons = getattr(self.tray_icon, "_nebula_icons", None)
            if icons and getattr(self, "_tray_icon_state", None) != icon_state:
                self.tray_icon.icon = icons[icon_state]
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
        """Legacy hook — idle timeout is edited in Settings now (frame 2c)."""
        self.config["idle_timeout_seconds"] = int(value)
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
        self._set_obs_status("Connecting...", AMBER)
        self.autostart()

    def _on_connected(self):
        self._refresh_obs_meta()
        self._set_obs_status("Connected", GREEN)
        self._set_monitoring(True)
        self.monitor.start()

    def _refresh_obs_meta(self):
        """Pull version, video settings and scene name once after connect.

        Runs on a worker — these calls are cheap but must not block Tk.
        """
        def worker():
            version = video = scene = None
            try:
                if self.obs.connected:
                    ver = self.obs.get_version()
                    raw = ver.get("obsVersion") or ver.get("obsStudioVersion") or ""
                    # "30.2.3" → "30.2" for the titlebar chip
                    parts = str(raw).split(".")
                    version = ".".join(parts[:2]) if parts and parts[0] else str(raw) or None
            except OBSError:
                pass
            try:
                if self.obs.connected:
                    vs = self.obs.get_video_settings()
                    w = vs.get("baseWidth") or vs.get("outputWidth")
                    h = vs.get("baseHeight") or vs.get("outputHeight")
                    num = vs.get("fpsNumerator") or vs.get("fpsNum")
                    den = vs.get("fpsDenominator") or vs.get("fpsDen") or 1
                    if w and h and num:
                        fps = int(round(float(num) / float(den)))
                        video = f"{w}×{h} · {fps} fps"
            except OBSError:
                pass
            try:
                if self.obs.connected:
                    scene = self.obs.get_current_program_scene()
            except OBSError:
                pass

            def apply():
                self._obs_version = version
                self._video_label = video
                self._scene_name = scene
                if self.obs.connected:
                    self._set_obs_status("Connected", GREEN)
                if self._hero_state in ("recording", "paused"):
                    self._set_hero_state(self._hero_state)
            self._ui(apply)

        threading.Thread(target=worker, daemon=True).start()

    def autostart(self):
        """Called once at launch, and again on retry, so the app starts
        recording-ready on its own (e.g. when run from Windows startup)
        without requiring a manual click - launches OBS itself if it isn't
        already running, and retries quietly rather than popping a blocking
        error dialog. Once monitor.start() runs, the monitor's own loop takes
        over reconnecting if OBS later crashes/closes."""
        if self.monitor._running or self._connecting:
            return
        self._connecting = True
        self._abort_connect = False
        self._set_obs_status("Connecting...", AMBER)

        # Runs off the Tk thread. ensure_obs_running() may launch OBS, and
        # obs.connect() blocks for up to its 5s socket timeout - which is the
        # normal case at startup, since we've usually just launched OBS and it
        # is still booting. Done inline (as it used to be) that froze the whole
        # window for seconds on launch, and again on every 10s retry.
        def worker():
            ms = None
            try:
                ensure_obs_running(self.config.get("obs_path"), log=self._log)
                t0 = time.perf_counter()
                self.obs.connect()
                ms = int((time.perf_counter() - t0) * 1000)
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
            handshake = ms
            self._ui(lambda: self._connect_succeeded(handshake))

        threading.Thread(target=worker, daemon=True).start()

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
        if is_obs_running():
            self._log("[Monitor] OBS is running but its WebSocket server isn't "
                      "accepting connections. In OBS: Tools -> WebSocket Server "
                      "Settings -> tick 'Enable WebSocket server' (or restart OBS). "
                      "Retrying in 10s...")
            self._set_obs_status("Enable WS in OBS", AMBER)
        else:
            self._log(f"[Monitor] OBS not available yet ({error}); retrying in 10s...")
            self._set_obs_status("Disconnected", RED)
        self.root.after(10000, self.autostart)

    def _connect_succeeded(self, handshake_ms=None):
        if self._abort_connect:
            # Monitoring was stopped while this attempt was still in flight -
            # don't quietly restart it behind the user's back.
            self.obs.disconnect()
            self._set_obs_status("Disconnected", RED)
            return
        if handshake_ms is not None:
            self._handshake_ms = handshake_ms
        self._on_connected()
        self._log("[Monitor] Auto-started.")

    def _on_connection_change(self, connected):
        # _obs_connected was declared in __init__ and then never assigned - it
        # sat False for the whole run. Nothing read it until the v3 tray needed
        # a "disconnected" state, at which point a permanently-false flag would
        # have pinned the tray icon to the slashed variant forever. Keep it in
        # step here and in _poll_obs_status, which is the other place the truth
        # is observed.
        self._obs_connected = bool(connected)
        self.root.after(0, lambda: self._set_obs_status(
            *(("Connected", GREEN) if connected else ("Reconnecting...", RED))
        ))
        self.root.after(0, self._update_tray_tooltip)

    def _stop(self):
        self._abort_connect = True  # cancel any connect attempt still in flight
        self.monitor.stop()
        self.obs.disconnect()
        self._set_obs_status("Disconnected", RED)
        self._set_monitoring(False)
        self._set_hero_state("disconnected")

    def _register_hotkey(self):
        binding = self.config.get("toggle_hotkey")

        def on_press():
            # keyboard's callback fires on its own thread - bounce onto the
            # Tk thread before touching any widgets/monitor state.
            self.root.after(0, self._toggle_monitoring)

        hotkey.register(binding, on_press, suppress=True, on_log=self._log,
                        scancode=self.config.get("toggle_hotkey_scancode"))

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
        self._images.append(photo)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        tile = make_glass_tile(sw, sh, CARD_TINT, tint_alpha=225, radius=self._S(18), border_hex=CARD_BORDER, border_alpha=80)
        tile_photo = to_photo(tile)
        self._images.append(tile_photo)
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

    def _ask_display_name(self, basename):
        suggestion = suggest_display_name(basename)
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
