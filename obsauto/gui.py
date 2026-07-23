import ctypes
import math
import os
import random
import re
import shutil
import threading
import time
import tkinter as tk
import tkinter.messagebox
import traceback

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter

from . import classifier as classifier_module
from .obs_client import OBSClient, OBSError
from .monitor import Monitor, ensure_obs_running
from .app_log import log_to_file
from .theme_art import (
    generate_nebula, make_accent_glow, make_glass_tile, make_solid_tile, to_photo,
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
BASE_BG = "#0F0C1A"
CARD_TINT = "#1B1631"
CARD_SURFACE = "#191430"   # what the glass card *looks* like once composited - used as widget bg_color so rounded widget corners blend in
CARD_BORDER = "#8B7CF6"
SURFACE = "#241E44"
SURFACE_HOVER = "#332B5C"
EDGE = "#39325F"
ACCENT = "#8B7CF6"
ACCENT_HOVER = "#9D91F8"
ACCENT_TINT = "#292254"
ACCENT_LIGHT = "#B9AEF9"   # brighter violet for icons/links on the nav rail
NAV_ACTIVE_TEXT = "#E9E5FF"
TEXT_SOFT = "#C9C3E8"       # secondary body text (a touch dimmer than TEXT)
GREEN = "#3DDC84"
GREEN_LIGHT = "#8DE9B4"
GREEN_TINT = "#14382B"
GREEN_TINT_HOVER = "#1B4A38"
GREEN_HOVER = GREEN_TINT_HOVER  # legacy alias
RED = "#FF5C7A"
RED_LIGHT = "#FF7D96"
RED_TINT = "#3B1D2A"
RED_TINT_HOVER = "#4C2434"
RED_HOVER = RED_TINT_HOVER  # legacy alias
RED_DIM = "#5A2836"
AMBER = "#F5A623"
AMBER_LIGHT = "#F5B84E"
AMBER_TINT = "#3A2D14"
TEAL = "#4FD1C5"            # accent hues used by the stat tiles / log tags
BLUE = "#7FB7F0"
PINK = "#F0A6CA"
MUTED = "#9A93C4"
FAINT = "#6E6896"
TEXT = "#F5F3FF"
LOG_TINT = "#120E22"
LOG_BG = "#141024"

# Tag colors for the activity log - each subsystem gets its own hue so a
# glance at the log's left edge tells you who's talking.
LOG_TAG_COLORS = {
    "OBS": ACCENT,
    "Monitor": "#7FB7F0",
    "Steam": "#4FD1C5",
    "Manual": AMBER,
    "Classifier": "#F0A6CA",
    "Audio": GREEN,
}

# Aurora shell: a full app window with a left nav rail and a main content
# column, instead of the old single 860x660 card stack. Everything below is in
# base design units (multiplied up by self.scale on high-DPI monitors).
WIDTH, HEIGHT = 1180, 760
SIDEBAR_W = 236            # left nav rail width
TOPBAR_HEIGHT = 56         # content-column header strip
TITLEBAR_HEIGHT = 56       # draggable region height (top bar); kept name for _start_move
MARGIN = 24                # gutter inside the content column

# ---- living backdrop tuning (all in base design units) ----
DRIFT = 14          # how far the nebula may wander; it's rendered this much
                    # larger on every side so an edge is never exposed
GLOW_SIZE = 460     # diameter of the drifting violet accent bloom
STAR_COUNT = 22
STAR_DIM = "#2E2A52"    # star colour at the bottom of its twinkle
STAR_BRIGHT = "#D9D4FF"  # ...and at the top
STAR_BATCHES = 3        # stars are twinkled in this many round-robin batches

# Animation pacing. Everything decorative runs at ACTIVE_TICK_MS while the
# window is on screen, and is skipped entirely while it's hidden in the tray -
# the timers then just idle at IDLE_TICK_MS waiting to notice it come back.
ACTIVE_TICK_MS = 80
IDLE_TICK_MS = 500

VIEW_TITLES = {
    "dashboard": "Dashboard",
    "recordings": "Recordings",
    "games": "Games",
    "activity": "Activity",
    "macropad": "Macropad",
    "settings": "Settings",
}
VIDEO_EXTS = (".mkv", ".mp4", ".mov", ".flv", ".ts", ".m4v")
LOG_HISTORY = 500  # lines kept for replay into the Activity view


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
    def __init__(self, config, classifier, on_close_to_tray):
        self.config = config
        self.classifier = classifier
        self.on_close_to_tray = on_close_to_tray

        self.obs = OBSClient(
            config["obs_host"], config["obs_port"], config["obs_password"],
            on_log=self._log,
        )
        self.monitor = Monitor(
            self.obs, classifier, config, on_log=self._log, on_state=self._on_state,
            on_notify=self._show_notification, on_connection_change=self._on_connection_change,
        )
        self._notification = None
        self.tray_icon = None  # set by main.py after the tray icon is built
        self._tray_game = None
        self._tray_idle = False
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
        self._hero_state = "offline"  # offline | watching | recording | paused
        self._current_game = None
        self._eq_bars = []            # scene-preview equaliser bar canvas ids
        self._star_phase = 0          # round-robin batch for the star twinkle
        self._log_lines = []          # replayed into the Activity view when shown
        self.console = None           # set by _build_activity
        self.console_full = None      # set by _build_activity_view

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

        # ---- living backdrop ----
        # The nebula is rendered DRIFT larger on every side so it can wander
        # without ever exposing an edge; a violet bloom drifts behind the glass
        # panels (they're translucent, so it glows *through* them); and a seeded
        # scatter of stars twinkles. One cheap timer (_animate_backdrop) drives
        # all three, so the window feels alive without ever re-rendering the
        # nebula or the panels.
        self.nebula = generate_nebula(self._S(WIDTH + DRIFT * 2), self._S(HEIGHT + DRIFT * 2))
        self.bg = ScaledCanvas(
            tk.Canvas(self.root, width=self._S(WIDTH), height=self._S(HEIGHT),
                      highlightthickness=0, bd=0),
            self.scale,
        )
        self.bg.pack(fill="both", expand=True)

        bg_photo = to_photo(self.nebula)
        self._images.append(bg_photo)
        self._backdrop_id = self.bg.create_image(-DRIFT, -DRIFT, anchor="nw", image=bg_photo)

        # Pre-render a few alpha levels of the bloom and cycle them for a slow
        # "breath" - re-blurring a glow this size every frame would be far too
        # expensive to do live.
        self._glow_frames = []
        # Deliberately faint. This bloom is the one layer that ISN'T in the
        # composite widgets sample their bg_color from (it moves, so no static
        # colour could match it) - every unit of alpha here is a unit of
        # mismatch around a widget's rounded corners. The accent punch comes
        # from the nebula's own violet blobs instead, which the composite does
        # capture exactly; this just adds a gentle breathing drift on top.
        for alpha in (8, 12, 16, 20, 16, 12):
            photo = to_photo(make_accent_glow(self._S(GLOW_SIZE), ACCENT, alpha))
            self._images.append(photo)
            self._glow_frames.append(photo)
        self._glow_id = self.bg.create_image(0, 0, anchor="nw", image=self._glow_frames[0])

        # Seeded so the sky is identical every launch (a different one each
        # start would read as flicker, not atmosphere - same rule as the nebula).
        self._stars = []
        star_rng = random.Random(11)
        for _ in range(STAR_COUNT):
            sx = star_rng.uniform(8, WIDTH - 8)
            sy = star_rng.uniform(8, HEIGHT - 8)
            r = star_rng.choice((0.9, 1.2, 1.6))
            star = self.bg.create_oval(sx - r, sy - r, sx + r, sy + r,
                                       fill=STAR_DIM, outline="")
            self._stars.append((star, star_rng.uniform(0, 6.283),
                                star_rng.uniform(0.5, 1.3)))
        self._anim_t = 0.0

        # Truth source for widget corner-blending. An embedded CTk widget paints
        # the area its rounded corners cut away with a single flat bg_color, so
        # that colour has to match the real pixels behind it or you get a square
        # fringe inside the rounded panel. Approximating it (nebula tint + alpha)
        # broke once the glass tiles gained their sheen gradient. Instead keep a
        # real composite - the nebula exactly as it sits behind the window, with
        # each glass panel pasted in as it's drawn - and sample that.
        drift_px = self._S(DRIFT)
        self._composite = self.nebula.crop((
            drift_px, drift_px,
            drift_px + self._S(WIDTH), drift_px + self._S(HEIGHT),
        )).convert("RGB")

        self.bg.bind("<ButtonPress-1>", self._start_move)
        self.bg.bind("<B1-Motion>", self._on_move)

        self._build_sidebar()
        self._build_topbar()
        self._build_views()

        self._poll_manual_review()
        self._poll_obs_status()
        self._poll_disk_stats()
        self._register_hotkey()
        self._animate_backdrop()
        self._animate_hero()

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

    def _animate_backdrop(self):
        """Drives the whole living backdrop from one timer: the nebula drifts on
        a slow lissajous, the violet bloom wanders on a wider/slower path and
        breathes, and the stars twinkle.

        Skipped entirely while the window is hidden in the tray - which is
        almost all of the time, since this app's whole job is to sit in the
        background during a game. Moving the full-window nebula image forces Tk
        to repaint the entire canvas, so animating it for a window nobody can
        see was burning CPU that belongs to whatever you're playing."""
        if not self._visible:
            self.root.after(IDLE_TICK_MS, self._animate_backdrop)
            return
        t = self._anim_t
        amp = DRIFT * 0.85  # stay just inside the rendered margin

        self.bg.coords(
            self._backdrop_id,
            -DRIFT + math.sin(t * 0.19) * amp,
            -DRIFT + math.cos(t * 0.13) * amp,
        )

        self.bg.coords(
            self._glow_id,
            WIDTH / 2 - GLOW_SIZE / 2 + math.sin(t * 0.10) * (WIDTH * 0.30),
            HEIGHT / 2 - GLOW_SIZE / 2 + math.cos(t * 0.07) * (HEIGHT * 0.26),
        )
        self.bg.itemconfigure(
            self._glow_id,
            image=self._glow_frames[int(t * 1.3) % len(self._glow_frames)],
        )

        # Twinkle a third of the stars each frame, cycling. The twinkle period is
        # seconds long, so spreading the itemconfigure calls over three frames is
        # visually identical and cuts two thirds of the per-frame canvas work.
        for i in range(self._star_phase, len(self._stars), STAR_BATCHES):
            star, phase, speed = self._stars[i]
            level = (math.sin(t * speed + phase) + 1) / 2
            self.bg.itemconfigure(star, fill=_blend_hex(STAR_DIM, STAR_BRIGHT, level))
        self._star_phase = (self._star_phase + 1) % STAR_BATCHES

        self._anim_t = t + 0.085
        self.root.after(ACTIVE_TICK_MS, self._animate_backdrop)

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
                            glyph_color=FAINT, hover_glyph=TEXT):
        """A genuinely circular button drawn straight on the canvas - the
        embedded CTkButton version left a visible square bounding box behind
        its rounded shape (same underlying issue as the "transparent frame"
        bug: a native widget's non-drawn corners don't blend with canvas art
        beneath them). A canvas oval has no such box - it's just a filled
        circle sitting on the backdrop."""
        circle_id = self.bg.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius, fill=base_color, outline="",
        )
        text_id = self.bg.create_text(cx, cy, text=symbol, fill=glyph_color, font=("Segoe UI", 11))

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

    # ---- left nav rail ----
    def _build_sidebar(self):
        # Faint divider between rail and content, drawn as a 1px line all the
        # way down (the design's border-right on the sidebar).
        self.bg.create_line(SIDEBAR_W, 0, SIDEBAR_W, HEIGHT, fill=EDGE, width=1)

        # Brand: logo + wordmark + tagline.
        self._draw_logo(38, 40, 26)
        self.bg.create_text(60, 33, anchor="w", text="Nebula",
                            fill=TEXT, font=("Segoe UI Semibold", 15))
        self.bg.create_text(60, 50, anchor="w", text="auto-folder recorder",
                            fill=FAINT, font=("Segoe UI", 10))

        # Section label.
        self.bg.create_text(28, 92, anchor="w", text="WORKSPACE",
                            fill=FAINT, font=("Segoe UI", 9, "bold"))

        # Nav items. Only Dashboard is wired in this pass; the rest render as
        # calm, inactive destinations (the shell the design is built around).
        nav = [
            ("▦", "Dashboard", "dashboard", None),
            ("▷", "Recordings", "recordings", None),
            ("◉", "Games", "games", self._game_count()),
            ("∿", "Activity", "activity", None),
            ("⌨", "Macropad", "macropad", None),
            ("⚙", "Settings", "settings", None),
        ]
        self._nav = {}
        y = 108
        for glyph, label, view, badge in nav:
            self._nav[view] = self._nav_item(
                12, y, SIDEBAR_W - 24, 40, glyph, label, view, badge)
            y += 46

        # ---- bottom status stack (OBS connection + monitoring toggle) ----
        self._build_sidebar_status()

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
        tile = self._glass(x, y, w, h, tint=ACCENT, radius=10, tint_alpha=36,
                           border_hex=ACCENT, border_alpha=0)
        bar = self.bg.create_rectangle(x, y + 9, x + 3, y + h - 9,
                                       fill=ACCENT, outline="")
        icon = self.bg.create_text(x + 20, cy, anchor="w", text=glyph,
                                   fill=MUTED, font=("Segoe UI Symbol", 15))
        text = self.bg.create_text(x + 42, cy, anchor="w", text=label,
                                   fill=MUTED, font=("Segoe UI", 13))
        if badge:
            bx = x + w - 34
            self._glass(bx, cy - 9, 26, 18, tint=ACCENT, radius=8, tint_alpha=40,
                        border_hex=ACCENT, border_alpha=0)
            self.bg.create_text(bx + 13, cy, text=badge, fill=ACCENT_LIGHT,
                                font=("Segoe UI", 9, "bold"))

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
            font=("Segoe UI Semibold", 13) if active else ("Segoe UI", 13))

    def _nav_hover(self, parts, hovering):
        if parts.get("active"):
            return
        self.bg.itemconfigure(parts["text"], fill=TEXT_SOFT if hovering else MUTED)
        self.bg.itemconfigure(parts["icon"], fill=TEXT_SOFT if hovering else MUTED)
        self.bg.configure(cursor="hand2" if hovering else "")

    def _build_sidebar_status(self):
        # OBS connection card, near the bottom of the rail.
        cx, cw = 12, SIDEBAR_W - 24
        oy = HEIGHT - 118
        self._glass(cx, oy, cw, 50, tint=GREEN_TINT, radius=11, tint_alpha=90,
                    border_hex=GREEN, border_alpha=45)
        self._obs_card_dot = self.bg.create_oval(cx + 15, oy + 21, cx + 23, oy + 29,
                                                fill=RED, outline="")
        self._obs_card_title = self.bg.create_text(
            cx + 34, oy + 19, anchor="w", text="OBS disconnected",
            fill=RED_LIGHT, font=("Segoe UI Semibold", 12))
        host = f"localhost:{self.config.get('obs_port', 4455)}"
        self._obs_card_sub = self.bg.create_text(
            cx + 34, oy + 33, anchor="w", text=host,
            fill=FAINT, font=("Segoe UI", 10))

        # Monitoring toggle row - clickable, flips monitoring on/off (same
        # action as the hotkey), with the bound key shown as a keycap.
        my = HEIGHT - 60
        self._mon_tile = self._glass(cx, my, cw, 44, tint=CARD_TINT, radius=11,
                                     tint_alpha=110, border_hex=CARD_BORDER, border_alpha=30)
        self._mon_icon = self.bg.create_text(cx + 16, my + 22, anchor="w", text="◉",
                                            fill=ACCENT, font=("Segoe UI Symbol", 14))
        self._mon_label = self.bg.create_text(cx + 36, my + 22, anchor="w",
                                            text="Monitoring off", fill=TEXT_SOFT,
                                            font=("Segoe UI", 12))
        binding = self.config.get("toggle_hotkey")
        if binding:
            self._draw_keycap(cx + cw - 24, my + 22, binding.upper())
        # Whole tile is the hit target.
        hit = self.bg.create_rectangle(cx, my, cx + cw, my + 44, fill="", outline="")
        for item in (hit, self._mon_icon, self._mon_label):
            self.bg.tag_bind(item, "<Button-1>", lambda _e: self._toggle_monitoring())
            self.bg.tag_bind(item, "<Enter>", lambda _e: self.bg.configure(cursor="hand2"))
            self.bg.tag_bind(item, "<Leave>", lambda _e: self.bg.configure(cursor=""))

    # ---- content-column top bar ----
    def _build_topbar(self):
        x0 = SIDEBAR_W
        cy = TOPBAR_HEIGHT / 2
        self._topbar_title = self.bg.create_text(
            x0 + MARGIN, cy, anchor="w", text="Dashboard",
            fill=TEXT, font=("Segoe UI Semibold", 15))

        # Window controls pinned to the right edge.
        self._make_circle_button(WIDTH - 26, cy, 14, SURFACE, RED, "✕", self._hide)
        self._make_circle_button(WIDTH - 60, cy, 14, SURFACE, SURFACE_HOVER, "−", self._hide)

        # Real tool actions that don't have a home yet in this pass (their full
        # pages are later work): rescan Steam + open game data, as ghost buttons.
        self.rescan_btn = ctk.CTkButton(
            self.root, text="↻  Rescan", command=self._rescan_steam,
            fg_color=SURFACE, hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(WIDTH - 190, cy), border_width=1, border_color=EDGE,
            corner_radius=9, font=ctk.CTkFont(size=12),
        )
        self.bg.create_window(WIDTH - 244, cy - 15, anchor="nw", window=self.rescan_btn,
                              width=108, height=30)
        self.gamedata_btn = ctk.CTkButton(
            self.root, text="Game data", command=self._open_game_data,
            fg_color=SURFACE, hover_color=SURFACE_HOVER, text_color=MUTED,
            bg_color=self._bg_at(WIDTH - 300, cy), border_width=1, border_color=EDGE,
            corner_radius=9, font=ctk.CTkFont(size=12),
        )
        self.bg.create_window(WIDTH - 356, cy - 15, anchor="nw", window=self.gamedata_btn,
                              width=104, height=30)

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
        self.bg.create_text(cx, cy, text=label, fill=MUTED, font=("Segoe UI Semibold", 9))

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
            ("recordings", self._build_recordings),
            ("games", self._build_games),
            ("activity", self._build_activity_view),
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
        for nav_name, parts in self._nav.items():
            self._set_nav_active(parts, nav_name == name)
        if name == "dashboard":
            # Showing the whole tag un-hides items the dashboard deliberately
            # keeps hidden (the timer/size readout and Pause button when nothing
            # is recording), so re-apply the current state's own visibility.
            self._set_hero_state(self._hero_state)
        elif name == "recordings":
            self._refresh_recordings()
        elif name == "games":
            self._refresh_games()

    # ---- content column: geometry ----
    # The main column lives to the right of the nav rail. Everything here is in
    # base design units; x0 is the left gutter of the content area.
    def _content_x0(self):
        return SIDEBAR_W + MARGIN

    def _build_dashboard(self):
        self._build_hero()
        self._build_stats()
        self._build_activity()

    # ---- shared building blocks for the secondary views ----
    def _view_panel(self, title, subtitle):
        """Full-height glass panel with a heading, used by every non-dashboard
        view. Returns (x, y, w, h) of the area left for content below the head,
        plus the canvas id of the subtitle so it can be updated live."""
        x0, y = self._content_x0(), 62
        w, h = WIDTH - MARGIN - x0, HEIGHT - MARGIN - 62
        self._glass(x0, y, w, h, tint=LOG_TINT, radius=16, tint_alpha=170)
        self.bg.create_text(x0 + 20, y + 26, anchor="w", text=title,
                            fill=TEXT, font=("Segoe UI Semibold", 15))
        sub = self.bg.create_text(x0 + 20, y + 48, anchor="w", text=subtitle,
                                  fill=FAINT, font=("Segoe UI", 11), width=w - 300)
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
    def _build_recordings(self):
        (x, y, w, h), sub = self._view_panel(
            "Per-game folders", self.config.get("recording_root", ""))
        self._rec_sub = sub
        self._view_button(x + w - 136, y + 20, 116, "Open folder",
                          self._open_recording_root)
        self._view_button(x + w - 262, y + 20, 116, "↻  Refresh",
                          self._refresh_recordings)
        self._rec_list = self._scroll_list(x + 16, y + 74, w - 32, h - 90)
        self._rec_loaded = False

    def _refresh_recordings(self):
        root_dir = self.config.get("recording_root", "")
        for child in self._rec_list.winfo_children():
            child.destroy()
        self._empty_note(self._rec_list, "Scanning…")

        def worker():
            folders, error = [], None
            try:
                with os.scandir(root_dir) as it:
                    for entry in it:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        clips, size, newest = 0, 0, 0
                        try:
                            with os.scandir(entry.path) as inner:
                                for f in inner:
                                    if f.is_file() and f.name.lower().endswith(VIDEO_EXTS):
                                        st = f.stat()
                                        clips += 1
                                        size += st.st_size
                                        newest = max(newest, st.st_mtime)
                        except OSError:
                            pass
                        folders.append((entry.name, entry.path, clips, size, newest))
            except Exception as exc:
                error = exc
            folders.sort(key=lambda f: (-f[4], f[0].lower()))
            self._ui(lambda: self._render_recordings(folders, error, root_dir))

        threading.Thread(target=worker, daemon=True).start()

    def _render_recordings(self, folders, error, root_dir):
        for child in self._rec_list.winfo_children():
            child.destroy()
        if error is not None:
            self._empty_note(self._rec_list, f"Couldn't read {root_dir}\n{error}")
            return
        if not folders:
            self._empty_note(
                self._rec_list,
                f"No per-game folders in {root_dir} yet.\n\n"
                "Nebula creates one the first time it records a game.")
            return
        total = sum(f[3] for f in folders)
        self.bg.itemconfigure(
            self._rec_sub,
            text=f"{root_dir}   ·   {len(folders)} folders   ·   {_format_bytes(total)}")
        for name, path, clips, size, newest in folders:
            when = time.strftime("%d %b %Y", time.localtime(newest)) if newest else "—"
            self._list_row(
                self._rec_list, name,
                f"{clips} clip{'' if clips == 1 else 's'}   ·   {_format_bytes(size)}",
                when, command=lambda p=path: self._open_path(p))

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
    def _build_games(self):
        (x, y, w, h), sub = self._view_panel(
            "Known games", "What the classifier has learned to record.")
        self._games_sub = sub
        self._view_button(x + w - 136, y + 20, 116, "Game data",
                          self._open_game_data)
        self._view_button(x + w - 262, y + 20, 116, "↻  Rescan",
                          self._rescan_steam)
        self._games_list = self._scroll_list(x + 16, y + 74, w - 32, h - 90)

    def _refresh_games(self):
        for child in self._games_list.winfo_children():
            child.destroy()
        try:
            data = self.classifier._data
            games, non_games = data.get("games", {}), data.get("non_games", {})
        except Exception as exc:
            self._empty_note(self._games_list, f"Couldn't read the game list: {exc}")
            return

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

        self.bg.itemconfigure(
            self._games_sub,
            text=f"{len(by_name)} game{'' if len(by_name) == 1 else 's'} recorded automatically"
                 f"   ·   {len(non_games)} app{'' if len(non_games) == 1 else 's'} ignored")
        if not by_name:
            self._empty_note(
                self._games_list,
                "Nothing classified yet.\n\nHit Rescan to pull in your installed "
                "Steam library, or just launch a game — Nebula asks once and "
                "remembers the answer.")
            return
        for name in sorted(by_name, key=str.lower):
            entry = by_name[name]
            exes = ", ".join(sorted(entry["exes"])[:3])
            if len(entry["exes"]) > 3:
                exes += f"  +{len(entry['exes']) - 3} more"
            self._list_row(self._games_list, name, exes,
                           entry["source"] or "manual")

    # ---- Activity (full height) ----
    def _build_activity_view(self):
        (x, y, w, h), _ = self._view_panel(
            "Activity", "Everything Nebula has done this session.")
        box_x, box_y = x + 16, y + 74
        box_w, box_h = w - 32, h - 90
        plate = make_solid_tile(self._S(box_w), self._S(box_h), LOG_BG, radius=self._S(10))
        photo = to_photo(plate)
        self._images.append(photo)
        self.bg.create_image(box_x, box_y, anchor="nw", image=photo)
        self._composite.paste(plate, (self._S(box_x), self._S(box_y)), plate)
        self.console_full = ctk.CTkTextbox(
            self.root, state="disabled", wrap="word", fg_color=LOG_BG,
            corner_radius=0, bg_color=LOG_BG,
            font=ctk.CTkFont(family="Consolas", size=12), text_color=MUTED,
        )
        self.bg.create_window(box_x + 10, box_y + 10, anchor="nw",
                              window=self.console_full,
                              width=box_w - 20, height=box_h - 20)
        self._prepare_log_tags(self.console_full)
        # Replay anything logged before this view existed.
        for line in self._log_lines:
            self._append_log(self.console_full, line)

    # ---- Macropad ----
    def _build_macropad(self):
        (x, y, w, h), _ = self._view_panel(
            "Macropad", "Bind physical keys to Nebula actions.")
        self.bg.create_text(
            x + 20, y + 110, anchor="nw", width=w - 40,
            text="Not wired up yet.\n\n"
                 "The design pairs this with a custom HID macropad: bind keys to "
                 "start/stop, pause, mark clip and scene switches, with per-game "
                 "profiles that follow whatever you launch.\n\n"
                 "Nothing here is connected to hardware, so rather than show a "
                 "mock keypad that does nothing, this page is deliberately empty "
                 "until the binding layer exists.",
            fill=MUTED, font=("Segoe UI", 13))
        self.bg.create_text(
            x + 20, y + h - 60, anchor="nw",
            text=f"Meanwhile the global hotkey  {self.config.get('toggle_hotkey') or '—'}  "
                 "toggles monitoring from anywhere.",
            fill=FAINT, font=("Segoe UI", 12))

    # ---- Settings ----
    def _build_settings(self):
        (x, y, w, h), _ = self._view_panel(
            "Settings", "Read from config.json next to the executable.")
        self._view_button(x + w - 136, y + 20, 116, "Open config",
                          self._open_config_file)
        self._view_button(x + w - 262, y + 20, 116, "Open logs",
                          self._open_logs_folder)

        rows = [
            ("OBS", f"{self.config.get('obs_host')}:{self.config.get('obs_port')}"),
            ("OBS executable", self.config.get("obs_path") or "— not set —"),
            ("Recording root", self.config.get("recording_root") or "—"),
            ("Sync folder", self.config.get("sync_folder") or "— local only —"),
            ("Idle timeout", f"{self.config.get('idle_timeout_seconds')}s"),
            ("Minimum clip", f"{self.config.get('min_clip_seconds')}s"),
            ("Poll interval", f"{self.config.get('poll_interval_seconds')}s"),
            ("Toggle hotkey", self.config.get("toggle_hotkey") or "— none —"),
        ]
        row_y = y + 88
        for label, value in rows:
            self.bg.create_text(x + 24, row_y, anchor="w", text=label,
                                fill=FAINT, font=("Segoe UI", 12))
            self.bg.create_text(x + 210, row_y, anchor="w", text=str(value),
                                fill=TEXT_SOFT, font=("Consolas", 12),
                                width=w - 240)
            row_y += 34
        self.bg.create_text(
            x + 24, row_y + 16, anchor="nw", width=w - 48,
            text="Editing these in the app isn't implemented yet — change them in "
                 "config.json and restart. The idle timeout is the exception: the "
                 "dashboard slider writes it straight through.",
            fill=FAINT, font=("Segoe UI", 12))

    def _open_config_file(self):
        from .paths import APP_DIR
        self._open_path(os.path.join(APP_DIR, "config.json"))

    def _open_logs_folder(self):
        from .paths import APP_DIR
        self._open_path(os.path.join(APP_DIR, "logs"))

    # ---- hero recording card ----
    def _build_hero(self):
        x, y = self._content_x0(), 62
        w, h = WIDTH - MARGIN - x, 300
        self._status_card_geom = (x, y, w, h)   # reused by _flash_status_card
        self._status_card_item = self._glass(x, y, w, h, radius=18)

        pad = 24
        left_x = x + pad
        preview_w, preview_h = 372, 209
        preview_x = x + w - pad - preview_w
        preview_y = y + pad
        left_w = preview_x - 20 - left_x

        # --- status badge (state pill) ---
        self._hero_badge_geom = (left_x, y + 16, 120, 24)
        self._hero_badge_item = self._glass(left_x, y + 16, 120, 24, tint=ACCENT,
                                            radius=12, tint_alpha=40, border_alpha=0)
        self.rec_dot_id = self.bg.create_text(left_x + 15, y + 28, text="●",
                                              fill=ACCENT, font=("Segoe UI", 9))
        self._hero_badge_text = self.bg.create_text(left_x + 28, y + 28, anchor="w",
                                                    text="WATCHING", fill=ACCENT_LIGHT,
                                                    font=("Segoe UI", 10, "bold"))
        self._hero_sub_id = self.bg.create_text(left_x + 132, y + 28, anchor="w",
                                                text="", fill=MUTED, font=("Segoe UI", 12))

        # --- game name ---
        self.game_label_id = self.bg.create_text(
            left_x, y + 82, anchor="w", text="No game detected",
            fill=MUTED, font=("Segoe UI Semibold", 32),
        )

        # --- folder chip ---
        self._glass(left_x, y + 112, left_w, 30, tint=LOG_TINT, radius=9,
                    tint_alpha=170, border_hex=CARD_BORDER, border_alpha=24)
        self.bg.create_text(left_x + 12, y + 127, anchor="w", text="▸",
                            fill=ACCENT, font=("Segoe UI", 12))
        self.folder_label_id = self.bg.create_text(
            left_x + 28, y + 127, anchor="w", text=self.config["recording_root"],
            fill=MUTED, font=("Consolas", 11), width=left_w - 40,
        )

        # --- elapsed + size readouts ---
        self._elapsed_label_id = self.bg.create_text(
            left_x, y + 162, anchor="w", text="ELAPSED", fill=FAINT,
            font=("Segoe UI", 10, "bold"))
        self.timer_label_id = self.bg.create_text(
            left_x, y + 194, anchor="w", text="--:--:--", fill=TEXT,
            font=("Consolas", 40, "bold"))
        self._size_label_id = self.bg.create_text(
            left_x + 250, y + 162, anchor="w", text="SIZE", fill=FAINT,
            font=("Segoe UI", 10, "bold"))
        self.storage_label_id = self.bg.create_text(
            left_x + 250, y + 192, anchor="w", text="--", fill=TEXT_SOFT,
            font=("Consolas", 22))
        # Shown instead of the readout while nothing is being recorded, so the
        # card reads as calm-and-ready rather than simply empty.
        self._hero_hint_id = self.bg.create_text(
            left_x, y + 180, anchor="w", text="", fill=FAINT,
            font=("Segoe UI", 13), width=left_w)

        # --- transport buttons ---
        bt_y = y + h - pad - 40
        rec_bg = self._bg_at(left_x + 78, bt_y + 20)
        self.record_toggle_btn = ctk.CTkButton(
            self.root, text="●  Record now", command=self._toggle_record, state="disabled",
            fg_color=GREEN_TINT, hover_color=GREEN_TINT_HOVER, text_color=GREEN,
            bg_color=rec_bg, border_width=1, border_color=EDGE, corner_radius=11,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._record_btn_win = self.bg.create_window(
            left_x, bt_y, anchor="nw", window=self.record_toggle_btn, width=156, height=40)
        pause_bg = self._bg_at(left_x + 166 + 60, bt_y + 20)
        self.pause_btn = ctk.CTkButton(
            self.root, text="❚❚  Pause", command=self._toggle_pause,
            fg_color=AMBER_TINT, hover_color="#4A3A1A", text_color=AMBER_LIGHT,
            bg_color=pause_bg, border_width=1, border_color=EDGE, corner_radius=11,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._pause_btn_win = self.bg.create_window(
            left_x + 166, bt_y, anchor="nw", window=self.pause_btn, width=120, height=40)

        # --- scene preview + info row (right column) ---
        self._build_preview(preview_x, preview_y, preview_w, preview_h)
        self._glass(preview_x, preview_y + preview_h + 12, preview_w, 40,
                    tint=CARD_TINT, radius=11, tint_alpha=120,
                    border_hex=CARD_BORDER, border_alpha=26)
        self.bg.create_text(preview_x + 15, preview_y + preview_h + 32, anchor="w",
                            text="◆", fill=ACCENT, font=("Segoe UI", 12))
        self._preview_info_id = self.bg.create_text(
            preview_x + 33, preview_y + preview_h + 32, anchor="w",
            text="Scene capture idle", fill=TEXT_SOFT, font=("Segoe UI", 12))

        self._set_hero_state("offline")

    def _build_preview(self, x, y, w, h):
        """A stylised 16:9 'scene preview' tile - a violet gradient stand-in for
        the live capture (rendering real OBS frames is out of scope), with the
        source label and a little equaliser that comes alive while recording."""
        tile = self._make_preview_tile(w, h)
        photo = to_photo(tile)
        self._images.append(photo)
        self.bg.create_image(x, y, anchor="nw", image=photo)

        # Source label chip, top-left.
        self._glass(x + 12, y + 12, 168, 24, tint=BASE_BG, radius=8,
                    tint_alpha=150, border_alpha=0)
        self._preview_dot_id = self.bg.create_text(x + 22, y + 24, anchor="w", text="●",
                                                   fill=FAINT, font=("Segoe UI", 9))
        self.bg.create_text(x + 34, y + 24, anchor="w", text="Game Capture (Auto)",
                            fill=NAV_ACTIVE_TEXT, font=("Segoe UI", 10, "bold"))

        # Equaliser bars along the bottom - animated in _animate_hero.
        self._eq_bars = []
        n = 11
        bar_w = 5
        span = w - 28
        gap = (span - n * bar_w) / (n - 1)
        base_x = x + 14
        floor_y = y + h - 14
        for i in range(n):
            bx = base_x + i * (bar_w + gap)
            bar = self.bg.create_rectangle(bx, floor_y - 6, bx + bar_w, floor_y,
                                           fill="#EDEAFF", outline="")
            self._eq_bars.append((bar, bx, floor_y, bar_w))

    def _make_preview_tile(self, w, h):
        sw, sh = self._S(w), self._S(h)
        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for i in range(sh):
            col = _blend_hex("#2A1C4D", "#7C3AED", i / max(1, sh - 1))
            r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
            draw.line([(0, i), (sw, i)], fill=(r, g, b, 255))
        # Soft top-left light bloom for a touch of depth.
        bloom = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        ImageDraw.Draw(bloom).ellipse(
            [-sw * 0.2, -sh * 0.4, sw * 0.7, sh * 0.6], fill=(255, 255, 255, 26))
        img = Image.alpha_composite(img, bloom.filter(ImageFilter.GaussianBlur(self._S(30))))
        mask = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, sw - 1, sh - 1], radius=self._S(13), fill=255)
        img.putalpha(mask)
        return img

    def _animate_hero(self):
        """Drives the scene-preview equaliser: lively while recording, a low
        idle shimmer otherwise. One cheap timer, a handful of canvas updates."""
        if not self._visible:
            self.root.after(IDLE_TICK_MS, self._animate_hero)
            return
        t = self._anim_t
        active = self._is_recording and not self._is_paused
        for i, (bar, bx, floor_y, bar_w) in enumerate(self._eq_bars):
            if active:
                level = (math.sin(t * 3.2 + i * 0.7) + 1) / 2
                height = 4 + level * 26
            else:
                height = 3 + (math.sin(t * 0.9 + i * 0.5) + 1) * 1.5
            self.bg.coords(bar, bx, floor_y - height, bx + bar_w, floor_y)
        self.root.after(90, self._animate_hero)

    def _set_hero_state(self, state):
        """Recolours the whole hero card for one of: offline / watching /
        recording / paused. Timer + size text are filled in by
        _poll_obs_status; this owns the badge, subtitle, border and buttons."""
        self._hero_state = state
        spec = {
            "offline":   (RED,    RED_LIGHT,    "OFFLINE",   "OBS not connected"),
            "watching":  (ACCENT, ACCENT_LIGHT, "WATCHING",  "Monitoring · auto-records on launch"),
            "recording": (RED,    RED_LIGHT,    "REC",       "Now recording · auto-detected"),
            "paused":    (AMBER,  AMBER_LIGHT,  "PAUSED",    "Idle — auto-paused, resumes on input"),
        }[state]
        base, light, badge_text, sub = spec
        bx, by, bw, bh = self._hero_badge_geom
        self._regen_glass(self._hero_badge_item, bx, by, bw, bh, tint=base,
                          radius=12, tint_alpha=40, border_alpha=0)
        self.bg.itemconfigure(self._hero_badge_text, text=badge_text, fill=light)
        self.bg.itemconfigure(self.rec_dot_id, fill=base)
        self.bg.itemconfigure(self._hero_sub_id, text=sub)

        # Card border tint follows the state (calm violet vs. hot red/amber).
        hx, hy, hw, hh = self._status_card_geom
        border = {"offline": RED, "watching": CARD_BORDER, "recording": RED,
                  "paused": AMBER}[state]
        self._regen_glass(self._status_card_item, hx, hy, hw, hh, radius=18,
                          border_hex=border, border_alpha=70)

        # Timer / size only carry meaning while a recording exists.
        show_readout = state in ("recording", "paused")
        for item in (self._elapsed_label_id, self._size_label_id,
                     self.timer_label_id, self.storage_label_id):
            self.bg.itemconfigure(item, state="normal" if show_readout else "hidden")
        self.bg.itemconfigure(self.timer_label_id,
                              fill=AMBER_LIGHT if state == "paused" else TEXT)
        self.bg.itemconfigure(
            self._hero_hint_id,
            state="hidden" if show_readout else "normal",
            text="" if show_readout else (
                "Start monitoring to connect to OBS and watch for a game."
                if state == "offline" else
                "Standing by — recording starts by itself the moment a game launches."
            ),
        )

        # Scene-preview caption follows the capture, so the right column isn't
        # claiming "idle" while a recording is plainly running.
        if state == "recording":
            info = f"Game Capture → {self._current_game}" if self._current_game else "Capturing"
        elif state == "paused":
            info = "Capture held — paused"
        elif state == "watching":
            info = "Scene capture idle"
        else:
            info = "No scene — OBS offline"
        self.bg.itemconfigure(self._preview_info_id, text=info)
        self.bg.itemconfigure(self._preview_dot_id,
                              fill=RED if state == "recording" else
                              (AMBER if state == "paused" else FAINT))

        # Buttons: primary record/stop always shown; pause only mid-recording.
        self.bg.itemconfigure(self._pause_btn_win,
                              state="normal" if show_readout else "hidden")
        if state == "paused":
            self.pause_btn.configure(text="▶  Resume")
        else:
            self.pause_btn.configure(text="❚❚  Pause")

    # ---- stat tiles ----
    def _build_stats(self):
        x0, y = self._content_x0(), 380
        total_w = WIDTH - MARGIN - x0
        gap = 14
        tw = (total_w - gap * 3) / 4
        h = 92

        def tile(i):
            return x0 + i * (tw + gap)

        # 1) Today's clips (filled in by _poll_disk_stats)
        self._stat_tile(tile(0), y, tw, h, "▤", ACCENT, "Today")
        self._stat_today_val = self.bg.create_text(
            tile(0) + 16, y + 48, anchor="w", text="–", fill=TEXT,
            font=("Segoe UI Semibold", 22))
        self._stat_today_sub = self.bg.create_text(
            tile(0) + 16, y + 72, anchor="w", text="scanning…", fill=MUTED,
            font=("Segoe UI", 12))

        # 2) Disk free
        self._stat_tile(tile(1), y, tw, h, "▥", TEAL, "Disk free")
        self._stat_disk_val = self.bg.create_text(
            tile(1) + 16, y + 48, anchor="w", text="–", fill=TEXT,
            font=("Segoe UI Semibold", 22))
        self._stat_disk_sub = self.bg.create_text(
            tile(1) + 16, y + 72, anchor="w", text="", fill=MUTED,
            font=("Segoe UI", 12))

        # 3) Idle timeout - value + live slider (keeps the old control alive)
        self._stat_tile(tile(2), y, tw, h, "◔", AMBER, "Idle timeout")
        self.timeout_value_id = self.bg.create_text(
            tile(2) + 16, y + 48, anchor="w",
            text=f"{self.config['idle_timeout_seconds']}s", fill=TEXT,
            font=("Segoe UI Semibold", 22))
        slider_bg = self._bg_at(tile(2) + tw / 2, y + 74)
        slider = ctk.CTkSlider(
            self.root, from_=1, to=60, number_of_steps=59, command=self._on_timeout_change,
            fg_color=SURFACE, progress_color=AMBER, button_color=AMBER,
            button_hover_color=AMBER_LIGHT, bg_color=slider_bg, height=14,
        )
        slider.set(self.config["idle_timeout_seconds"])
        self.bg.create_window(tile(2) + 16, y + 68, anchor="w", window=slider,
                              width=int(tw - 32), height=14)

        # 4) Sync target
        self._stat_tile(tile(3), y, tw, h, "⟳", BLUE, "Sync")
        sync = self.config.get("sync_folder") or ""
        sync_val = "OneDrive" if "onedrive" in sync.lower() else (
            os.path.basename(sync.rstrip("/\\")) or "Local")
        self.bg.create_text(tile(3) + 16, y + 48, anchor="w", text=sync_val,
                            fill=TEXT, font=("Segoe UI Semibold", 22))
        self.bg.create_text(tile(3) + 16, y + 72, anchor="w",
                            text="synced" if sync else "local only", fill=MUTED,
                            font=("Segoe UI", 12))

    def _stat_tile(self, x, y, w, h, glyph, color, label):
        self._glass(x, y, w, h, tint=CARD_TINT, radius=14, tint_alpha=120,
                    border_hex=CARD_BORDER, border_alpha=26)
        self.bg.create_text(x + 16, y + 20, anchor="w", text=glyph, fill=color,
                            font=("Segoe UI Symbol", 14))
        self.bg.create_text(x + 36, y + 20, anchor="w", text=label, fill=FAINT,
                            font=("Segoe UI", 11))

    # ---- activity log ----
    def _build_activity(self):
        x0, y = self._content_x0(), 490
        w = WIDTH - MARGIN - x0
        self.bg.create_text(x0, y, anchor="nw", text="ACTIVITY", fill=FAINT,
                            font=("Segoe UI", 10, "bold"))
        y += 22
        panel_h = HEIGHT - MARGIN - y
        self._glass(x0, y, w, panel_h, tint=LOG_TINT, radius=14, tint_alpha=195)

        # Rounded plate + a flat square textbox inset inside it (see the note in
        # the old build - a tall widget can't match a sheen gradient's corners).
        box_x, box_y = x0 + 10, y + 10
        box_w, box_h = w - 20, panel_h - 20
        box_r = 10
        backing = make_solid_tile(self._S(box_w), self._S(box_h), LOG_BG, radius=self._S(box_r))
        backing_photo = to_photo(backing)
        self._images.append(backing_photo)
        self.bg.create_image(box_x, box_y, anchor="nw", image=backing_photo)
        self._composite.paste(backing, (self._S(box_x), self._S(box_y)), backing)

        self.console = ctk.CTkTextbox(
            self.root, state="disabled", wrap="word", fg_color=LOG_BG, corner_radius=0,
            bg_color=LOG_BG,
            font=ctk.CTkFont(family="Consolas", size=11), text_color=MUTED,
        )
        self.bg.create_window(box_x + box_r, box_y + box_r, anchor="nw", window=self.console,
                              width=box_w - box_r * 2, height=box_h - box_r * 2)
        self._prepare_log_tags(self.console)

    # ---- disk / clip stats ----
    def _poll_disk_stats(self):
        """Fill the Today + Disk-free tiles from the real recording folder,
        off the Tk thread (a recursive scan + disk query can be slow)."""
        root_dir = self.config.get("recording_root", "")

        def worker():
            free_txt, drive = "", ""
            try:
                usage = shutil.disk_usage(root_dir if os.path.isdir(root_dir) else os.path.expanduser("~"))
                free_txt = _format_bytes(usage.free)
                drive = os.path.splitdrive(os.path.abspath(root_dir))[0] or ""
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
                self.root.after(0, lambda: self._apply_disk_stats(clips, total, free_txt, drive))
            except RuntimeError:
                pass  # window torn down while the scan was still running

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(300000, self._poll_disk_stats)  # 5 min; it's a slow-moving stat

    def _apply_disk_stats(self, clips, total, free_txt, drive):
        self.bg.itemconfigure(self._stat_today_val,
                              text=f"{clips} clip" + ("" if clips == 1 else "s"))
        self.bg.itemconfigure(self._stat_today_sub,
                              text=f"{_format_bytes(total)} recorded" if clips else "nothing yet")
        if free_txt:
            self.bg.itemconfigure(self._stat_disk_val, text=free_txt)
            self.bg.itemconfigure(self._stat_disk_sub, text=f"on {drive}" if drive else "free")

    # ---- sidebar status updaters ----
    def _set_obs_status(self, text, color):
        """Update the sidebar OBS card (replaces the old OBS status pill)."""
        light = {RED: RED_LIGHT, GREEN: GREEN_LIGHT, AMBER: AMBER_LIGHT}.get(color, color)
        self.bg.itemconfigure(self._obs_card_dot, fill=color)
        self.bg.itemconfigure(self._obs_card_title, text=f"OBS {text.lower()}", fill=light)

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
        # Kept so the Activity view can replay history when it's first shown,
        # and bounded so a long session can't grow this without limit.
        self._log_lines.append(message)
        if len(self._log_lines) > LOG_HISTORY:
            del self._log_lines[:-LOG_HISTORY]
        for box in (self.console, getattr(self, "console_full", None)):
            if box is not None:
                self._append_log(box, message)

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

    def _append_log(self, box, message):
        box.configure(state="normal")
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
        box.see("end")
        box.configure(state="disabled")

    # ---- recording indicator (pulsing dot + elapsed timer + live storage) ----
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
                    self.bg.itemconfigure(self.timer_label_id, text=f"{hh:02d}:{mm:02d}:{ss:02d}")
                    self.bg.itemconfigure(self.storage_label_id, text=_format_bytes(status.get("outputBytes", 0)))
            except OBSError:
                pass

        was_paused = self._is_paused
        self._is_paused = is_paused
        if is_recording and (not self._is_recording or was_paused) and not is_paused:
            self._pulse_dot(True)  # just started, or just resumed from pause
        self._is_recording = is_recording

        # The hero card owns the badge/border/readout visibility; pick the state
        # that matches what OBS and the monitor are actually doing right now.
        if not self.obs.connected:
            state = "offline"
        elif is_recording and is_paused:
            state = "paused"
        elif is_recording:
            state = "recording"
        else:
            state = "watching"
        if state != self._hero_state:
            self._set_hero_state(state)

        self.record_toggle_btn.configure(state="normal" if self.obs.connected else "disabled")
        if is_recording:
            self.record_toggle_btn.configure(
                text="■  Stop recording", fg_color=RED_TINT, hover_color=RED_TINT_HOVER, text_color=RED,
            )
        else:
            self.record_toggle_btn.configure(
                text="●  Record now", fg_color=GREEN_TINT, hover_color=GREEN_TINT_HOVER, text_color=GREEN,
            )

        # A second is right when you're watching the timer tick; while hidden in
        # the tray nothing renders it, so back off. The monitor thread drives the
        # actual recording independently of this poll.
        self.root.after(1000 if self._visible else 5000, self._poll_obs_status)

    def _pulse_dot(self, bright=True):
        if not self._is_recording:
            self.bg.itemconfigure(self.rec_dot_id, fill=FAINT)
            return
        if self._is_paused:
            self.bg.itemconfigure(self.rec_dot_id, fill=AMBER)
            return
        self.bg.itemconfigure(self.rec_dot_id, fill=(RED if bright else RED_DIM))
        self.root.after(650, lambda: self._pulse_dot(not bright))

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
        border = {"offline": RED, "watching": CARD_BORDER, "recording": RED,
                  "paused": AMBER}.get(self._hero_state, CARD_BORDER)

        def step(i=0):
            if i >= len(steps):
                # Settle back on the border the current hero state owns, not the
                # generic default - otherwise a flash would wash out the state tint.
                self._regen_glass(self._status_card_item, x, y, w, h, radius=18,
                                  border_hex=border, border_alpha=70)
                return
            border_alpha = int(70 + (230 - 70) * steps[i])
            self._regen_glass(self._status_card_item, x, y, w, h, radius=18,
                              border_hex=border, border_alpha=min(border_alpha, 255))
            self.root.after(110, lambda: step(i + 1))

        step()

    # ---- notifications ----
    def _show_notification(self, event, display_name, details=None):
        """A small, silent, borderless popup that slides in from the bottom
        right edge and slides back out - deliberately not the native Windows
        toast, which the user wanted to avoid (system notification sound +
        generic styling, plus a plain fade felt static compared to a modern
        slide-in). A thin countdown line along the bottom shows how long it
        will stay; hovering pauses the countdown and reveals final
        duration/size (for "stop" events) so there's time to actually read
        it. Called from the monitor's background thread, so everything
        Tk-related is marshalled onto the main thread."""
        def build():
            if self._notification is not None:
                try:
                    self._notification.destroy()
                except Exception:
                    pass
                self._notification = None

            width, height = 336, 88          # base design units (drawing coords)
            sw, sh = self._S(width), self._S(height)  # physical popup size in px
            popup = ctk.CTkToplevel(self.root)
            popup.overrideredirect(True)
            popup.attributes("-topmost", True)
            popup.attributes("-alpha", 0.0)  # fade in alongside the slide

            end_x = popup.winfo_screenwidth() - sw - 20
            start_x = popup.winfo_screenwidth() + 10
            y = popup.winfo_screenheight() - sh - 60
            popup.geometry(f"{sw}x{sh}+{start_x}+{y}")
            apply_rounded_corners(popup)

            canvas = ScaledCanvas(
                tk.Canvas(popup, width=sw, height=sh, highlightthickness=0, bd=0),
                self.scale,
            )
            canvas.pack(fill="both", expand=True)
            crop = self.nebula.crop((0, 0, sw, sh)) if self.nebula.size[0] >= sw and self.nebula.size[1] >= sh else self.nebula.resize((sw, sh))
            photo = to_photo(crop)
            self._images.append(photo)
            canvas.create_image(0, 0, anchor="nw", image=photo)
            tile = make_glass_tile(sw, sh, CARD_TINT, tint_alpha=215, radius=self._S(16), border_hex=CARD_BORDER, border_alpha=80)
            tile_photo = to_photo(tile)
            self._images.append(tile_photo)
            canvas.create_image(0, 0, anchor="nw", image=tile_photo)

            accent_colors = {"start": GREEN, "stop": ACCENT, "pause": AMBER, "resume": GREEN}
            glyphs = {"start": "▶", "stop": "■", "pause": "●", "resume": "▶"}
            titles = {
                "start": "Recording started", "stop": "Recording stopped",
                "pause": "Recording paused", "resume": "Recording resumed",
            }
            accent = accent_colors.get(event, ACCENT)

            # Leading icon chip: the event glyph inside a tinted circle, the
            # same badge language as the status pills.
            canvas.create_oval(16, 20, 48, 52, fill=_tint_for(accent), outline="")
            canvas.create_text(32, 36, text=glyphs.get(event, "●"), fill=accent, font=("Segoe UI", 11))

            canvas.create_text(60, 28, anchor="w", text=titles.get(event, event), fill=TEXT, font=("Segoe UI Semibold", 12))
            canvas.create_text(60, 48, anchor="w", text=display_name, fill=MUTED, font=("Segoe UI", 12))

            detail_parts = []
            if details:
                duration = details.get("duration")
                if duration is not None:
                    mm, ss = divmod(int(duration), 60)
                    detail_parts.append(f"{mm:02d}:{ss:02d}")
                size = details.get("size")
                if size is not None:
                    detail_parts.append(_format_bytes(size))
            detail_id = None
            if detail_parts:
                detail_id = canvas.create_text(
                    60, 67, anchor="w", text="  ·  ".join(detail_parts), fill=FAINT, font=("Segoe UI", 11),
                )
                canvas.itemconfigure(detail_id, state="hidden")

            # Inset countdown line along the bottom - a faint full track with
            # the accent fill draining left as time runs out; freezes while
            # hovered so there's no rush to read.
            lifetime_ms = 4000
            track_x0, track_x1 = 16, width - 16
            canvas.create_rectangle(track_x0, height - 8, track_x1, height - 6, fill=EDGE, outline="")
            countdown_id = canvas.create_rectangle(track_x0, height - 8, track_x1, height - 6, fill=accent, outline="")

            self._notification = popup
            hovering = {"value": False}
            remaining = {"ms": lifetime_ms}

            def set_alpha(a):
                try:
                    popup.attributes("-alpha", max(0.0, min(a, 1.0)))
                except Exception:
                    pass

            def slide(x, target, on_done=None, fade_from=None, fade_to=None):
                total = abs(target - x) or 1

                def step(cx):
                    remaining_px = target - cx
                    if fade_from is not None:
                        progress = 1 - abs(remaining_px) / total
                        set_alpha(fade_from + (fade_to - fade_from) * progress)
                    if abs(remaining_px) <= 4:
                        popup.geometry(f"{sw}x{sh}+{target}+{y}")
                        if fade_to is not None:
                            set_alpha(fade_to)
                        if on_done:
                            on_done()
                        return
                    cx = cx + int(remaining_px * 0.3)
                    try:
                        popup.geometry(f"{sw}x{sh}+{cx}+{y}")
                    except Exception:
                        return
                    popup.after(12, lambda: step(cx))

                step(x)

            def dismiss():
                def finish():
                    popup.destroy()
                    if self._notification is popup:
                        self._notification = None
                slide(end_x, start_x, finish, fade_from=1.0, fade_to=0.0)

            def tick():
                if not hovering["value"]:
                    remaining["ms"] -= 50
                if remaining["ms"] <= 0:
                    dismiss()
                    return
                try:
                    fill_x1 = track_x0 + (track_x1 - track_x0) * remaining["ms"] / lifetime_ms
                    canvas.coords(countdown_id, track_x0, height - 8, fill_x1, height - 6)
                except Exception:
                    return
                popup.after(50, tick)

            def on_enter(_event):
                hovering["value"] = True
                if detail_id is not None:
                    canvas.itemconfigure(detail_id, state="normal")

            def on_leave(_event):
                hovering["value"] = False
                if detail_id is not None:
                    canvas.itemconfigure(detail_id, state="hidden")

            canvas.bind("<Enter>", on_enter)
            canvas.bind("<Leave>", on_leave)

            slide(start_x, end_x, fade_from=0.0, fade_to=1.0)
            popup.after(50, tick)

        self.root.after(0, build)

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
                # Refresh the hero in place so the scene caption picks up the
                # new title (the state itself is unchanged, so this is a no-op
                # visually apart from that caption).
                self._set_hero_state(self._hero_state)
                self._flash_status_card()
                # The timer/storage/pulsing dot are driven by _poll_obs_status
                # from OBS's own GetRecordStatus, not from this event - that
                # way they reflect whether OBS is *actually* recording, not
                # just whether the monitor decided a game should be recorded.
            if "folder" in kwargs:
                self.bg.itemconfigure(self.folder_label_id, text=kwargs["folder"] or self.config["recording_root"])
            if "idle" in kwargs:
                # Idle no longer has its own pill - it reads as the hero card's
                # "PAUSED" state, which _poll_obs_status derives from OBS itself.
                self._tray_idle = kwargs["idle"]
            self._update_tray_tooltip()
        self.root.after(0, apply)

    def _update_tray_tooltip(self):
        if not self.tray_icon:
            return
        if self._tray_game:
            text = f"Recording: {self._tray_game}"
        elif self._tray_idle:
            text = "Nebula - idle"
        else:
            text = "Nebula - watching for a game"
        try:
            self.tray_icon.title = text[:127]  # Windows tray tooltip length limit
        except Exception:
            pass

    def _on_timeout_change(self, value):
        self.config["idle_timeout_seconds"] = int(value)
        self.bg.itemconfigure(self.timeout_value_id, text=f"{int(value)}s")
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
        self._set_obs_status("Connected", GREEN)
        self._set_monitoring(True)
        self.monitor.start()

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
            try:
                ensure_obs_running(self.config.get("obs_path"), log=self._log)
                self.obs.connect()
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
            self._ui(self._connect_succeeded)

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
        self._log(f"[Monitor] OBS not available yet ({error}); retrying in 10s...")
        self._set_obs_status("Disconnected", RED)
        self.root.after(10000, self.autostart)

    def _connect_succeeded(self):
        if self._abort_connect:
            # Monitoring was stopped while this attempt was still in flight -
            # don't quietly restart it behind the user's back.
            self.obs.disconnect()
            self._set_obs_status("Disconnected", RED)
            return
        self._on_connected()
        self._log("[Monitor] Auto-started.")

    def _on_connection_change(self, connected):
        self.root.after(0, lambda: self._set_obs_status(
            *(("Connected", GREEN) if connected else ("Reconnecting...", RED))
        ))

    def _stop(self):
        self._abort_connect = True  # cancel any connect attempt still in flight
        self.monitor.stop()
        self.obs.disconnect()
        self._set_obs_status("Disconnected", RED)
        self._set_monitoring(False)
        self._set_hero_state("offline")

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
                self.root.after(0, lambda: self._log(
                    f"[Steam] Rescan complete - {len(registered)} game(s) registered."
                ))
            except Exception as exc:
                # Same late-binding trap as the connect worker: `exc` is gone by
                # the time Tk runs this callback, so capture it in a local.
                error = exc
                self.root.after(0, lambda: self._log(f"[Steam] Rescan failed: {error}"))
            finally:
                self._scanning = False
                self.root.after(0, lambda: self.rescan_btn.configure(state="normal", text="↻  Rescan"))

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
            font=("Segoe UI Semibold", 15), width=380, justify="center",
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
            font=("Segoe UI", 12), width=380, justify="center",
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
            fill=TEXT, font=("Segoe UI", 13),
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
        # Only meaningful while the window is mapped - a withdrawn window has no
        # taskbar button or Alt-Tab entry to animate, so this was ~12 icon swaps
        # a second painting something that wasn't on screen. The tray icon has
        # its own animation thread and is unaffected.
        if not self._visible:
            self.root.after(IDLE_TICK_MS, self._animate_taskbar_icon)
            return
        try:
            self.root.iconphoto(False, self._taskbar_icon_frames[self._taskbar_icon_index % len(self._taskbar_icon_frames)])
        except Exception:
            pass
        self._taskbar_icon_index += 1
        self.root.after(ACTIVE_TICK_MS, self._animate_taskbar_icon)

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
