"""Generates the app's icon: an original sparkle-in-orbit design (inspired by
the common "AI/magic sparkle" icon motif - a four-point star with tilted
orbit rings - but drawn from scratch for Nebula's own violet/gold palette,
not copied from any existing icon asset) plus rotation frames so the mark
can animate on hover.
"""

import math

from PIL import Image, ImageDraw, ImageFilter

VIOLET = (139, 124, 246, 255)   # matches gui.py's ACCENT
VIOLET_SOFT = (185, 174, 249, 255)
GOLD = (245, 166, 35, 255)      # matches gui.py's AMBER
GOLD_SOFT = (255, 200, 110, 220)
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


def _ellipse_point(cx, cy, rx, ry, tilt_deg, angle_deg):
    """Point on a tilted ellipse — for the traveling orbit bead."""
    a = math.radians(angle_deg)
    # Ellipse in local space, then rotate by tilt.
    x = rx * math.cos(a)
    y = ry * math.sin(a)
    t = math.radians(tilt_deg)
    xr = x * math.cos(t) - y * math.sin(t)
    yr = x * math.sin(t) + y * math.cos(t)
    return cx + xr, cy + yr


def _with_alpha(rgba, a):
    r, g, b = rgba[:3]
    return (r, g, b, max(0, min(255, int(a))))


def render_frame(size=256, ring_rotation=0.0, supersample=4):
    """Resting mark: sparkle + one gold orbit. Used for .ico / mark.png."""
    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = s / 2

    ring_w = max(int(s * 0.05), 2)
    _draw_tilted_ellipse(
        img, cx, cy, s * 0.46, s * 0.46 * 0.6, 22 + ring_rotation, GOLD, ring_w)

    _draw_sparkle(draw, cx, cy, s * 0.34, VIOLET)
    return img.resize((size, size), Image.LANCZOS)


def render_animation_frame(size=256, t=0.0, supersample=4):
    """Hover animation — comet orbit, aurora wash, breathing sparkle.

    Designed to read at titlebar size *and* look cinematic in the 128–256px
    showcase GIF. ``t`` is in [0, 1).
    """
    t = t % 1.0
    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = s / 2
    two_pi = math.pi * 2

    # --- aurora wash (soft violet oval, slow counter-spin) ---------------
    wash = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wash)
    wrx, wry = s * 0.42, s * 0.28
    wd.ellipse([cx - wrx, cy - wry, cx + wrx, cy + wry],
               fill=_with_alpha(VIOLET, 55))
    wash = wash.filter(ImageFilter.GaussianBlur(radius=max(s * 0.08, 2)))
    wash = wash.rotate(-25 - 60 * t, resample=Image.BICUBIC, center=(cx, cy))
    img.alpha_composite(wash)

    # --- faint outer counter-ring ---------------------------------------
    _draw_tilted_ellipse(
        img, cx, cy, s * 0.52, s * 0.52 * 0.52,
        -20 - 220 * t, _with_alpha(VIOLET_SOFT, 90), max(int(s * 0.022), 1))

    # --- main gold orbit + bloom ----------------------------------------
    tilt = 24 + 360 * t
    rx, ry = s * 0.44, s * 0.44 * 0.58
    ring_w = max(int(s * 0.05), 2)

    bloom = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    _draw_tilted_ellipse(
        bloom, cx, cy, rx, ry, tilt, _with_alpha(GOLD, 90), max(ring_w * 4, 4))
    bloom = bloom.filter(ImageFilter.GaussianBlur(radius=max(s * 0.035, 1.5)))
    img.alpha_composite(bloom)

    _draw_tilted_ellipse(img, cx, cy, rx, ry, tilt, GOLD, ring_w)

    # --- comet trail (fading beads behind the head) ---------------------
    head_ang = 360 * t
    trail_n = 10
    for i in range(trail_n, 0, -1):
        frac = i / float(trail_n)
        ang = head_ang - frac * 55  # degrees of trail length
        px, py = _ellipse_point(cx, cy, rx, ry, tilt, ang)
        rad = max(s * (0.012 + 0.038 * (1.0 - frac)), 1.2)
        alpha = int(40 + 180 * (1.0 - frac))
        col = GOLD if frac < 0.45 else GOLD_SOFT
        draw.ellipse([px - rad, py - rad, px + rad, py + rad],
                     fill=_with_alpha(col, alpha))

    # Comet head — bright core + halo
    hx, hy = _ellipse_point(cx, cy, rx, ry, tilt, head_ang)
    hr = max(s * 0.07, 2.5)
    halo = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hd.ellipse([hx - hr * 2.2, hy - hr * 2.2, hx + hr * 2.2, hy + hr * 2.2],
               fill=_with_alpha(GOLD, 70))
    halo = halo.filter(ImageFilter.GaussianBlur(radius=max(s * 0.025, 1)))
    img.alpha_composite(halo)
    draw = ImageDraw.Draw(img)
    draw.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=GOLD)
    draw.ellipse([hx - hr * 0.4, hy - hr * 0.4, hx + hr * 0.4, hy + hr * 0.4],
                 fill=WHITE)

    # Opposite pole fleck — keeps the orbit feeling balanced
    ox, oy = _ellipse_point(cx, cy, rx, ry, tilt, head_ang + 180)
    orad = max(s * 0.022, 1)
    draw.ellipse([ox - orad, oy - orad, ox + orad, oy + orad],
                 fill=_with_alpha(VIOLET_SOFT, 160))

    # --- central sparkle (breath + tip glints) --------------------------
    breath = 1.0 + 0.10 * math.sin(t * two_pi)
    twinkle = 12 * math.sin(t * two_pi)
    spark_r = s * 0.33 * breath
    _draw_sparkle(draw, cx, cy, spark_r, VIOLET, rotation_deg=twinkle)

    # Tip glints — four small sparks at the points, phased
    for i in range(4):
        a = math.radians(twinkle + i * 90)
        tip = spark_r * 0.92
        gx = cx + tip * math.cos(a)
        gy = cy + tip * math.sin(a)
        pulse = 0.55 + 0.45 * math.sin(t * two_pi * 2 + i * 1.1)
        gr = max(s * 0.028 * pulse, 1)
        draw.ellipse([gx - gr, gy - gr, gx + gr, gy + gr],
                     fill=_with_alpha(WHITE, int(80 + 140 * pulse)))

    core = s * 0.06 * breath
    draw.ellipse([cx - core, cy - core, cx + core, cy + core],
                 fill=_with_alpha(WHITE, 220))

    return img.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------------------
# v3 tray states (frame 2j)
# ---------------------------------------------------------------------------
# "Tray icon states: idle = accent outline, recording = ember filled,
#  disconnected = neutral with a slash."
#
# This replaces the constantly-spinning tray animation. The spec asks the icon
# to *mean* something - which state the app is in - and a 12fps spin says
# nothing while redrawing the icon 12 times a second forever. Three static
# icons, swapped on state change, carry more information for no ongoing cost.

EMBER = (255, 92, 122, 255)      # matches design_v3.EMBER
NEUTRAL = (154, 147, 196, 255)   # matches design_v3.TEXT_SECONDARY

TRAY_STATES = ("idle", "recording", "disconnected")


def render_state_icon(state, size=64, supersample=4):
    """The tray mark in one of the three v3 states."""
    if state not in TRAY_STATES:
        raise ValueError(f"unknown tray state: {state!r}")
    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = s / 2
    ring_w = max(int(s * 0.05), 2)

    color = {"idle": VIOLET, "recording": EMBER, "disconnected": NEUTRAL}[state]

    _draw_tilted_ellipse(img, cx, cy, s * 0.46, s * 0.46 * 0.6, 22, color, ring_w)

    if state == "recording":
        # Filled: the one state that should read as "live" at a glance.
        _draw_sparkle(draw, cx, cy, s * 0.34, color)
    else:
        # Outline: same silhouette, drawn as a stroke. PIL's polygon has no
        # outline width, so stroke it as a closed line loop.
        points = _four_point_star(cx, cy, s * 0.34, s * 0.34 * 0.34)
        draw.line(points + [points[0]], fill=color, width=max(int(s * 0.035), 2),
                  joint="curve")

    if state == "disconnected":
        # A slash across the whole mark - unmistakable at 16px, where a colour
        # change alone is not.
        pad = s * 0.16
        draw.line([(pad, s - pad), (s - pad, pad)], fill=color,
                  width=max(int(s * 0.075), 2))

    return img.resize((size, size), Image.LANCZOS)


def generate_state_icons(size=64):
    return {state: render_state_icon(state, size=size) for state in TRAY_STATES}


def generate_static_icon(size=256):
    return render_frame(size=size, ring_rotation=0.0)


def generate_animation_frames(size=64, n_frames=48):
    """Hover-GIF frames — denser sampling for a smoother orbit."""
    return [
        render_animation_frame(size=size, t=i / float(n_frames))
        for i in range(n_frames)
    ]


def save_gif(path, size=64, n_frames=48, duration_ms=40):
    """Write the orbit animation as a looping GIF with a transparent ground.

    Soft glow edges cannot survive GIF's 1-bit transparency cleanly — prefer
    :func:`save_webp` for the titlebar. This path keeps a chromakey GIF for
    callers that still want one (hard alpha cut, no green fringe).
    """
    frames = generate_animation_frames(size=size, n_frames=n_frames)
    key_rgb = (0, 255, 0)
    alpha_cut = 24
    sheet = Image.new("RGB", (size * n_frames, size), key_rgb)
    for i, frame in enumerate(frames):
        rgb = Image.new("RGB", frame.size, key_rgb)
        alpha = frame.getchannel("A")
        mask = alpha.point(lambda a: 255 if a >= alpha_cut else 0)
        rgb.paste(frame.convert("RGB"), mask=mask)
        sheet.paste(rgb, (i * size, 0))
    sheet_p = sheet.convert("P", palette=Image.ADAPTIVE, colors=255)
    pal = sheet_p.getpalette() or []
    transparent = 0
    for idx in range(min(256, len(pal) // 3)):
        r, g, b = pal[idx * 3], pal[idx * 3 + 1], pal[idx * 3 + 2]
        if (r, g, b) == key_rgb:
            transparent = idx
            break
    out = []
    for i in range(n_frames):
        tile = sheet_p.crop((i * size, 0, (i + 1) * size, size))
        tile.info["transparency"] = transparent
        out.append(tile)
    out[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=out[1:],
        duration=duration_ms,
        loop=0,
        disposal=2,
        transparency=transparent,
        optimize=False,
    )
    return path


def save_webp(path, size=64, n_frames=48, duration_ms=40, quality=88):
    """Orbit animation as animated WebP — true alpha, seamless on any chrome."""
    frames = generate_animation_frames(size=size, n_frames=n_frames)
    frames[0].save(
        path,
        format="WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        quality=quality,
        method=4,
    )
    return path


def save_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256)):
    base = render_frame(size=256)
    imgs = [base.resize((s, s), Image.LANCZOS) for s in sizes]
    imgs[0].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[1:])
