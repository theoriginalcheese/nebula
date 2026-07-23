"""Generates the app's icon: an original sparkle-in-orbit design (inspired by
the common "AI/magic sparkle" icon motif - a four-point star with tilted
orbit rings - but drawn from scratch for Nebula's own violet/gold palette,
not copied from any existing icon asset) plus rotation frames so the tray
icon can animate.
"""

import math

from PIL import Image, ImageDraw

VIOLET = (139, 124, 246, 255)   # matches gui.py's ACCENT
GOLD = (245, 166, 35, 255)      # matches gui.py's AMBER
WHITE = (245, 243, 255, 255)    # matches gui.py's TEXT


def _four_point_star(cx, cy, outer_r, inner_r, rotation_deg=0):
    """8 alternating points (tip, notch, tip, notch...) around a center -
    the classic sparkle/twinkle shape."""
    points = []
    for i in range(8):
        angle = math.radians(rotation_deg + i * 45)
        r = outer_r if i % 2 == 0 else inner_r
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def _draw_sparkle(draw, cx, cy, size, color, rotation_deg=0):
    draw.polygon(
        _four_point_star(cx, cy, size, size * 0.34, rotation_deg),
        fill=color,
    )


def render_frame(size=256, ring_rotation=0.0, supersample=4):
    """One frame: a bold central sparkle with a single tilted orbit ring,
    rotated by ring_rotation degrees for the animated tray-icon version.
    Kept deliberately simple - an earlier two-ring, multi-accent version
    turned into an illegible smudge once scaled down to a real 16-24px tray
    icon, so this favors legibility at that size over detail at 256px."""
    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = s / 2

    ring_w = max(int(s * 0.05), 2)
    _draw_tilted_ellipse(img, cx, cy, s * 0.46, s * 0.46 * 0.6, 22 + ring_rotation, GOLD, ring_w)

    # Central sparkle stays fixed - the icon should still read clearly as
    # "one thing" even mid-animation, not spin apart into confetti.
    _draw_sparkle(draw, cx, cy, s * 0.34, VIOLET)

    return img.resize((size, size), Image.LANCZOS)


def _draw_tilted_ellipse(base_img, cx, cy, rx, ry, tilt_deg, color, width):
    """PIL can't stroke a rotated ellipse directly - draw it on its own
    upright layer, then rotate the whole layer and composite."""
    pad = int(max(rx, ry) * 2.4)
    layer = Image.new("RGBA", (pad, pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lcx, lcy = pad / 2, pad / 2
    d.ellipse([lcx - rx, lcy - ry, lcx + rx, lcy + ry], outline=color, width=width)
    layer = layer.rotate(tilt_deg, resample=Image.BICUBIC, expand=False)
    base_img.alpha_composite(layer, (int(cx - pad / 2), int(cy - pad / 2)))


def generate_static_icon(size=256):
    return render_frame(size=size, ring_rotation=0.0)


def generate_animation_frames(size=64, n_frames=24):
    return [render_frame(size=size, ring_rotation=360 * i / n_frames) for i in range(n_frames)]


def save_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    base = render_frame(size=256)
    imgs = [base.resize((s, s), Image.LANCZOS) for s in sizes]
    imgs[0].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[1:])
