"""Nebula UI v3 design contract - section 05 of the mockup, as code.

Source: ``design/ui-v3/BUILD-SPEC.md`` (transcribed from the Claude Design doc
``Nebula UI Mockups v3.dc.html``). The mockup states its own precedence rule:

    "Every number the frames above imply, written down. If a frame and this
     table disagree, this table wins."

So this module is the single place a v3 number lives. ``gui.py`` should import
from here rather than re-declaring literals, and ``tests/test_design_v3.py``
asserts the values still match the spec.

Two things this module deliberately does NOT carry, because they can't be
honoured in Tk as written - see ``CURSOR-HANDOFF.md`` sections 2.1 and 2.4:

* the pointer spotlight / pointer lean (per-pointer-event full-window repaints)
* the aurora + star *motion* cycles

The background *randomisation* survives; only the animation is dropped. See
``BACKGROUND`` below.
"""

# ---------------------------------------------------------------------------
# Colour - "Nebula Deep"
# ---------------------------------------------------------------------------
# The spec is explicit: "No other hues exist in this app - log tag colours stay
# as LOG_TAG_COLORS in gui.py." Ember is live-and-errors ONLY; it is the one
# place a second hue leads, and only on the disconnected hero state (frame 2h).

GROUND = "#100D1C"        # window ground
GROUND_DEEP = "#0A0812"   # outer stop of the ground gradient (6.1 layer 0)
PANEL = "#12101F"         # panel base
CARD_CORE = "#181428"     # card core (the *inner* of the two card layers)
RAISED = "#241E44"        # raised surface, keycaps
ACCENT = "#8B7CF6"        # lines, dots, glow
ACCENT_TEXT = "#B9AEF9"   # accent text / icons on dark
EMBER = "#FF5C7A"         # live + errors ONLY
TEXT = "#F5F3FF"          # primary text
TEXT_SECONDARY = "#9A93C4"
TEXT_TERTIARY = "#8B84B8"  # captions
TEXT_EYEBROW = "#736BA4"   # eyebrow labels, mono meta

COLORS = {
    "ground": GROUND,
    "panel": PANEL,
    "card_core": CARD_CORE,
    "raised": RAISED,
    "accent": ACCENT,
    "accent_text": ACCENT_TEXT,
    "ember": EMBER,
    "text": TEXT,
    "text_secondary": TEXT_SECONDARY,
    "text_tertiary": TEXT_TERTIARY,
    "text_eyebrow": TEXT_EYEBROW,
}

# "Hairlines are rgba(245,243,255,0.055-0.09), never a solid grey."
HAIRLINE_RGB = (245, 243, 255)
HAIRLINE_ALPHA = (0.055, 0.09)

# "Tinted fills are the accent or ember at 0.06-0.16 alpha."
TINT_ALPHA = (0.06, 0.16)

# "In-window panels sit on rgba(16,13,28,0.72-0.92) so the aurora reads through
# them while text keeps its contrast. A fully opaque panel over the aurora is a
# bug." (16,13,28) is #100D1C, i.e. the ground itself at partial alpha.
PANEL_OVER_BACKDROP_ALPHA = (0.72, 0.92)

# "In-window cores are translucent so the aurora reads through: .72 for the
# rail and titlebar, .82-.92 for content cards." (6.2)
CHROME_ALPHA = int(round(0.72 * 255))       # rail, titlebar
CARD_ALPHA = int(round(0.86 * 255))         # content cards, mid-band


def _hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def over(fg, alpha, bg=CARD_CORE):
    """Composite ``fg`` at ``alpha`` over ``bg`` and return a flat hex.

    A ``tk.Canvas`` item has no alpha channel, so every "accent at 0.10" in the
    spec has to be resolved to an opaque colour against whatever it sits on.
    Doing that here keeps the alphas in the source readable instead of leaving
    a pile of unexplained hex values in ``gui.py``.
    """
    f, b = _hex_to_rgb(fg), _hex_to_rgb(bg)
    return _rgb_to_hex(f[i] * alpha + b[i] * (1.0 - alpha) for i in range(3))


def hairline(bg=PANEL, alpha=None):
    """The spec's hairline, composited over ``bg``."""
    if alpha is None:
        alpha = sum(HAIRLINE_ALPHA) / 2.0
    return over(_rgb_to_hex(HAIRLINE_RGB), alpha, bg)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
# Base design units, exactly as v2 did it - self.scale multiplies these on
# high-DPI monitors (see nebula-dpi-scaling). MIN_* is the spec's resizable
# floor; whether the layout actually reflows is an open decision, see
# CURSOR-HANDOFF.md 2.4.

WIDTH, HEIGHT = 1280, 808          # core
TRAY_INSET = 6                     # the core sits in a 6px tray
MIN_WIDTH, MIN_HEIGHT = 1080, 700

# Radii. "Nesting rule: inner = outer - padding."
RADIUS_TRAY = 28
RADIUS_CORE = 22
RADIUS_CARD = 17
RADIUS_TILE = 12
RADIUS_CONTROL = 9

# 6.2 - "A flat single-border card is a bug. Each card is a tinted outer shell
# with 4-6px of padding wrapping a darker inner core, and the inner radius
# equals the outer radius minus that padding."
#
# The whole nesting table, so a card can never be built with a geometry nobody
# chose. Every row satisfies core == shell - padding; test_design_v3 asserts it.
#
#   kind  -> (shell radius, padding, core radius)
CARD_LAYERS = {
    "tray":  (RADIUS_TRAY, 6, RADIUS_CORE),     # 28 / 6 / 22 - the window itself
    "hero":  (RADIUS_CORE, 5, RADIUS_CARD),     # 22 / 5 / 17
    "panel": (18, 4, 14),                       # activity, lists
    "tile":  (16, 4, RADIUS_TILE),              # 16 / 4 / 12 - stat tiles
}
# "Control / field 9-10, single layer - the one exception."
SINGLE_LAYER_RADIUS = (9, 10)

# The shell is a neutral wash, not an accent tint: rgba(245,243,255,.035) with a
# rgba(245,243,255,.06) border. The core is rgba(24,20,40,.82).
SHELL_HEX = "#f5f3ff"
SHELL_FILL_ALPHA = 0.035
SHELL_BORDER_ALPHA = 0.06
CORE_ALPHA = 0.82

TITLEBAR_H = 46
TITLEBAR_PAD_LEFT = 18
TITLEBAR_PAD_RIGHT = 8

RAIL_W = 232
RAIL_PAD_X = 16
RAIL_PAD_Y = 12
RAIL_ITEM_H = 38
RAIL_ITEM_GAP = 3

PANE_HEADER_H = 62
PANE_HEADER_PAD_X = 26

CONTENT_PAD = 26
STACK_GAP = 16

# Pane content is drawn at its true size in frames 2b-2e: 1048x746. That falls
# out of the geometry above (1280 - 232 = 1048; 808 - 46 - 16 = 746) - keeping
# it here as an assertion target rather than a second source of truth.
PANE_W = WIDTH - RAIL_W
PANE_H = HEIGHT - TITLEBAR_H - STACK_GAP

CONTROL_PILL_H = 40
CONTROL_FIELD_H = 36
ICON_BTN = (26, 30)                # icon button size range
MIN_HIT_TARGET = 30
SIBLING_GAP = 8

# "Trailing icons on primary pills live in their own 26-28px circle, flush to
# the right padding."
PILL_TRAILING_CIRCLE = (26, 28)

# "Rules and dividers fade at both ends over 32-48px."
RULE_FADE = (32, 48)

# ---------------------------------------------------------------------------
# Type
# ---------------------------------------------------------------------------
# The spec designs in Geist / Geist Mono and names its own shipping
# substitutes, so there is nothing to decide here: "UI face Geist 300/400/500 -
# ship as Segoe UI Variable", "Numeric face Geist Mono - ship as Cascadia Mono".

FONT_UI = "Segoe UI Variable"
FONT_MONO = "Cascadia Mono"

# ...except neither of those is a font family you can actually ask Tk for.
#
# Two things bite here, both found by probing tkfont.families() on this machine:
#
# 1. Windows ships "Segoe UI Variable" as three *optical sizes*, not one family:
#    Small, Text and Display. Asking for the bare name silently falls back to a
#    default face.
# 2. Tk truncates font family names at 31 characters, so the real names are
#    "Segoe UI Variable Display Semib" and "Segoe UI Variable Text Semiligh" -
#    not the full words. Spelling them out in full also silently falls back.
#
# And "Cascadia Mono" is simply not installed here, so the numeric face needs a
# fallback or the timer loses its tabular figures. Each stack below is tried in
# order against the families Tk actually reports; see resolve_fonts().

_OPTICAL = {  # px thresholds for Segoe UI Variable's optical sizes
    "small": 12,      # <= this
    "display": 24,    # >= this
}

FONT_STACKS = {
    ("small", 300):   ("Segoe UI Variable Small Light", "Segoe UI Light", "Segoe UI"),
    ("small", 400):   ("Segoe UI Variable Small", "Segoe UI", "Tahoma"),
    ("small", 500):   ("Segoe UI Variable Small Semibol", "Segoe UI Semibold", "Segoe UI"),
    ("text", 300):    ("Segoe UI Variable Text Light", "Segoe UI Light", "Segoe UI"),
    ("text", 400):    ("Segoe UI Variable Text", "Segoe UI", "Tahoma"),
    ("text", 500):    ("Segoe UI Variable Text Semibold", "Segoe UI Semibold", "Segoe UI"),
    ("display", 300): ("Segoe UI Variable Display Light", "Segoe UI Light", "Segoe UI"),
    ("display", 400): ("Segoe UI Variable Display", "Segoe UI", "Tahoma"),
    ("display", 500): ("Segoe UI Variable Display Semib", "Segoe UI Semibold", "Segoe UI"),
}

MONO_STACK = ("Cascadia Mono", "Consolas", "Courier New")

# Filled in by resolve_fonts() at startup; until then the first entry of each
# stack is assumed, which is correct on a machine that has the fonts.
_resolved = {}


def resolve_fonts(available):
    """Pick the first family in each stack that `available` actually contains.

    `available` is whatever ``tkinter.font.families()`` returns - passed in
    rather than queried here so this module needs no Tk and stays importable
    (and testable) on its own.
    """
    have = set(available)
    _resolved.clear()
    for key, stack in FONT_STACKS.items():
        _resolved[key] = next((f for f in stack if f in have), stack[-1])
    _resolved["mono"] = next((f for f in MONO_STACK if f in have), MONO_STACK[-1])
    return _resolved


def _optical(size_px):
    if size_px <= _OPTICAL["small"]:
        return "small"
    if size_px >= _OPTICAL["display"]:
        return "display"
    return "text"


def font(size_px, weight=400, mono=False):
    """A Tk font tuple for a v3 type size.

    The size is passed **negative**, which is Tk for "this many pixels" rather
    than points. That matters: the spec's type scale is CSS pixels, and the
    layout geometry is in the same units, so using Tk's default point sizing
    would render every string ~1.33x larger than the design against a layout
    that didn't grow with it. ScaledCanvas._scale_font multiplies negative
    sizes correctly, so high-DPI scaling still works.
    """
    size = -int(round(size_px))
    if mono:
        return (_resolved.get("mono", MONO_STACK[0]), size)
    key = (_optical(size_px), weight)
    return (_resolved.get(key, FONT_STACKS[key][0]), size)


def type_font(role, mono=False, weight=None):
    """The font for a named role in TYPE, e.g. type_font("timer")."""
    spec = TYPE[role]
    return font(spec["size"], weight or spec["weight"], mono=mono)

# (size, weight, tracking em) - tracking is informational; Tk has no letter
# spacing, so eyebrow text is spaced by hand where it matters.
TYPE = {
    "timer":      {"size": 34,   "weight": 400, "tracking": -0.02},
    "game_title": {"size": 25,   "weight": 500, "tracking": -0.02},
    "pane_title": {"size": 19,   "weight": 500, "tracking": 0.0},
    "body":       {"size": 13,   "weight": 400, "tracking": 0.0},
    "row":        {"size": 12.5, "weight": 400, "tracking": 0.0},
    "row_small":  {"size": 12,   "weight": 400, "tracking": 0.0},
    "meta":       {"size": 11.5, "weight": 400, "tracking": 0.0},
    "mono":       {"size": 10.5, "weight": 400, "tracking": 0.0},
    "eyebrow":    {"size": 9.5,  "weight": 500, "tracking": 0.22},
}

# ---------------------------------------------------------------------------
# Hero card states
# ---------------------------------------------------------------------------
# "Only the hero card changes; nothing else on the dashboard moves. Same 22px
# padding, same button row position - swap the eyebrow, the tint, and the
# primary action." One enum drives all four (frames 2a, 2f, 2g, 2h).

HERO_PAD = 22

HERO_STATES = {
    "recording":   {"eyebrow": "Recording",      "tint": ACCENT, "actions": ("Stop recording", "Pause", "Mark clip")},
    "watching":    {"eyebrow": "Idle - watching", "tint": None,   "actions": ("Record anyway", "Pause monitoring")},
    "paused":      {"eyebrow": "Paused",          "tint": ACCENT, "actions": ("Resume", "Stop & save")},
    "disconnected": {"eyebrow": "OBS disconnected", "tint": EMBER, "actions": ("Retry now", "Connection settings")},
}

# "Paused - accent tint, timer frozen at 60% opacity."
PAUSED_TIMER_OPACITY = 0.60

# ---------------------------------------------------------------------------
# Icons - Phosphor Light
# ---------------------------------------------------------------------------
# "Light weight everywhere at 12-24px. The only Fill glyphs are ph-circle
# (status dots, 6-8px) and ph-square (stop, 9-11px)."

ICON_SIZE = (12, 24)
ICON_FILL_ONLY = {"circle": (6, 8), "square": (9, 11)}

ICONS = {
    # navigation
    "dashboard": "broadcast",
    "clips": "film-strip",
    "games": "game-controller",
    "macropad": "keyboard",
    "settings": "sliders-horizontal",
    # transport
    "start": "record",
    "pause": "pause",
    "resume": "play",
    "mark_clip": "scissors",
    "scene": "stack-simple",
    # status
    "disconnected": "plugs",
    "connected": "plugs-connected",
    "storage": "hard-drives",
    "idle": "timer",
    "idle_pause": "moon",
    "hotkey": "command",
    # actions
    "rescan": "steam-logo",
    "reveal": "folder-open",
    "delete_clip": "trash",
    "show_window": "arrows-out-simple",
    "collapse_mini": "arrows-in-simple",
    "quit": "sign-out",          # tray only
    "hide_to_tray_minus": "minus",
    "hide_to_tray_x": "x",
}

# ---------------------------------------------------------------------------
# Config map - control -> config.json key
# ---------------------------------------------------------------------------
# Every key here already exists in config.DEFAULTS; the test asserts that, so a
# renamed key can't silently orphan a Settings field.
#
# The rules attached to this table in the spec:
#   * every *_seconds key is in seconds - render the unit suffix in every field
#     AND every status string
#   * write on blur, not per keystroke
#   * show the saved timestamp in the pane header
#   * never silently drop an unknown key - merge over DEFAULTS and keep the rest

CONFIG_MAP = [
    # (label, config key, section, unit)
    ("Host",                   "obs_host",                   "Connection",   None),
    ("Port",                   "obs_port",                   "Connection",   None),
    ("Password",               "obs_password",               "Connection",   None),
    ("OBS executable",         "obs_path",                   "Connection",   None),
    ("Reconnect every",        "reconnect_interval_seconds", "Connection",   "seconds"),
    ("Recording folder",       "recording_root",             "Storage",      None),
    ("Discard clips under",    "min_clip_seconds",           "Storage",      "seconds"),
    ("Pause after idle",       "idle_timeout_seconds",       "Idle & audio", "seconds"),
    ("Window poll rate",       "poll_interval_seconds",      "Idle & audio", "seconds"),
    ("Keep-alive apps",        "keep_alive_audio_processes", "Idle & audio", None),
    ("Toggle hotkey",          "toggle_hotkey",              "Hotkey",       None),
    ("... bind by scan code",  "toggle_hotkey_scancode",     "Hotkey",       None),
    ("Shared classifications", "sync_folder",                "Sync",         None),
]

SETTINGS_SECTIONS = ["Connection", "Storage", "Idle & audio", "Hotkey", "Sync"]

# ---------------------------------------------------------------------------
# Motion
# ---------------------------------------------------------------------------
# Kept for reference and for the surfaces where it IS affordable: the toast and
# the mini overlay are separate toplevels, so their fades don't composite this
# window. Inside the main window, treat every one of these as an instant state
# swap - see CURSOR-HANDOFF.md 2.1.

EASING = (0.32, 0.72, 0.0, 1.0)     # cubic-bezier(.32,.72,0,1)
HOVER_MS, PRESS_MS = 500, 120
PRESS_SCALE = 0.98
PANE_CHANGE_MS, PANE_CHANGE_RISE = 260, 8
LIVE_DOT_PERIOD_MS, LIVE_DOT_OPACITY = 1900, (0.35, 0.95)
FOCUS_RING_W, FOCUS_RING_OFFSET = 2, 2
DISABLED_OPACITY = 0.45

# "Never animate width / height / top / left."
# "The elapsed timer updates once per second and must not reflow its
#  neighbours - tabular figures, fixed width."
TIMER_TICK_MS = 1000

# ---------------------------------------------------------------------------
# Toast / tray / mini overlay
# ---------------------------------------------------------------------------

TOAST_LIFE_MS = 4000
TOAST_DRAIN_H = 2
TOAST_MARGIN = 24                    # from both edges of the active screen
TOAST_IN_MS, TOAST_IN_RISE = 320, 16
TOAST_OUT_MS = 200
# "Icon + tint per event: start/stop -> ember, pause/resume -> accent,
#  error -> ember."
TOAST_TINTS = {
    "start": EMBER, "stop": EMBER, "error": EMBER,
    "pause": ACCENT, "resume": ACCENT,
}

# ---------------------------------------------------------------------------
# Customise mode (6.8)
# ---------------------------------------------------------------------------
# "This feature was never specified - it was invented during the build, and it
# does not work." What follows is the spec for keeping it, which is what
# Anthony chose over cutting it.

GRID_COLS = 12
GRID_GAP = 16
# "Three widths only: 1/2 (6 col), 2/3 (8 col), Full (12 col)."
SPANS = (6, 8, 12)
SPAN_LABELS = {6: "½", 8: "⅔", 12: "Full"}
HANDLE_STRIP_H = 26          # "26px INSIDE the module, pushes content down"
EDIT_CONTENT_OPACITY = 0.55  # "Content while editing: pointer-events:none · opacity .55"
GRID_OVERLAY_ALPHA = 0.10    # "12 col, 1px accent @ .10, gap 16"
DRAG_ROTATE_DEG = -0.6       # "Dragged copy: rotate -0.6deg · shadow lg"
# "Origin slot collapses; siblings reflow over 260ms." Recorded, deliberately
# not animated: reflowing many canvas items over 260ms is a per-frame window
# composite, which is the one thing this UI cannot do. Siblings snap on drop.
REFLOW_MS_UNUSED = 260

# ---------------------------------------------------------------------------
# Session ribbon (7b) and storage forecast (7c)
# ---------------------------------------------------------------------------
RIBBON_H = 188                  # "Real size - 996x188 inside the Clips pane"
RIBBON_TRACK_H = 38             # "Track h 38, gap 3, radius 3 (6 on ends)"
RIBBON_TRACK_GAP = 3
RIBBON_RADIUS = 3
RIBBON_END_RADIUS = 6
RIBBON_MIN_BLOCK = 4            # "shorter spans merge into neighbour"
RIBBON_BLOCK_TOP = "#8B7CF6"    # linear-gradient(180deg, #8B7CF6, #5340A8)
RIBBON_BLOCK_BOTTOM = "#5340A8"
RIBBON_SHADE_STEP = 0.08        # "Per-game shade: lightness ±8% only"
RIBBON_HATCH_ALPHA = 0.07       # "Idle gap: 135° hatch, 4px period, alpha .07"
RIBBON_HATCH_PERIOD = 4
RIBBON_MARK_W = 2               # "Clip mark: 2px #FF5C7A, overhangs 5px"
RIBBON_MARK_OVERHANG = 5
RIBBON_AXIS_TICKS = (4, 5)
RIBBON_LIVE_UPDATE_MS = 10000   # "Live update: last block width every 10s"
RIBBON_RANGES = ("Day", "12h", "Session")

# 7e - command palette. "560xauto, centred with a 22% top offset, backdrop at
# 55% black."
PALETTE_W = 560
# DELIBERATE DEVIATION from the mockup's 22%, requested by the user: the palette
# "is way too far down" with "so much room at the top".
#
# It was also further down than 22% ever intended. The CSS was `padding-top: 22%`,
# and a percentage padding - top included - resolves against the containing
# block's *width*, not its height. On a 1280x808 window that is 0.22 x 1280 =
# ~281px rather than the 0.22 x 808 = ~178px the spec meant: ~100px too low
# before any question of taste. The token is emitted in vh so the fraction means
# what it reads as.
PALETTE_TOP_FRACTION = 0.14
PALETTE_BACKDROP_ALPHA = 0.55
PALETTE_ROW_H = 38
PALETTE_GROUP_H = 24

STORAGE_CARD = (486, 286)
FORECAST_REFRESH_MS = 15 * 60 * 1000     # "Refresh: on launch, on rec_stop, every 15 min"

MINI_W, MINI_H = 296, 54
MINI_SNAP_PX = 32                    # snap to nearest corner within this
MINI_FADE_AFTER_MS = 3000
MINI_FADED_OPACITY = 0.55

# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------
# The spec's values, kept in full. What changed is *when* they're used: these
# seed a single render at launch instead of an animation.
#
#   "The background is randomised per launch - never hard-code blob positions
#    or star coordinates."
#
# That requirement is honoured. The motion cycles below are recorded for
# provenance and are deliberately unused - reintroducing them would reinstate
# the per-frame composite that measured p50 110ms at 95% CPU (CLAUDE.md, and
# tests/test_frame_pacing.py).

BACKGROUND = {
    # 0 - ground: radial-gradient(150% 110% at 50% -10%, PANEL 0%, GROUND_DEEP 58%)
    "ground_stop": 0.58,
    # 1 - aurora: three blobs, sized as a fraction of the surface
    "blobs_per_surface": 3,
    "blob_size_w": (0.42, 0.58),
    "blob_size_h": (0.56, 0.88),
    "blob_blur_px": (54, 110),
    "blob_fade_at": 0.68,               # rgba(...) -> transparent 68%
    # Above the spec's .22/.22/.07. Those alphas were written for a surface
    # where the blobs also MOVE - drift is most of what makes a faint wash
    # register, and without it .22 measured as a peak delta of 61 over the
    # ground, which is present-but-barely. Motion is not coming back (the
    # composite cost is in gui.py's note), so the amplitude has to carry the
    # aurora on its own. Ratios are the spec's: accent leads, indigo matches
    # it, ember stays roughly a third of them.
    "blob_alpha": {"accent": 0.34, "deep": 0.30, "ember": 0.13},
    # 1b - aurora filaments. NOT a fourth blob: `blobs_per_surface` stays 3,
    # because these are a different thing. The three blobs give the surface its
    # colour; three soft ellipses is also exactly why the old backdrop read as
    # three soft ellipses. A nebula has structure - lanes of brighter gas
    # curling through the wash - and that is what these are. Same trick as the
    # blobs (baked once, no motion), so they cost nothing per frame.
    "wisp_count": 7,
    "wisp_size_w": (0.30, 0.62),        # fraction of the surface
    "wisp_size_h": (0.10, 0.20),
    "wisp_alpha": {"accent": 0.20, "deep": 0.16, "ember": 0.09},
    # Blur as a fraction of the wisp's OWN height, not an absolute px figure.
    # A lane is thin, so the blobs' 54px would not soften it, it would erase it.
    "wisp_blur_frac": 0.24,
    "wisp_angle": (-38, 38),            # degrees
    # 2/3 - star dust. "Near layer N = star density (default 34). Far layer =
    # 0.75xN, max size 1.3px, max alpha .5, wrapper opacity .7."
    #
    # Density is above the spec's default 34. That number was written for an
    # animated sky, where parallax drift carries the depth on its own; static,
    # 34 dots over this window area is a thin scatter rather than a field, so
    # the depth has to come from count and variance instead.
    "star_layers": 2,
    "star_density": 52,
    "star_size_near": (1.0, 1.9),
    "star_alpha_near": (0.24, 0.85),
    "star_size_far_max": 1.3,
    "star_alpha_far_max": 0.5,
    "star_far_opacity": 0.7,
    # A few near stars are brighter and carry a faint cross glint. Uniform dust
    # reads as sensor noise; a sky needs a handful of things to actually look
    # at. Still STAR_RGB - "never #fff" holds at every alpha.
    "star_bright_every": 13,            # 1 in N of the near layer
    "star_bright_alpha": 0.95,
    # Short arms, low alpha. Long even arms drew a literal "+" - a diffraction
    # spike is a hint that the dot is too bright for its size, not a symbol.
    "star_glint_px": 3.2,               # arm length of the cross, base px
    "star_glint_alpha": 0.20,           # x star_bright_alpha
    # 4 - vignette
    # Eased off the spec's .55: at that strength the ramp reached the corners
    # before the aurora did, so the outer third of the window was flat black
    # whatever layer 1 put there. .45 still sits the rounded corners in shadow.
    "vignette": {"transparent_to": 0.46, "black_alpha": 0.45},
}

# Recorded, not used - see the note above.
BACKGROUND_MOTION_UNUSED = {
    "blob_cycle_s": (46, 92),
    "blob_travel_pct": 9,
    "blob_scale": (1.0, 1.14),
    "star_speed_near_s": (120, 170),
    "star_speed_far_s": (190, 260),
    "pointer_spotlight_px": 300,
    "pointer_spotlight_alpha": 0.22,
    "pointer_lean_page_px": 16,
    "pointer_lean_window_px": 7,
    # The lean was applied with no damping at all: every pointermove wrote the
    # new offset straight onto the backdrop, so the lights tracked the cursor
    # 1:1 with zero latency. Even at 9px that reads as jitter rather than
    # parallax - "all over the place". The magnitude was never really the
    # problem; the instantaneous response was. This eases the backdrop toward
    # the pointer instead, which is also free: transform is compositor-only,
    # so a CSS transition costs nothing the lean was not already costing.
    "pointer_lean_ms": 900,
}

# ---------------------------------------------------------------------------
# Panes
# ---------------------------------------------------------------------------
# v2's "recordings" pane is v3's "clips"; "activity" is folded into the
# dashboard as a block rather than being its own rail entry.

PANES = ["dashboard", "clips", "games", "macropad", "settings"]

PANE_TITLES = {
    "dashboard": "Dashboard",
    "clips": "Clips",
    "games": "Games",
    "macropad": "Macropad",
    "settings": "Settings",
}

PANE_EYEBROWS = {
    "dashboard": "Live session",
    "settings": "Writes config.json on blur",
}
