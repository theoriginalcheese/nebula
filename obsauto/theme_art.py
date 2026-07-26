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

_STAR_TINTS = [(245, 243, 255), (196, 189, 240), (173, 196, 255)]


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


def generate_backdrop_v3(width, height, seed=None):
    """The v3 aurora + starfield, rendered once from `seed` (random per launch
    when None). Returns an opaque RGBA image the size asked for."""
    from . import design_v3 as d  # local: keeps this module importable alone

    rng = random.Random(seed)
    spec = d.BACKGROUND
    img = Image.new("RGBA", (width, height), (*_hex_to_rgb(d.GROUND), 255))

    # Blur radii in the spec are base design pixels; scale them with the surface
    # so a high-DPI render is proportionally as soft, not sharper.
    unit = max(width, height) / float(d.WIDTH)
    blur_lo, blur_hi = spec["blob_blur_px"]

    # "3 per surface" - one blob each of accent, deep and ember.
    for tone, alpha in (
        ("accent", spec["blob_alpha"]["accent"]),
        ("deep", spec["blob_alpha"]["deep"]),
        ("ember", spec["blob_alpha"]["ember"]),
    ):
        hex_color = {"accent": d.ACCENT, "deep": AURORA_DEEP, "ember": d.EMBER}[tone]
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        cx = rng.uniform(0.04, 0.96) * width
        cy = rng.uniform(-0.05, 1.05) * height
        rx = rng.uniform(0.26, 0.40) * width
        ry = rng.uniform(0.30, 0.46) * height
        ImageDraw.Draw(layer).ellipse(
            [cx - rx, cy - ry, cx + rx, cy + ry],
            fill=(*_hex_to_rgb(hex_color), int(round(alpha * 255))),
        )
        layer = _blur_downscaled(layer, rng.uniform(blur_lo, blur_hi) * unit, (width, height))
        img = Image.alpha_composite(img, layer)

    # Two star layers. Static, so "near/far" is expressed as size and alpha
    # rather than parallax speed - the far layer is smaller, dimmer and sparser.
    draw = ImageDraw.Draw(img)
    size_lo, size_hi = spec["star_size_px"]
    alpha_lo, alpha_hi = spec["star_alpha"]
    area_ratio = (width * height) / float(d.WIDTH * d.HEIGHT)
    for layer_index in range(spec["star_layers"]):
        far = layer_index == 1
        count = int(round((100 if far else 135) * area_ratio))
        for _ in range(count):
            x = rng.uniform(0, width)
            y = rng.uniform(0, height)
            radius = rng.uniform(size_lo, size_hi) * unit * (0.7 if far else 1.0) / 2.0
            alpha = rng.uniform(alpha_lo, alpha_hi * (0.6 if far else 1.0))
            tint = rng.choice(_STAR_TINTS)
            draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                         fill=(*tint, int(round(alpha * 255))))

    vignette = spec["vignette"]
    img.paste((0, 0, 0), (0, 0), _vignette_mask_v3(
        width, height, vignette["transparent_to"], vignette["black_alpha"]))
    return img


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
