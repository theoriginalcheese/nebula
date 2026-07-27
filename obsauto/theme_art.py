"""Generates the app's atmospheric "nebula" backdrop and translucent glass
panels, inspired by BetterDiscord themes like ClearVision/Neutron - soft
blurred colour blobs on a dark base, with frosted rounded panels floating on
top rather than flat solid cards.

Real OS blur-behind (SetWindowCompositionAttribute) was tried and confirmed
broken on this Windows 11 build, so instead of blurring the desktop, this
bakes a nice atmospheric image *into* the app and uses genuine alpha-channel
PNGs for the "glass" panels. Tkinter's Canvas actually composites RGBA
PhotoImages correctly against other canvas content (unlike opaque native
widgets, which was the bug in an earlier attempt) - so a tinted, rounded,
semi-transparent tile placed over the nebula backdrop gives real translucency
with genuinely rounded corners, no mismatched boxes.
"""

import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageTk

BASE_COLOR = "#0F0C1A"
BLOBS = [
    # (x_fraction, y_fraction, radius, hex_color, alpha)
    # The violet blobs carry most of the accent. Baking the colour in here (as
    # opposed to a separate overlay) matters: gui.py samples widget bg_colors
    # from a composite built off this image, so anything painted here is matched
    # exactly, while a moving overlay layer can never be.
    (0.08, 0.05, 260, "#4C2A9E", 132),
    (0.92, 0.10, 230, "#1D4ED8", 95),
    (0.85, 0.55, 260, "#7C3AED", 105),
    (0.10, 0.62, 240, "#0891B2", 80),
    (0.50, 0.98, 300, "#5B21B6", 112),
]
STAR_COLORS = [(245, 243, 255), (196, 189, 240), (173, 196, 255)]


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _scatter_stars(img, width, height):
    """A sparse field of tiny stars, drawn crisp *after* the blob blur so
    they read as points of light rather than smearing into the nebula.
    Seeded so the backdrop is identical every launch - a subtly different
    sky each start would read as flicker, not atmosphere."""
    rng = random.Random(7)
    draw = ImageDraw.Draw(img)
    for _ in range(90):
        x, y = rng.randrange(width), rng.randrange(height)
        color = rng.choice(STAR_COLORS)
        alpha = rng.randint(20, 95)
        if rng.random() < 0.12:
            draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=(*color, alpha))
        else:
            draw.point((x, y), fill=(*color, alpha))


# Big Gaussian blurs are the single most expensive thing in startup, and they
# scale with image area. Since everything we blur here is a soft, low-frequency
# shape (colour blobs, a vignette falloff), blurring a downscaled copy with a
# proportionally smaller radius and scaling back up is visually indistinguishable
# and roughly an order of magnitude cheaper. (make_accent_glow already did this.)
_BLUR_DOWNSCALE = 4


def _blur_downscaled(img, radius, size):
    width, height = size
    sw, sh = max(1, width // _BLUR_DOWNSCALE), max(1, height // _BLUR_DOWNSCALE)
    small = img.resize((sw, sh), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(radius / _BLUR_DOWNSCALE))
    return small.resize((width, height), Image.BILINEAR)


def _apply_vignette(img, width, height, max_alpha=80):
    """Gently darken the edges so the composition draws the eye inward and
    the window's own rounded corners sit in shadow rather than glow."""
    mask = Image.new("L", (width, height), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse(
        [-width * 0.25, -height * 0.25, width * 1.25, height * 1.25], fill=255,
    )
    mask = _blur_downscaled(mask, 120, (width, height))
    edge = ImageOps.invert(mask).point(lambda p: int(p * (max_alpha / 255)))
    img.paste((0, 0, 0), (0, 0), edge)
    return img


def generate_nebula(width, height):
    base = Image.new("RGBA", (width, height), (*_hex_to_rgb(BASE_COLOR), 255))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for fx, fy, radius, color, alpha in BLOBS:
        cx, cy = int(width * fx), int(height * fy)
        r, g, b = _hex_to_rgb(color)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(r, g, b, alpha))
    overlay = _blur_downscaled(overlay, 90, (width, height))
    img = Image.alpha_composite(base, overlay)
    _scatter_stars(img, width, height)
    return _apply_vignette(img, width, height)


# ---------------------------------------------------------------------------
# v3 backdrop
# ---------------------------------------------------------------------------
# The v3 spec ("Living background - exact values") describes two animated
# layers. Here they are rendered ONCE, from a seed drawn at launch. That keeps
# the requirement the spec actually writes down -
#
#     "The background is randomised per launch - never hard-code blob positions
#      or star coordinates."
#
# - while dropping the motion, which on this window is a full composite per
# frame at a flat ~100ms (see CLAUDE.md, and CURSOR-HANDOFF.md 2.1).
#
# Note this reverses _scatter_stars' fixed seed, and deliberately so: that seed
# existed because a *different sky each launch* was judged to read as flicker.
# It doesn't - you only ever see one sky per run. What actually read as flicker
# was the sky changing *within* a session, which nothing here does.

# The spec's blob palette is "accent · deep · ember". "Deep" is the raised
# surface tone - the deepest chromatic token in the Nebula Deep palette.
AURORA_DEEP = "#241E44"

# "Colour is always rgba(217,212,255,a) - never #fff." The old three-tint mix
# included a blue that read as a second accent hue, which v3 doesn't have.
STAR_RGB = (217, 212, 255)


def _vignette_mask_v3(width, height, inner_frac, max_alpha):
    """Transparent out to `inner_frac` of the half-diagonal, then ramping to
    `max_alpha` at the corners. Computed small and upscaled - the ramp is
    low-frequency, so nothing is lost and it costs almost nothing."""
    sw, sh = 64, 64
    mask = Image.new("L", (sw, sh), 0)
    px = mask.load()
    for y in range(sh):
        for x in range(sw):
            # normalised distance from centre, 1.0 at the corners
            dx = (x + 0.5) / sw * 2.0 - 1.0
            dy = (y + 0.5) / sh * 2.0 - 1.0
            dist = min(1.0, (dx * dx + dy * dy) ** 0.5 / (2 ** 0.5))
            if dist <= inner_frac:
                continue
            t = (dist - inner_frac) / (1.0 - inner_frac)
            px[x, y] = int(255 * max_alpha * t * t)
    return mask.resize((width, height), Image.BICUBIC)


def _ground_gradient_v3(width, height, inner_hex, outer_hex, stop):
    """Layer 0: radial-gradient(150% 110% at 50% -10%, inner 0%, outer `stop`).

    Painted small and upscaled - it is the lowest-frequency thing on screen, so
    a 96px render carries every bit of information a 1770px one would.
    """
    sw, sh = 96, 96
    grad = Image.new("RGB", (sw, sh))
    px = grad.load()
    r0, g0, b0 = _hex_to_rgb(inner_hex)
    r1, g1, b1 = _hex_to_rgb(outer_hex)
    # The gradient box is 150% x 110% of the surface, centred at (50%, -10%).
    cx, cy = 0.5, -0.10
    rx, ry = 0.75, 0.55
    for y in range(sh):
        fy = ((y + 0.5) / sh - cy) / ry
        for x in range(sw):
            fx = ((x + 0.5) / sw - cx) / rx
            t = min(1.0, ((fx * fx + fy * fy) ** 0.5) / stop)
            px[x, y] = (int(r0 + (r1 - r0) * t),
                        int(g0 + (g1 - g0) * t),
                        int(b0 + (b1 - b0) * t))
    return grad.resize((width, height), Image.BICUBIC).convert("RGBA")


def _radial_blob(size, colour, alpha, fade_at=0.68):
    """One aurora blob: radial-gradient(circle, rgba(colour, alpha), transparent
    `fade_at`). Drawn as a real falloff rather than a hard ellipse that gets
    blurred - a blurred disc keeps a flat plateau in the middle, which is what
    made the aurora read as a smudge instead of light."""
    w, h = size
    steps = 48
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rgb = _hex_to_rgb(colour)
    for i in range(steps, 0, -1):
        t = i / steps                      # 1.0 at the rim, ->0 at the centre
        if t > fade_at:
            continue
        # Linear, like the CSS stop it comes from. A squared falloff packs the
        # brightness into a small core that a 54px blur then flattens away -
        # measured peak 22/255 against the linear ramp's 38.
        a = alpha * (1.0 - t / fade_at)
        rx, ry = w / 2 * t, h / 2 * t
        draw.ellipse([w / 2 - rx, h / 2 - ry, w / 2 + rx, h / 2 + ry],
                     fill=(*rgb, int(round(a * 255))))
    return layer


def generate_backdrop_v3(width, height, seed=None):
    """The v3 living background, rendered once from `seed` (random per launch
    when None).

    Returns **two** images: the full stack, and the same stack without the star
    dust. Section 6.1 of the build spec names the single biggest defect of the
    last build as "star dots are currently painted above the rail and the
    cards... the whole background stack lives at z-index:0 behind the chrome -
    never inside it, never over it", while also requiring the chrome to stay
    translucent so the aurora reads through it. Both hold at once only if the
    chrome composites against a surface that has the aurora but not the dust:
    the aurora is a broad wash that survives glass, a 1.9px star at .85 alpha
    punches through it as a speck of dirt.

    The five layers, back to front:
      0  ground gradient
      1  aurora blobs x3 (accent .22, deep indigo .22, ember .07)
      2  star dust, near
      3  star dust, far
      4  vignette
    """
    from . import design_v3 as d  # local: keeps this module importable alone

    rng = random.Random(seed)
    spec = d.BACKGROUND

    # --- 0: ground -----------------------------------------------------------
    img = _ground_gradient_v3(width, height, d.PANEL, d.GROUND_DEEP,
                              spec["ground_stop"])

    # Blur radii in the spec are base design pixels; scale them with the surface
    # so a high-DPI render is proportionally as soft, not sharper.
    unit = max(width, height) / float(d.WIDTH)
    blur_lo, blur_hi = spec["blob_blur_px"]
    w_lo, w_hi = spec["blob_size_w"]
    h_lo, h_hi = spec["blob_size_h"]

    # --- 1: aurora -----------------------------------------------------------
    # "Three per surface: accent .22, deep indigo .22, ember .07. The ember one
    # is what keeps the ground from going cold - do not drop it."
    for tone in ("accent", "deep", "ember"):
        alpha = spec["blob_alpha"][tone]
        hex_color = {"accent": d.ACCENT, "deep": AURORA_DEEP, "ember": d.EMBER}[tone]
        bw = int(rng.uniform(w_lo, w_hi) * width)
        bh = int(rng.uniform(h_lo, h_hi) * height)
        blob = _radial_blob((bw, bh), hex_color, alpha, spec["blob_fade_at"])
        # The spec's own CSS marks 54px as the per-element blur and 90-110 as
        # what the page ends up with once the blobs overlap. Blurring each one
        # by the page-level figure crushed the peak alpha from 49/255 to 9 and
        # the aurora vanished, which is exactly the defect 6.1 reports.
        blob = _blur_downscaled(blob, blur_lo * unit, (bw, bh))
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        # No mask. Passing the blob as its own mask multiplies its alpha by
        # itself - a 19% blob became 3.6%, then rounded away to nothing.
        layer.paste(blob, (int(rng.uniform(-0.18, 0.82) * width),
                           int(rng.uniform(-0.28, 0.72) * height)))
        img = Image.alpha_composite(img, layer)

    # This is the surface the chrome sits on: everything above is dust, which
    # must not appear inside a card.
    aurora_only = img.copy()

    # --- 2 & 3: star dust ----------------------------------------------------
    # "Vary size and alpha per dot; no uniform grid; never #fff." Static here,
    # so near/far is carried by size, alpha and density rather than by parallax
    # speed - animating either layer would cost a full window composite a frame.
    draw = ImageDraw.Draw(img)
    area_ratio = (width * height) / float(d.WIDTH * d.HEIGHT)
    near_size_lo, near_size_hi = spec["star_size_near"]
    near_a_lo, near_a_hi = spec["star_alpha_near"]
    for far in (False, True):
        count = int(round(spec["star_density"] * (0.75 if far else 1.0) * area_ratio))
        size_hi = spec["star_size_far_max"] if far else near_size_hi
        alpha_hi = spec["star_alpha_far_max"] if far else near_a_hi
        # "wrapper opacity .7" on the far layer, on top of its lower ceiling.
        dim = spec["star_far_opacity"] if far else 1.0
        for _ in range(count):
            x, y = rng.uniform(0, width), rng.uniform(0, height)
            radius = rng.uniform(near_size_lo, size_hi) * unit / 2.0
            alpha = rng.uniform(near_a_lo, alpha_hi) * dim
            draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                         fill=(*STAR_RGB, int(round(alpha * 255))))

    # --- 4: vignette ---------------------------------------------------------
    vignette = spec["vignette"]
    mask = _vignette_mask_v3(width, height, vignette["transparent_to"],
                             vignette["black_alpha"])
    img.paste((0, 0, 0), (0, 0), mask)
    aurora_only.paste((0, 0, 0), (0, 0), mask)
    return img, aurora_only


def make_glass_tile(width, height, tint_hex, tint_alpha=145, radius=16, border_hex=None, border_alpha=90):
    """A rounded, semi-transparent tile: fully transparent outside the
    rounded rect (so the nebula shows through untouched there, giving real
    rounded corners), tinted+translucent inside (so the nebula shows through
    faintly, tinted, giving the frosted-glass look)."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [0, 0, width - 1, height - 1], radius=radius,
        fill=(*_hex_to_rgb(tint_hex), tint_alpha),
        outline=(*_hex_to_rgb(border_hex or tint_hex), border_alpha),
        width=1,
    )

    # Glass dimensionality, clipped to the rounded shape: a soft white highlight
    # catching the top edge (light from above), plus a faint shadow settling into
    # the bottom edge. Together they lift the flat tint into a real pane of glass.
    # Both kept low-alpha so they read as finish, not gloss.
    rounded_mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(rounded_mask).rounded_rectangle(
        [0, 0, width - 1, height - 1], radius=radius, fill=255,
    )

    top_h = max(1, int(height * 0.55))
    top_alpha = Image.new("L", (width, height), 0)
    tdraw = ImageDraw.Draw(top_alpha)
    for i in range(top_h):
        tdraw.line([(0, i), (width, i)], fill=int(20 * (1 - i / top_h) ** 1.4))
    img.paste((255, 255, 255), (0, 0), ImageChops.multiply(top_alpha, rounded_mask))

    bot_h = max(1, int(height * 0.35))
    bot_alpha = Image.new("L", (width, height), 0)
    bdraw = ImageDraw.Draw(bot_alpha)
    for i in range(bot_h):
        y = height - 1 - i
        bdraw.line([(0, y), (width, y)], fill=int(18 * (1 - i / bot_h) ** 1.4))
    img.paste((0, 0, 0), (0, 0), ImageChops.multiply(bot_alpha, rounded_mask))
    return img


def make_solid_tile(width, height, hex_color, radius=12):
    """A fully opaque rounded tile - no tint, no sheen, no border.

    Backing plate for an embedded CTk widget. A CTk widget fills the area its
    rounded corners cut away with one flat `bg_color`, which can't match a
    background that varies (a sheen gradient, a drifting glow) - you get a square
    fringe. So instead: draw this rounded plate on the canvas, then place the
    widget square and flat in the same colour, inset by `radius`. The rounding
    you see is this tile's, cleanly anti-aliased against whatever is behind it,
    and the widget never has to match anything."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, width - 1, height - 1], radius=radius,
        fill=(*_hex_to_rgb(hex_color), 255),
    )
    return img


def make_accent_glow(size, hex_color, peak_alpha=44):
    """A soft radial bloom of `hex_color`, fading to fully transparent at the
    rim. Painted into the backdrop *behind* the glass panels - since those are
    translucent, the accent glows up through them ("lit from within") - and it's
    cheap enough to drift and pulse for a living background without ever
    regenerating the nebula itself.

    The falloff is built small then upscaled + blurred, which is far cheaper
    than drawing hundreds of concentric ellipses at full size and gives a
    smoother ramp."""
    r, g, b = _hex_to_rgb(hex_color)
    base = 96
    mask = Image.new("L", (base, base), 0)
    draw = ImageDraw.Draw(mask)
    half = base / 2
    for i in range(int(half), 0, -1):
        edge_frac = i / half  # 1.0 at the rim -> 0.0 at the centre
        draw.ellipse(
            [half - i, half - i, half + i, half + i],
            fill=int(255 * (1 - edge_frac) ** 2),
        )
    mask = mask.resize((size, size), Image.LANCZOS).filter(
        ImageFilter.GaussianBlur(size / 18)
    )
    glow = Image.new("RGBA", (size, size), (r, g, b, 0))
    glow.putalpha(mask.point(lambda p: p * peak_alpha // 255))
    return glow


def to_photo(pil_image):
    return ImageTk.PhotoImage(pil_image)
