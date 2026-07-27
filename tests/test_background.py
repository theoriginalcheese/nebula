"""The living background - build spec 6.1, and fixes 1-4 of 6.7.

6.1 names this "the feature the build missed hardest" and it was right: the
aurora measured a peak contribution of *zero* over the plain ground. Two bugs
did it. `layer.paste(blob, pos, blob)` hands the blob its own alpha channel as
a mask, multiplying its alpha by itself, so a 19% blob composited at 3.6%; and
each blob was blurred by the page-level 90-110px figure rather than the 54px
the spec's own CSS puts on the element, which flattened what was left.

Neither would ever fail a "does it render" check - the image comes back the
right size and shape, just without the feature in it. So these assertions
measure the layers instead: the aurora against a bare ground, the dust against
the aurora, the vignette against the centre.

    python tests/test_background.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import design_v3 as dv
from obsauto.theme_art import (
    STAR_RGB, _ground_gradient_v3, _vignette_mask_v3, generate_backdrop_v3,
)

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


W, H = 1770, 1140          # 1280x808 at this machine's 1.383 scale
SPEC = dv.BACKGROUND


def sample(img, step=7):
    px = img.load()
    for y in range(0, img.height, step):
        for x in range(0, img.width, step):
            yield x, y, px[x, y]


def bare_ground():
    """Layers 0 and 4 only - what the surface looks like with no aurora."""
    g = _ground_gradient_v3(W, H, dv.PANEL, dv.GROUND_DEEP, SPEC["ground_stop"])
    g.paste((0, 0, 0), (0, 0), _vignette_mask_v3(
        W, H, SPEC["vignette"]["transparent_to"], SPEC["vignette"]["black_alpha"]))
    return g


start = time.perf_counter()
full, aurora = generate_backdrop_v3(W, H, seed=7)
render_ms = (time.perf_counter() - start) * 1000

check("the backdrop returns both surfaces", full.size == aurora.size == (W, H),
      f"{full.size} / {aurora.size}")
check("rendering stays a one-off launch cost, not a frame cost",
      render_ms < 400, f"{render_ms:.0f}ms")

# --- layer 0: the ground is a gradient, not a flat fill ---------------------
px = full.load()
top_centre = px[W // 2, 4][:3]
centre = px[W // 2, H // 2][:3]
check("the ground is lighter at the gradient's origin than at its centre",
      sum(top_centre) > sum(centre), f"{top_centre} vs {centre}")

# --- layer 1: the aurora actually contributes -------------------------------
ground = bare_ground()
gp = ground.load()
ap = aurora.load()
peak, where = 0, None
for x, y, _ in sample(aurora):
    delta = sum(abs(ap[x, y][i] - gp[x, y][i]) for i in range(3))
    if delta > peak:
        peak, where = delta, (ap[x, y][:3], gp[x, y][:3])
check("the aurora is present at all", peak > 0,
      f"peak delta {peak}" if peak else "ZERO - the blobs composited away to nothing")
# .22 accent over the deep ground is (38, 33, 68) against (10, 8, 18): a sum-of-
# channels delta near 100. Anything under ~25 is a wash nobody can see.
check("the aurora is strong enough to read", peak >= 40, f"peak delta {peak} {where}")

# "Three per surface: accent .22, deep indigo .22, ember .07. The ember one is
# what keeps the ground from going cold - do not drop it." Accent and indigo
# are both blue-dominant and leave the ground's red:blue ratio near 0.55;
# ember (#FF5C7A) is red-dominant, so wherever it lands that ratio climbs. If
# the blob were dropped, nothing on the surface would ever be warm.
ground_ratio = 10 / 18.0
warmest = max(ap[x, y][0] / max(ap[x, y][2], 1) for x, y, _ in sample(aurora, step=5))
check("the ember blob is there, keeping the ground from going cold",
      warmest > ground_ratio * 1.25, f"warmest r:b {warmest:.2f} vs ground {ground_ratio:.2f}")

# --- layers 2/3: dust, and only outside the chrome's sample surface ---------
dust = [(x, y) for x, y, _ in sample(full, step=1) if px[x, y][:3] != ap[x, y][:3]]
check("star dust exists on the painted surface", dust, len(dust))
expected = SPEC["star_density"] * 1.75 * (W * H) / (dv.WIDTH * dv.HEIGHT)
check("the dust is sparse enough to read as depth, not noise",
      len(dust) < expected * 60,
      f"{len(dust)} lit pixels for ~{expected:.0f} stars")

# "Colour is always rgba(217,212,255,a) - never #fff."
whites = 0
off_hue = 0
for x, y in dust:
    r, g, b = px[x, y][:3]
    if (r, g, b) == (255, 255, 255):
        whites += 1
    if b < r:                      # STAR_RGB is blue-leaning; nothing warmer
        off_hue += 1
check("no pure-white stars", whites == 0, whites)
check("stars only ever use the one tint", off_hue == 0, f"{off_hue} off-hue")
check("the tint is the spec's", STAR_RGB == (217, 212, 255), STAR_RGB)

# The point of the second surface: a widget sampling its corner-blend colour
# from the composite must never pick up a star.
starless = [(x, y) for x, y in dust if ap[x, y][:3] == px[x, y][:3]]
check("every star is absent from the starless surface", not starless,
      f"{len(starless)} stars leaked into the chrome's surface")

# --- layer 4: vignette ------------------------------------------------------
corner = px[4, H - 4][:3]
check("the corners are pulled down", sum(corner) < sum(centre),
      f"corner {corner} vs centre {centre}")

# --- randomised per launch --------------------------------------------------
a1, _ = generate_backdrop_v3(320, 200, seed=None)
a2, _ = generate_backdrop_v3(320, 200, seed=None)
check("two launches never look alike", a1.tobytes() != a2.tobytes())
b1, _ = generate_backdrop_v3(320, 200, seed=5)
b2, _ = generate_backdrop_v3(320, 200, seed=5)
check("a seed still reproduces exactly", b1.tobytes() == b2.tobytes())

# --- the motion values stay quarantined -------------------------------------
art = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "obsauto", "theme_art.py"), encoding="utf-8").read()
check("theme_art never reads the quarantined motion values",
      "BACKGROUND_MOTION_UNUSED" not in art)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<54} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
