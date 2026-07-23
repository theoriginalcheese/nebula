import ctypes
import math
import os
import random
import re
import threading
import tkinter as tk
import tkinter.messagebox

import customtkinter as ctk
from PIL import Image

from . import classifier as classifier_module
from .obs_client import OBSClient, OBSError
from .monitor import Monitor, ensure_obs_running
from .app_log import log_to_file
from .theme_art import (
    generate_nebula, make_accent_glow, make_glass_tile, make_solid_tile, to_photo,
)
from .icon_art import generate_animation_frames
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
GREEN = "#3DDC84"
GREEN_TINT = "#14382B"
GREEN_TINT_HOVER = "#1B4A38"
GREEN_HOVER = GREEN_TINT_HOVER  # legacy alias
RED = "#FF5C7A"
RED_TINT = "#3B1D2A"
RED_TINT_HOVER = "#4C2434"
RED_HOVER = RED_TINT_HOVER  # legacy alias
RED_DIM = "#5A2836"
AMBER = "#F5A623"
AMBER_TINT = "#3A2D14"
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

WIDTH, HEIGHT = 860, 660
TITLEBAR_HEIGHT = 44
MARGIN = 24

# ---- living backdrop tuning (all in base design units) ----
DRIFT = 14          # how far the nebula may wander; it's rendered this much
                    # larger on every side so an edge is never exposed
GLOW_SIZE = 460     # diameter of the drifting violet accent bloom
STAR_COUNT = 22
STAR_DIM = "#2E2A52"    # star colour at the bottom of its twinkle
STAR_BRIGHT = "#D9D4FF"  # ...and at the top


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


class Pill(ctk.CTkLabel):
    """A small rounded status badge - dark tint of the status color as the
    fill with the bright color as text (the calm 'badge' look, not a loud
    solid chip) - that crossfades between states instead of snapping."""

    def __init__(self, master, text, color, width=88, bg_color=CARD_SURFACE):
        super().__init__(
            master, text=f"●  {text}", text_color=color, fg_color=_tint_for(color),
            bg_color=bg_color, corner_radius=11, width=width, height=22,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self._current_color = color

    def set(self, text, color, steps=8, delay=20):
        self.configure(text=f"●  {text}")
        if color == self._current_color:
            return
        start = self._current_color
        start_tint, end_tint = _tint_for(start), _tint_for(color)

        def step(i=0):
            t = i / steps
            self.configure(
                fg_color=_blend_hex(start_tint, end_tint, t),
                text_color=_blend_hex(start, color, t),
            )
            if i < steps:
                self.after(delay, lambda: step(i + 1))
            else:
                self._current_color = color

        step()


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
        self._dragging = False
        self._scanning = False

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

        self._build_titlebar()
        self._build_status_card()
        self._build_controls()
        self._build_log()
        self._build_idle_row()

        self._poll_manual_review()
        self._poll_obs_status()
        self._register_hotkey()
        self._animate_backdrop()

    def _S(self, v):
        """Scale a base design-unit value to physical pixels by the UI scale."""
        return int(round(v * self.scale))

    def _animate_backdrop(self):
        """Drives the whole living backdrop from one timer: the nebula drifts on
        a slow lissajous, the violet bloom wanders on a wider/slower path and
        breathes, and the stars twinkle. Deliberately ~12fps with only a couple
        of dozen canvas updates per tick, so it stays visually alive while
        costing next to nothing during a recording session."""
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

        for star, phase, speed in self._stars:
            level = (math.sin(t * speed + phase) + 1) / 2
            self.bg.itemconfigure(star, fill=_blend_hex(STAR_DIM, STAR_BRIGHT, level))

        self._anim_t = t + 0.085
        self.root.after(80, self._animate_backdrop)

    def _item_right_base(self, item_id, fallback_base):
        """Right edge of a canvas item in BASE design units (bbox is in real
        px, so divide back out the UI scale). Lets neighbouring elements be
        placed just past real, measured text width - so nothing overlaps no
        matter the font metrics, UI scale, or how long the text is. Falls back
        to a fixed offset if the item isn't measurable yet."""
        try:
            bbox = self.bg.bbox(item_id)
            if bbox:
                return bbox[2] / self.scale
        except Exception:
            pass
        return fallback_base

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
        flash) without creating a duplicate canvas item."""
        tile = make_glass_tile(
            self._S(w), self._S(h), tint, tint_alpha=tint_alpha, radius=self._S(radius),
            border_hex=border_hex or CARD_BORDER, border_alpha=border_alpha,
        )
        photo = to_photo(tile)
        self._images.append(photo)
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

    def _build_titlebar(self):
        cy = TITLEBAR_HEIGHT / 2
        title_id = self.bg.create_text(
            MARGIN, cy, anchor="w", text="Nebula",
            fill=TEXT, font=("Segoe UI Semibold", 13),
        )
        # Subtitle sits just past the wordmark - measured, not a fixed offset,
        # so the "·" separator keeps a clean gap at any font metric or scale.
        self.bg.create_text(
            self._item_right_base(title_id, MARGIN + 62) + 16, cy, anchor="w",
            text="·   auto-record by game, auto-sorted by folder",
            fill=FAINT, font=("Segoe UI", 11),
        )

        # Window controls pinned to the right edge.
        self._make_circle_button(WIDTH - 28, cy, 13, SURFACE, RED, "✕", self._hide)
        self._make_circle_button(WIDTH - 62, cy, 13, SURFACE, SURFACE_HOVER, "−", self._hide)

        # Discoverable hotkey hint (keycap + "toggle"), packed to the left of
        # the window controls and sized to the binding text - so a short "F6"
        # or a long "ALT GR" both sit cleanly without overlapping anything.
        binding = self.config.get("toggle_hotkey")
        if binding:
            label = binding.upper()
            keycap_w = 2 * (5 + len(label) * 4)      # mirrors _draw_keycap's width
            keycap_cx = (WIDTH - 84) - keycap_w / 2  # right edge clears the − button
            self._draw_keycap(keycap_cx, cy, label)
            self.bg.create_text(
                keycap_cx - keycap_w / 2 - 12, cy, anchor="e", text="toggle",
                fill=FAINT, font=("Segoe UI", 10),
            )

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

    def _build_status_card(self):
        # Everything here is either a canvas-native text/item (blends
        # seamlessly with the glass tile behind it, and can be recolored/
        # retexted live via itemconfigure) or a genuinely opaque widget
        # (the status Pills and record button, which are meant to look like
        # solid controls, not glass) - no "transparent" CTkFrame wrappers,
        # which don't actually composite against arbitrary canvas art.
        x, y, w, h = MARGIN, 60, WIDTH - MARGIN * 2, 142
        self._status_card_geom = (x, y, w, h)
        self._status_card_item = self._glass(x, y, w, h)

        # OBS + IDLE flow left-to-right, each pill measured to sit just past
        # its label, and the IDLE group placed just past the OBS pill - so the
        # labels never disappear behind the pills at any font width or scale.
        LABEL_GAP, GROUP_GAP = 12, 28
        OBS_PILL_W, IDLE_PILL_W = 140, 84  # OBS wide enough for "Reconnecting..."

        obs_label = self.bg.create_text(x + 20, y + 26, anchor="w", text="OBS", fill=FAINT, font=("Segoe UI", 10, "bold"))
        obs_pill_x = self._item_right_base(obs_label, x + 44) + LABEL_GAP
        obs_bg = self._bg_at(obs_pill_x + OBS_PILL_W / 2, y + 26)
        self.obs_pill = Pill(self.root, "Disconnected", RED, width=OBS_PILL_W, bg_color=obs_bg)
        self.bg.create_window(obs_pill_x, y + 15, anchor="nw", window=self.obs_pill, width=OBS_PILL_W, height=22)

        idle_label_x = obs_pill_x + OBS_PILL_W + GROUP_GAP
        idle_label = self.bg.create_text(idle_label_x, y + 26, anchor="w", text="IDLE", fill=FAINT, font=("Segoe UI", 10, "bold"))
        idle_pill_x = self._item_right_base(idle_label, idle_label_x + 34) + LABEL_GAP
        idle_bg = self._bg_at(idle_pill_x + IDLE_PILL_W / 2, y + 26)
        self.idle_pill = Pill(self.root, "No", GREEN, width=IDLE_PILL_W, bg_color=idle_bg)
        self.bg.create_window(idle_pill_x, y + 15, anchor="nw", window=self.idle_pill, width=IDLE_PILL_W, height=22)

        # Manual override - independent of auto-detection, so recording can
        # be started/stopped directly regardless of whether a game is
        # currently being monitored.
        rec_bg = self._bg_at(x + w - 90, y + 26)
        self.record_toggle_btn = ctk.CTkButton(
            self.root, text="●  Record now", command=self._toggle_record, state="disabled",
            fg_color=GREEN_TINT, hover_color=GREEN_TINT_HOVER, text_color=GREEN,
            bg_color=rec_bg,
            border_width=1, border_color=EDGE, corner_radius=13,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.bg.create_window(x + w - 160, y + 13, anchor="nw", window=self.record_toggle_btn, width=140, height=26)

        self.rec_dot_id = self.bg.create_text(x + 20, y + 74, anchor="w", text="●", fill=FAINT, font=("Segoe UI", 16))
        self.game_label_id = self.bg.create_text(
            x + 42, y + 74, anchor="w", text="No game detected", fill=MUTED, font=("Segoe UI Semibold", 20),
        )
        self.timer_label_id = self.bg.create_text(
            x + 42, y + 102, anchor="w", text="", fill=FAINT, font=("Consolas", 12),
        )
        self.storage_label_id = self.bg.create_text(
            x + 116, y + 102, anchor="w", text="", fill=FAINT, font=("Consolas", 12),
        )

        self.folder_label_id = self.bg.create_text(
            x + 20, y + h - 18, anchor="w", text=self.config["recording_root"],
            fill=FAINT, font=("Segoe UI", 11), width=w - 40,
        )

    def _build_controls(self):
        y = 218
        x = MARGIN
        gap = 12

        def make_button(width, **kwargs):
            nonlocal x
            bg = self._bg_at(x + width / 2, y + 18)
            button = ctk.CTkButton(
                self.root, bg_color=bg,
                border_width=1, border_color=EDGE, corner_radius=10, **kwargs,
            )
            self.bg.create_window(x, y, anchor="nw", window=button, width=width, height=36)
            x += width + gap
            return button

        self.start_btn = make_button(
            164, text="▶  Start monitoring", command=self._start,
            fg_color=GREEN_TINT, hover_color=GREEN_TINT_HOVER, text_color=GREEN,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.stop_btn = make_button(
            164, text="■  Stop monitoring", command=self._stop, state="disabled",
            fg_color=RED_TINT, hover_color=RED_TINT_HOVER, text_color=RED,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.rescan_btn = make_button(
            186, text="⟳  Rescan Steam games", command=self._rescan_steam,
            fg_color=SURFACE, hover_color=SURFACE_HOVER, text_color=MUTED,
            font=ctk.CTkFont(size=12),
        )
        make_button(
            150, text="Open game data", command=self._open_game_data,
            fg_color=SURFACE, hover_color=SURFACE_HOVER, text_color=MUTED,
            font=ctk.CTkFont(size=12),
        )

    def _build_log(self):
        y = 272
        self.bg.create_text(
            MARGIN, y, anchor="nw", text="ACTIVITY", fill=FAINT, font=("Segoe UI", 10, "bold"),
        )
        y += 22

        log_height = HEIGHT - y - 64
        self._glass(MARGIN, y, WIDTH - MARGIN * 2, log_height, tint=LOG_TINT, tint_alpha=195)

        # The text area is the one widget tall enough to span the panel's whole
        # sheen gradient, so no single bg_color could match its top AND bottom
        # corners - that's what showed up as a square fringe inside the rounded
        # panel. Draw the rounded shape on the canvas instead and inset a flat,
        # square textbox inside it: the rounding is the tile's, and the widget
        # (same colour, corner_radius 0) never paints a corner cut-away at all.
        box_x, box_y = MARGIN + 10, y + 9
        box_w, box_h = WIDTH - MARGIN * 2 - 20, log_height - 18
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
        # Color-code the [Subsystem] prefix of each log line + give lines
        # some breathing room. Reaches into CTkTextbox's underlying tk.Text
        # (private but stable across ctk 5.x) since CTkTextbox doesn't proxy
        # tag configuration - guarded so a ctk update can't crash the app.
        try:
            tb = self.console._textbox
            for tag, color in LOG_TAG_COLORS.items():
                tb.tag_config(f"t_{tag}", foreground=color)
            tb.configure(spacing1=2, spacing3=2)
        except Exception:
            pass

    def _build_idle_row(self):
        y = HEIGHT - 44
        label_id = self.bg.create_text(
            MARGIN, y + 10, anchor="w", text="Idle timeout",
            fill=FAINT, font=("Segoe UI", 11),
        )
        # Slider starts just past the label (measured) and ends with room for
        # the value readout - so the label and slider never collide at scale.
        slider_x = self._item_right_base(label_id, MARGIN + 96) + 20
        slider_right = WIDTH - MARGIN - 52
        slider_bg = self._bg_at((slider_x + slider_right) / 2, y + 10)
        slider = ctk.CTkSlider(
            self.root, from_=1, to=60, number_of_steps=59, command=self._on_timeout_change,
            fg_color=SURFACE, progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, bg_color=slider_bg, height=16,
        )
        slider.set(self.config["idle_timeout_seconds"])
        self.bg.create_window(slider_x, y + 2, anchor="nw", window=slider,
                              width=slider_right - slider_x, height=16)
        self.timeout_value_id = self.bg.create_text(
            WIDTH - MARGIN, y + 10, anchor="e",
            text=f"{self.config['idle_timeout_seconds']}s",
            fill=TEXT, font=("Segoe UI Semibold", 11),
        )

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
        self.console.configure(state="normal")
        # Color the [Subsystem] prefix if it's one we know; plain otherwise.
        tagged = False
        try:
            m = re.match(r"\[(\w+)\]", message)
            if m and m.group(1) in LOG_TAG_COLORS:
                tb = self.console._textbox
                tb.insert("end", m.group(0), (f"t_{m.group(1)}",))
                tb.insert("end", message[m.end():] + "\n")
                tagged = True
        except Exception:
            tagged = False
        if not tagged:
            self.console.insert("end", message + "\n")
        self.console.see("end")
        self.console.configure(state="disabled")

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
                    mm, ss = divmod(total_seconds, 60)
                    self.bg.itemconfigure(self.timer_label_id, text=f"{mm:02d}:{ss:02d}")
                    self.bg.itemconfigure(self.storage_label_id, text=_format_bytes(status.get("outputBytes", 0)))
            except OBSError:
                pass

        if not is_recording:
            self.bg.itemconfigure(self.timer_label_id, text="")
            self.bg.itemconfigure(self.storage_label_id, text="")

        was_paused = self._is_paused
        self._is_paused = is_paused
        if is_recording and is_paused:
            self.bg.itemconfigure(self.rec_dot_id, fill=AMBER)
        elif is_recording and (not self._is_recording or was_paused):
            self._pulse_dot(True)  # just started, or just resumed from pause
        elif not is_recording:
            self.bg.itemconfigure(self.rec_dot_id, fill=FAINT)
        self._is_recording = is_recording

        self.record_toggle_btn.configure(state="normal" if self.obs.connected else "disabled")
        if is_recording:
            self.record_toggle_btn.configure(
                text="■  Stop recording", fg_color=RED_TINT, hover_color=RED_TINT_HOVER, text_color=RED,
            )
        else:
            self.record_toggle_btn.configure(
                text="●  Record now", fg_color=GREEN_TINT, hover_color=GREEN_TINT_HOVER, text_color=GREEN,
            )

        self.root.after(1000, self._poll_obs_status)

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

    def _flash_status_card(self):
        """A brief brighter-border pulse on the status card glass panel
        whenever the detected game changes, so a switch is visually
        confirmed even if you're not staring at the timer/name text."""
        x, y, w, h = self._status_card_geom
        steps = [1.0, 0.6, 0.25, 0.0]

        def step(i=0):
            if i >= len(steps):
                self._regen_glass(self._status_card_item, x, y, w, h)
                return
            border_alpha = int(55 + (230 - 55) * steps[i])
            self._regen_glass(self._status_card_item, x, y, w, h, border_alpha=min(border_alpha, 255))
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
                self._flash_status_card()
                # The timer/storage/pulsing dot are driven by _poll_obs_status
                # from OBS's own GetRecordStatus, not from this event - that
                # way they reflect whether OBS is *actually* recording, not
                # just whether the monitor decided a game should be recorded.
            if "folder" in kwargs:
                self.bg.itemconfigure(self.folder_label_id, text=kwargs["folder"] or self.config["recording_root"])
            if "idle" in kwargs:
                self.idle_pill.set(*(("Yes", AMBER) if kwargs["idle"] else ("No", GREEN)))
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
        self.start_btn.configure(state="disabled", text="Connecting...")
        self.autostart()

    def _on_connected(self):
        self.start_btn.configure(text="▶  Start monitoring")
        self.obs_pill.set("Connected", GREEN)
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.monitor.start()

    def autostart(self):
        """Called once at launch, and again on retry, so the app starts
        recording-ready on its own (e.g. when run from Windows startup)
        without requiring a manual click - launches OBS itself if it isn't
        already running, and retries quietly rather than popping a blocking
        error dialog. Once monitor.start() runs, the monitor's own loop takes
        over reconnecting if OBS later crashes/closes."""
        if self.monitor._running:
            return
        self.obs_pill.set("Connecting...", AMBER)
        ensure_obs_running(self.config.get("obs_path"), log=self._log)
        try:
            self.obs.connect()
        except (OBSError, OSError) as e:
            self._log(f"[Monitor] OBS not available yet ({e}); retrying in 10s...")
            self.obs_pill.set("Disconnected", RED)
            self.root.after(10000, self.autostart)
            return
        self._on_connected()
        self._log("[Monitor] Auto-started.")

    def _on_connection_change(self, connected):
        self.root.after(0, lambda: self.obs_pill.set(
            *(("Connected", GREEN) if connected else ("Reconnecting...", RED))
        ))

    def _stop(self):
        self.monitor.stop()
        self.obs.disconnect()
        self.obs_pill.set("Disconnected", RED)
        self.start_btn.configure(state="normal", text="▶  Start monitoring")
        self.stop_btn.configure(state="disabled")

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
        self.rescan_btn.configure(text="⟳  Scanning" + "." * (n % 4))
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
            except Exception as e:
                self.root.after(0, lambda: self._log(f"[Steam] Rescan failed: {e}"))
            finally:
                self._scanning = False
                self.root.after(0, lambda: self.rescan_btn.configure(state="normal", text="⟳  Rescan Steam games"))

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
        try:
            self.root.iconphoto(False, self._taskbar_icon_frames[self._taskbar_icon_index % len(self._taskbar_icon_frames)])
        except Exception:
            pass
        self._taskbar_icon_index += 1
        self.root.after(80, self._animate_taskbar_icon)

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
