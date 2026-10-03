# Frozen excerpt of obsauto/design_v3.py at commit a1ebd65 (2026-08-08).
# Nothing imports this. Live tokens: obsauto/design_v3.py
# Backup of the toast Anthony confirmed on 2026-10-01.

TOAST_LIFE_MS = 4000
TOAST_DRAIN_H = 2
TOAST_MARGIN = 24                    # from both edges of the active screen
TOAST_IN_MS, TOAST_IN_RISE = 420, 28
TOAST_OUT_MS = 320
# Capsule silhouette (design C): pill radius = height / 2. Width tuned so a
# title + middot + game name fit without wrapping.
TOAST_W, TOAST_H = 384, 60
TOAST_PROMPT_W, TOAST_PROMPT_H = 404, 116
TOAST_PAD = 3                        # shell → core inset (two-layer card)
# Keep text clear of the capsule's curved ends (radius ≈ H/2).
TOAST_TEXT_INSET = 32
# Chromakey for true pill corners on the frameless toplevel (not in the
# Nebula Deep palette, so it never punches holes in the glass).
TOAST_KEY = "#00FF01"
# "Icon + tint per event: start/stop -> ember, pause/resume -> accent,
#  error -> ember."
TOAST_TINTS = {
    "start": EMBER, "stop": EMBER, "error": EMBER,
    "pause": ACCENT, "resume": ACCENT,
    "prompt": ACCENT,
}
TOAST_PROMPT_LIFE_MS = 30000
# Soft dust near the icon chip - (dx, dy, radius_px, base_alpha) relative to
# the chip centre. Animated on the toast surface only (own toplevel; free).
TOAST_DUST = (
    (20, -12, 2.2, 0.78),
    (30, -5, 1.5, 0.48),
    (17, 15, 1.8, 0.58),
    (-11, -17, 1.4, 0.42),
    (38, 11, 1.2, 0.36),
    (7, -19, 1.1, 0.32),
    (26, 16, 1.0, 0.28),
)
# Event-flavoured motion for the dust. Each show also draws a fresh random
# seed so the same event never repeats the identical dance.
TOAST_DUST_STYLE = {
    "start": "burst",      # outward pulse from the chip
    "stop": "sink",        # settle inward / down
    "pause": "drift",      # slow lateral float
    "resume": "rise",      # lift and brighten
    "error": "scatter",    # jittery, uneven
    "prompt": "orbit",     # calm circular wander
}
# Which end of the capsule the constellation lives on. Action flavours hug
# the icon; calmer ones float at the trailing end so the toast feels alive
# in more than one place.
TOAST_DUST_ANCHOR = {
    "burst": "left",
    "sink": "left",
    "rise": "left",
    "scatter": "left",
    "drift": "right",
    "orbit": "right",
}

