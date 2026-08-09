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

# --- one geometry, every size -------------------------------------------
# Everything here is a ratio of `size`, so the mark is identical at 16px and
# 256px rather than being one drawing scaled twice.
RING_RX = 0.46          # x size - gold ring
RING_RATIO = 0.60       # ry / rx
RING_TILT = 22
RING_W = 0.053          # x size - stroke width
INNER_RX = 0.406        # x size - thin violet ring under the gold one
INNER_RATIO = 0.404
INNER_TILT = -48
INNER_W = 0.023
SPARK_R = 0.34          # x size

ARC_SPAN = 56           # degrees of the ring lit while recording
ARC_PERIOD_S = 3.8      # seconds for one full tour

GOLD_LIT = (255, 232, 188, 255)   # the arc itself
SLASH = (183, 177, 208, 255)      # disconnected stroke


def _mix(c1, c2, t):
    """Blend two RGBA colours, keeping c1's alpha."""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1[:3], c2[:3])) + (c1[3],)


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


def _draw_tilted_arc(base_img, cx, cy, rx, ry, tilt_deg, start, end, color, width):
    """A lit segment of the orbit. Angles are degrees, 0 deg at 3 o'clock,
    measured before the tilt is applied.

    Same trick as _draw_tilted_ellipse - draw upright on its own layer, rotate
    the layer, composite - but with `arc` instead of `ellipse`. This is the
    only new drawing primitive the recording state needs.
    """
    pad = int(max(rx, ry) * 2.4)
    layer = Image.new("RGBA", (pad, pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    l = pad / 2
    d.arc([l - rx, l - ry, l + rx, l + ry], start, end, fill=color, width=width)
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
    """Resting mark: sparkle + one gold orbit. mark.png and the hover frames.

    Reads the same RING_/SPARK_ ratios as the tray and tile, so there is one
    geometry rather than a second copy that drifts. What it deliberately does
    *not* draw is the thin inner ring: this is the mark for the web titlebar,
    where a 64px render is displayed at ~18 CSS px, and a second ring at that
    size is a smudge rather than a detail. render_state_icon's detail gate
    makes the same call from the other direction.

    ``ring_rotation`` offsets the orbit tilt. Nothing in the app passes it any
    more - the hover animation is render_animation_frame's job - but it costs
    nothing to keep for a caller that wants a tilted still.
    """
    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = s / 2

    ring_w = max(int(s * RING_W), 2)
    _draw_tilted_ellipse(
        img, cx, cy, s * RING_RX, s * RING_RX * RING_RATIO,
        RING_TILT + ring_rotation, GOLD, ring_w)

    _draw_sparkle(draw, cx, cy, s * SPARK_R, VIOLET)
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

NEUTRAL = (154, 147, 196, 255)   # matches design_v3.TEXT_SECONDARY

TRAY_STATES = ("idle", "recording", "disconnected")

# No red anywhere in the mark. In the web chrome ember means *something is
# wrong* - `.card.hero.is-ember` is the disconnected state, and tokens.css
# keeps --ember out of the accent presets so a real disconnection still reads
# as one. Using the same red for "recording" in the tray gave one colour two
# opposite meanings. What changes between states now is motion and saturation:
# still at rest, a lit arc touring the gold ring while recording, chroma
# drained and slashed when the connection drops. The sparkle stays violet
# throughout, which is the one thing the brand should never trade away.


def render_state_icon(state, size=64, t=0.0, supersample=4, detail_size=None):
    """The tray mark, transparent ground.

    ``t`` in [0, 1) drives the recording arc and is ignored by the other two
    states, so idle and disconnected still render once and cache.

    ``detail_size`` is the size the result will actually be *looked at*, when
    that differs from the size it is drawn at. render_tile_icon draws the mark
    at supersampled resolution with supersample=1, so `size` there is ~43px
    for a 16px tile - and judging "can this resolve a second ring?" on 43
    rather than on 11 put the thin ring into exactly the entries the spec says
    it should drop out of.
    """
    if state not in TRAY_STATES:
        raise ValueError(f"unknown tray state: {state!r}")
    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = s / 2
    # Below 32px, one ring only - the second cannot resolve and reads as smear.
    detailed = (size if detail_size is None else detail_size) >= 32
    dead = state == "disconnected"

    spark = _mix(VIOLET, NEUTRAL, 0.78) if dead else VIOLET
    ring = _mix(GOLD, NEUTRAL, 0.85) if dead else GOLD

    rx, ry = s * RING_RX, s * RING_RX * RING_RATIO
    ring_w = max(int(s * RING_W), 2)

    if detailed:
        _draw_tilted_ellipse(img, cx, cy, s * INNER_RX, s * INNER_RX * INNER_RATIO,
                             INNER_TILT, _with_alpha(spark, 128),
                             max(int(s * INNER_W), 1))

    if state == "recording":
        # The ring dims and one lit segment tours it. Motion is the state.
        _draw_tilted_ellipse(img, cx, cy, rx, ry, RING_TILT,
                             _with_alpha(ring, 140), ring_w)
        head = 360.0 * (t % 1.0)
        _draw_tilted_arc(img, cx, cy, rx, ry, RING_TILT,
                         head, head + ARC_SPAN, GOLD_LIT, ring_w)
    else:
        _draw_tilted_ellipse(img, cx, cy, rx, ry, RING_TILT, ring, ring_w)

    _draw_sparkle(draw, cx, cy, s * SPARK_R, spark)      # violet, always

    if dead:
        pad = s * 0.14
        ends = [(pad, s - pad), (s - pad, pad)]
        # Punch a gap through the mark first so the slash separates from it.
        # ImageDraw writes pixels rather than compositing, so a zero-alpha line
        # genuinely erases. Both widths are FIXED ratios - do not scale them up
        # at small sizes or the gap swallows the sparkle at 16px.
        draw.line(ends, fill=(0, 0, 0, 0), width=max(int(s * 0.145), 3))
        draw.line(ends, fill=SLASH, width=max(int(s * 0.072), 2))

    return img.resize((size, size), Image.LANCZOS)


def generate_state_icons(size=64):
    return {state: render_state_icon(state, size=size) for state in TRAY_STATES}


def generate_recording_frames(size=64, fps=10):
    """One loop of the arc.

    10fps is plenty for a drift this slow - 38 frames, rendered once and
    cached rather than redrawn live. Stop the timer and drop back to the
    cached idle image the moment recording ends.
    """
    n = max(int(round(ARC_PERIOD_S * fps)), 1)
    return [render_state_icon("recording", size=size, t=i / float(n))
            for i in range(n)]


# --- the tiled variant: same mark, on the app's own sky ------------------
# Two different jobs on one taskbar. The taskbar button and the .ico get a
# body - a rounded corner and the sky behind it. The tray gets the
# transparent mark, because a tile there would fight every other tray glyph.

TILE_BG = (14, 15, 26, 255)        # the app's ground
TILE_GLOW_A = (139, 124, 246)      # violet, upper left
TILE_GLOW_B = (94, 168, 205)       # cyan, lower right
TILE_RADIUS = 0.22                 # x size - corner radius
MARK_INSET = 0.16                  # x size - padding around the mark


def _deep_field(s):
    """The app's sky, at icon scale."""
    tile = Image.new("RGBA", (s, s), TILE_BG)
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse([0.00 * s, 0.02 * s, 0.68 * s, 0.54 * s], fill=TILE_GLOW_A + (64,))
    g.ellipse([0.42 * s, 0.50 * s, 1.02 * s, 0.98 * s], fill=TILE_GLOW_B + (38,))
    tile.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius=s * 0.14)))
    return tile


def render_tile_icon(state="idle", size=256, t=0.0, supersample=4):
    """The mark with a body - taskbar button, .ico, anywhere it needs one."""
    s = size * supersample
    tile = _deep_field(s)

    # Clip to the rounded square.
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, s - 1, s - 1], radius=int(s * TILE_RADIUS), fill=255)
    tile.putalpha(mask)

    # Hairline of light along the edge - what makes it read as a real tile.
    edge = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(edge).rounded_rectangle(
        [0, 0, s - 1, s - 1], radius=int(s * TILE_RADIUS),
        outline=(245, 243, 255, 28), width=max(int(s * 0.006), 1))
    tile.alpha_composite(edge)

    # The mark itself - already supersampled, so ask for no second pass, but
    # tell it the size it will be seen at so the detail gate judges that.
    inner = int(s * (1 - 2 * MARK_INSET))
    mark = render_state_icon(state, size=inner, t=t, supersample=1,
                             detail_size=int(size * (1 - 2 * MARK_INSET)))
    tile.alpha_composite(mark, (int(s * MARK_INSET), int(s * MARK_INSET)))
    return tile.resize((size, size), Image.LANCZOS)


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


def save_ico(path, sizes=(16, 24, 32, 48, 64, 128, 256), tile=True, state="idle"):
    """Every size drawn at its own size - never one render downsampled.

    The old version rendered once at 256 and resized, which is why the small
    entries went mushy: the thin ring survived as a grey smear instead of
    disappearing cleanly. Rendering each size natively lets the `detailed`
    flag in render_state_icon do the right thing on its own, dropping the
    second ring below 32px where it cannot resolve.
    """
    def one(px):
        return (render_tile_icon(state, size=px) if tile
                else render_state_icon(state, size=px))

    # Largest first, and this is not cosmetic. Pillow's ICO writer drops any
    # requested size larger than the image it is saving from, so handing it
    # the 16px render first silently produced a **single 16px entry** - which
    # is what nebula_icon.ico had been for its whole life, leaving Windows to
    # upscale 16px onto the taskbar and the exe. The file was 702 bytes and
    # nothing ever failed.
    ordered = sorted(sizes, reverse=True)
    imgs = [one(px) for px in ordered]
    imgs[0].save(path, format="ICO", sizes=[(px, px) for px in ordered],
                 append_images=imgs[1:])
    return path
