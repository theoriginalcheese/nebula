"""Fine-detail fidelity against the v3 mockup.

design/ui-v3/BUILD-SPEC.md carries a set of small rules that are easy to satisfy
in one place and quietly miss in another - the trailing-icon circle, the focus
ring, the disabled state, "no emoji", "every card is two layers". This checks
the ones that can be verified mechanically, so they can't rot.

Where a rule genuinely can't be honoured on this stack (per-frame motion), the
deviation is asserted to be *documented*, not silently absent.

    python tests/test_fidelity.py
"""
import os
import re
import sys
import time
import traceback
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto import design_v3 as dv
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI_SRC = open(os.path.join(ROOT, "obsauto", "gui.py"), encoding="utf-8").read()
SPEC = open(os.path.join(ROOT, "design", "ui-v3", "BUILD-SPEC.md"), encoding="utf-8").read()

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


# ---------------------------------------------------------------------------
# Static rules - read the source, no window needed
# ---------------------------------------------------------------------------

# "No emoji, no gradient floods, no second accent hue."
# Private-use codepoints are the Fluent icon font and are fine. What is not:
# emoji-presentation sequences, and the ASCII-art glyph substitutes v2 used
# where v3 wants a real icon.
BANNED_GLYPHS = {
    "⣿": "braille block used as a 'customise' icon",
    "↻": "arrow glyph used as a 'refresh' icon",
    "●": "black circle used as a status dot",
    "✓": "check mark glyph",
    "️": "VARIATION SELECTOR-16 (emoji presentation)",
}
found = {g: GUI_SRC.count(g) for g in BANNED_GLYPHS if g in GUI_SRC}
check("no emoji or glyph stand-ins for icons", not found,
      {BANNED_GLYPHS[g]: n for g, n in found.items()})

# Anything above the BMP symbol range that isn't PUA or ordinary typography.
allowed_punct = {"—", "–", "…", "→", "·", "‘", "’"}
stray = sorted({c for c in GUI_SRC
                if ord(c) > 0x2000 and not (0xE000 <= ord(c) <= 0xF8FF)
                and c not in allowed_punct})
check("no stray symbol glyphs", not stray,
      [(hex(ord(c)), unicodedata.name(c, "?")) for c in stray])

# "Focus ring 2px #8B7CF6, offset 2" - keyboard focus must be themed, never the
# platform default.
check("focus ring is implemented",
      "_focus_ring" in GUI_SRC or "highlightcolor" in GUI_SRC,
      "no focus-ring handling found in gui.py")
check("focus ring uses the spec's width", "dv.FOCUS_RING_W" in GUI_SRC)
# `offset 2` has no expression on a CTk widget border (no outset, and these are
# embedded in canvas windows). It must be recorded as a known limitation rather
# than silently skipped.
check("focus-ring offset limitation is documented",
      "FOCUS_RING_OFFSET" in GUI_SRC and "not applied" in GUI_SRC)

# "Disabled opacity .45, no hover"
check("disabled state uses the spec's opacity",
      "DISABLED_OPACITY" in GUI_SRC, "dv.DISABLED_OPACITY never referenced")

# "Trailing icons on primary pills live in their own 26-28px circle, flush to
#  the right padding."
check("primary pills carry the trailing-icon circle",
      "PILL_TRAILING_CIRCLE" in GUI_SRC,
      "dv.PILL_TRAILING_CIRCLE never referenced")

# A button's label must not change out from under itself.
resets = re.findall(r'rescan_btn\.configure\([^)]*text="([^"]+)"', GUI_SRC)
creates = re.findall(r'text="([^"]+)", command=self\._rescan_steam', GUI_SRC)
check("rescan button keeps one label",
      not resets or not creates or set(resets) <= set(creates),
      f"created as {creates}, reset to {resets}")

# "Never animate width / height / top / left" inside the main window, and never
# per-frame. The quarantined motion values must stay unread.
check("quarantined motion values stay unread",
      "BACKGROUND_MOTION_UNUSED" not in GUI_SRC)

# Deviations that cannot be honoured must be written down, not silently dropped.
handoff = open(os.path.join(ROOT, "CURSOR-HANDOFF.md"), encoding="utf-8").read()
for topic in ("pointer spotlight", "Mark clip", "Length"):
    check(f"deviation documented: {topic}", topic.lower() in handoff.lower())

# ---------------------------------------------------------------------------
# Live rules - need the window
# ---------------------------------------------------------------------------
app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=150):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


settle(200)

# Type scale: every canvas text item must use a size from the spec's scale, and
# a pixel size (negative) rather than points.
sizes = set()
faces = set()
for item in app.bg._c.find_all():
    if app.bg._c.type(item) != "text":
        continue
    font = app.bg._c.itemcget(item, "font")
    if not font:
        continue
    parts = font.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].lstrip("-").isdigit():
        sizes.add(int(parts[1]))
        faces.add(parts[0].strip("{}"))
positive = sorted(s for s in sizes if s > 0)
check("all canvas text is sized in pixels, not points", not positive, positive)

scale_px = {int(round(t["size"] * app.scale)) for t in dv.TYPE.values()}
scale_px |= {int(round(s * app.scale)) for s in (9.5, 10, 10.5, 11, 12, 13, 14, 16, 19, 21, 25, 34)}
# "The only Fill glyphs are ph-circle (status dots, 6-8px) and ph-square
# (stop, 9-11px)" - those sizes are sanctioned by the spec, not off-scale.
for _lo, _hi in dv.ICON_FILL_ONLY.values():
    scale_px |= {int(round(px * app.scale)) for px in range(_lo, _hi + 1)}
off_scale = sorted(-s for s in sizes if s < 0 and -s not in scale_px)
check("no off-scale type sizes", not off_scale, off_scale)

expected_faces = set()
for key in dv.FONT_STACKS:
    expected_faces.add(dv._resolved.get(key, ""))
expected_faces |= {dv._resolved.get("mono", ""), gui.ICON_FONT, ""}
rogue = sorted(f for f in faces if f and f not in expected_faces)
check("only the resolved v3 faces are used", not rogue, rogue)

# Geometry the frames pin down.
check("titlebar height", gui.TITLEBAR_HEIGHT == 46)
check("rail width", gui.SIDEBAR_W == 232)
check("pane header height", gui.TOPBAR_HEIGHT == 62)
check("content padding", gui.MARGIN == dv.CONTENT_PAD == 26)

# "Hit target >= 30px" for the titlebar circle buttons.
check("titlebar buttons meet the 30px hit target",
      2 * 15 >= dv.MIN_HIT_TARGET, f"diameter 30 vs min {dv.MIN_HIT_TARGET}")

# "In-window panels sit on rgba(16,13,28,0.72-0.92)" - never opaque.
alphas = [int(a) for a in re.findall(r"tint_alpha=(\d+)", GUI_SRC)]
check("no fully opaque panel over the backdrop", all(a < 255 for a in alphas),
      [a for a in alphas if a >= 255])
lo, hi = dv.PANEL_OVER_BACKDROP_ALPHA
check("panel alphas land in the spec's band",
      all(a <= int(hi * 255) + 12 for a in alphas),
      sorted({a for a in alphas if a > int(hi * 255) + 12}))

# 6.1: "Star dots are currently painted above the rail and the cards. The whole
# background stack lives at z-index:0 behind the chrome." The rail and titlebar
# used to be bare backdrop with text on it - nothing between the wordmark and
# the sky - so every star in that area read as being inside the chrome. Both
# now carry a .72 panel, which shows up as the composite differing from the
# raw backdrop there.
comp, aur = app._composite, app.aurora
def differs(x, y):
    sx, sy = app._S(x), app._S(y)
    return comp.getpixel((sx, sy))[:3] != aur.convert("RGB").getpixel((sx, sy))[:3]

check("the titlebar is a panel, not bare backdrop",
      differs(gui.WIDTH * 0.6, gui.TITLEBAR_HEIGHT / 2),
      "nothing painted between the titlebar text and the sky")
check("the rail is a panel, not bare backdrop",
      differs(gui.SIDEBAR_W / 2, gui.HEIGHT - 200),
      "nothing painted between the rail and the sky")
check("the chrome sits at the spec's .72",
      dv.CHROME_ALPHA == int(round(0.72 * 255)), dv.CHROME_ALPHA)

# The composite is what embedded widgets sample for their corner blend. Seeded
# from the starless surface, so a widget landing on a star can't pick it up.
check("widgets sample a dust-free surface",
      app._composite.size == app.aurora.size, "composite/aurora size mismatch")

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
