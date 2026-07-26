"""The v3 design contract in code must not drift from the contract on paper.

``obsauto/design_v3.py`` is a transcription of section 05 of the mockup, kept as
``design/ui-v3/BUILD-SPEC.md``. Transcriptions rot silently, so this test reads
the markdown back and compares it against the module: every colour token, every
config key, and the geometry the panes are drawn at.

Also asserts every key the Settings pane is specified to write actually exists
in ``config.DEFAULTS`` - a renamed key would otherwise orphan a field with no
error until someone opened that pane.

No GUI, no OBS, no desktop session needed.

    python tests/test_design_v3.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import design_v3 as d
from obsauto.config import DEFAULTS

SPEC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "design", "ui-v3", "BUILD-SPEC.md",
)

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), detail))


def section(text, heading):
    """The body of one '## heading' block of the spec."""
    parts = re.split(r"^## ", text, flags=re.M)
    for part in parts:
        if part.startswith(heading):
            return part
    return ""


with open(SPEC, encoding="utf-8") as f:
    spec_text = f.read()

check("BUILD-SPEC.md present", bool(spec_text), SPEC)

# ---- colour tokens -------------------------------------------------------
# "No other hues exist in this app" - so the module's palette and the spec's
# table must be the same set, not merely overlapping.
spec_colours = set(re.findall(r"`(#[0-9A-Fa-f]{6})`", section(spec_text, "Colour tokens")))
module_colours = {v.upper() for v in d.COLORS.values()}
check("colour tokens match the spec table",
      spec_colours == module_colours,
      f"spec-only={sorted(spec_colours - module_colours)} module-only={sorted(module_colours - spec_colours)}")

check("ember is not reused as a general accent",
      d.EMBER not in (d.ACCENT, d.ACCENT_TEXT) and d.HERO_STATES["disconnected"]["tint"] == d.EMBER)

# ---- config map ----------------------------------------------------------
spec_keys = set(re.findall(r"`([a-z_]+(?:\[\])?)`", section(spec_text, "Config map")))
spec_keys = {k.rstrip("[]") for k in spec_keys} - {"config", "json", "defaults"}
module_keys = {key for _, key, _, _ in d.CONFIG_MAP}
check("config map matches the spec table",
      spec_keys == module_keys,
      f"spec-only={sorted(spec_keys - module_keys)} module-only={sorted(module_keys - spec_keys)}")

missing = sorted(k for k in module_keys if k not in DEFAULTS)
check("every mapped key exists in config.DEFAULTS", not missing, f"missing={missing}")

# The spec pins three defaults by name; a drift here changes what the pane shows.
check("reconnect_interval_seconds default is 10", DEFAULTS["reconnect_interval_seconds"] == 10)
check("min_clip_seconds default is 10", DEFAULTS["min_clip_seconds"] == 10)
check("idle_timeout_seconds default is 4", DEFAULTS["idle_timeout_seconds"] == 4)
check("poll_interval_seconds default is 1", DEFAULTS["poll_interval_seconds"] == 1)

# "Every *_seconds key is in seconds - render the unit suffix in every field."
unlabelled = sorted(k for _, k, _, u in d.CONFIG_MAP if k.endswith("_seconds") and u != "seconds")
check("every *_seconds control carries a unit", not unlabelled, f"unlabelled={unlabelled}")

check("settings sections cover every mapped control",
      {s for _, _, s, _ in d.CONFIG_MAP} <= set(d.SETTINGS_SECTIONS))

# ---- geometry ------------------------------------------------------------
check("core window is 1280x808", (d.WIDTH, d.HEIGHT) == (1280, 808))
check("minimum window is 1080x700", (d.MIN_WIDTH, d.MIN_HEIGHT) == (1080, 700))
check("rail is 232 wide", d.RAIL_W == 232)
check("titlebar is 46 tall", d.TITLEBAR_H == 46)

# Frames 2b-2e are drawn at "its true size: 1048x746" - that must fall out of
# the chassis numbers rather than being a fourth independent constant.
check("pane size derives to the frames' 1048x746",
      (d.PANE_W, d.PANE_H) == (1048, 746), f"got {(d.PANE_W, d.PANE_H)}")

# "Nesting rule: inner = outer - padding" - radii must descend, never cross.
radii = [d.RADIUS_TRAY, d.RADIUS_CORE, d.RADIUS_CARD, d.RADIUS_TILE, d.RADIUS_CONTROL]
check("radii descend tray > core > card > tile > control",
      radii == sorted(radii, reverse=True) and radii == [28, 22, 17, 12, 9], radii)

check("tray inset reconciles tray and core radii",
      d.RADIUS_TRAY - d.TRAY_INSET == d.RADIUS_CORE)

# ---- alpha ranges --------------------------------------------------------
for name, rng in [("hairline", d.HAIRLINE_ALPHA), ("tint", d.TINT_ALPHA),
                  ("panel-over-backdrop", d.PANEL_OVER_BACKDROP_ALPHA)]:
    check(f"{name} alpha range is ordered and < 1", rng[0] < rng[1] < 1.0, rng)

check("panels over the backdrop are never opaque",
      d.PANEL_OVER_BACKDROP_ALPHA[1] < 1.0)

# over() has to actually composite, not pass through.
check("over() composites toward the ground",
      d.over(d.ACCENT, 0.0, d.CARD_CORE).upper() == d.CARD_CORE
      and d.over(d.ACCENT, 1.0, d.CARD_CORE).upper() == d.ACCENT
      and d.over(d.ACCENT, 0.5, d.CARD_CORE) not in (d.ACCENT, d.CARD_CORE))

check("hairline() never returns a solid grey",
      len(set(d._hex_to_rgb(d.hairline()))) > 1, d.hairline())

# ---- icons ---------------------------------------------------------------
# "The only Fill glyphs are ph-circle and ph-square."
check("fill weight is restricted to circle and square",
      set(d.ICON_FILL_ONLY) == {"circle", "square"})
check("every pane has a rail icon",
      all(p in d.ICONS for p in d.PANES), sorted(set(d.PANES) - set(d.ICONS)))
check("every pane has a title", all(p in d.PANE_TITLES for p in d.PANES))

# ---- hero states ---------------------------------------------------------
check("four hero states, one enum",
      set(d.HERO_STATES) == {"recording", "watching", "paused", "disconnected"})
check("idle-watching carries no tint", d.HERO_STATES["watching"]["tint"] is None)
check("every hero state names its actions",
      all(s["actions"] for s in d.HERO_STATES.values()))

# ---- the performance guard ----------------------------------------------
# The motion cycles are recorded for provenance only. If something starts
# reading them, the per-frame composite is back - see CLAUDE.md and
# tests/test_frame_pacing.py.
check("background motion values are quarantined, not in BACKGROUND",
      "blob_cycle_s" not in d.BACKGROUND and "pointer_spotlight_px" not in d.BACKGROUND)
check("randomisation requirement is still expressible",
      d.BACKGROUND["blobs_per_surface"] == 3 and d.BACKGROUND["star_layers"] == 2)

gui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "obsauto", "gui.py")
with open(gui_path, encoding="utf-8") as f:
    gui_src = f.read()
check("gui.py does not read the quarantined motion values",
      "BACKGROUND_MOTION_UNUSED" not in gui_src)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

sys.exit(0 if passed_all else 1)
