"""Customise mode layout rules for the v4 spike (6.8).

The web UI reads ``dashboard_layout`` through ``Api.config()`` and writes it
with ``set_dashboard_layout``. These checks mirror ``tests/test_customise.py``
for the normalisation contract — a hand-edited config must never lose a panel.

    python tests/test_v4_customise.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import design_v3 as dv
from spike.app import (
    SPIKE_DASH_BLOCKS,
    SPIKE_DEFAULT_GRID,
    normalise_dashboard_layout,
)

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


check("twelve columns in the contract", dv.GRID_COLS == 12, dv.GRID_COLS)
check("grid gutter is 16", dv.GRID_GAP == 16, dv.GRID_GAP)
check("three spans only", dv.SPANS == (6, 8, 12), dv.SPANS)
check("handle strip is 26px", dv.HANDLE_STRIP_H == 26, dv.HANDLE_STRIP_H)

# Overlap is impossible when packing left-to-right into twelve columns.
def overlaps(layout):
    cols = dv.GRID_COLS
    y = 0
    row_h = 0
    used = 0
    row_x = []
    rects = {}
    gap = dv.GRID_GAP
    col_w = (1000 - gap * (cols - 1)) / cols

    def width_of(span):
        return col_w * span + gap * (span - 1)

    for item in layout:
        span = cols if item["id"] == "hero" else item["span"]
        if used + span > cols:
            y += row_h + gap
            row_h = 0
            used = 0
            row_x = []
        x = sum(row_x) + len(row_x) * gap if row_x else 0
        w = width_of(span)
        h = 100
        rects[item["id"]] = (x, y, w, h)
        row_x.append(w)
        used += span
        row_h = max(row_h, h)
    boxes = [(k, *v) for k, v in rects.items()]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            _, ax0, ay0, aw, ah = boxes[i]
            _, bx0, by0, bw, bh = boxes[j]
            ax1, ay1 = ax0 + aw, ay0 + ah
            bx1, by1 = bx0 + bw, by0 + bh
            if ax0 < bx1 - 0.5 and bx0 < ax1 - 0.5 and ay0 < by1 - 0.5 and by0 < ay1 - 0.5:
                return "%s / %s" % (boxes[i][0], boxes[j][0])
    return None


bad = []
for a in dv.SPANS:
    for b in dv.SPANS:
        layout = normalise_dashboard_layout([
            {"id": "hero", "span": 12},
            {"id": "stats", "span": a},
            {"id": "activity", "span": b},
        ])
        clash = overlaps(layout)
        if clash:
            bad.append((a, b, clash))
check("no span combination overlaps", not bad, bad[:3])

# --- never lose a panel ---------------------------------------------------
empty = normalise_dashboard_layout([])
check("empty file yields a full dashboard",
      {it["id"] for it in empty} == set(SPIKE_DASH_BLOCKS), empty)

mangled = normalise_dashboard_layout([
    {"id": "stats", "span": 6},
    {"id": "nonsense", "span": 12},
    {"name": "activity", "span": 1},
])
ids = [it["id"] for it in mangled]
check("unknown ids are dropped", "nonsense" not in ids, ids)
check("legacy span 1 migrates to half width",
      next(it for it in mangled if it["id"] == "activity")["span"] == 6,
      mangled)
check("missing hero is appended",
      "hero" in ids, ids)
check("every known block present once",
      sorted(ids) == sorted(SPIKE_DASH_BLOCKS), ids)

check("hero stays full width whatever you ask",
      all(it["span"] == dv.GRID_COLS for it in mangled if it["id"] == "hero"),
      mangled)

dupes = normalise_dashboard_layout([
    {"id": "hero", "span": 12},
    {"id": "stats", "span": 6},
    {"id": "stats", "span": 8},
    {"id": "activity", "span": 12},
])
check("duplicate ids keep the first entry",
      sum(1 for it in dupes if it["id"] == "stats") == 1
      and next(it for it in dupes if it["id"] == "stats")["span"] == 6,
      dupes)

check("default grid matches the spike catalogue",
      [it["id"] for it in SPIKE_DEFAULT_GRID] == list(SPIKE_DASH_BLOCKS),
      SPIKE_DEFAULT_GRID)

check("260ms reflow is recorded, not wired to canvas",
      "REFLOW_MS_UNUSED" in open(
          os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "obsauto", "design_v3.py"),
          encoding="utf-8").read(),
      "design_v3.py")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print("%s  %-52s %s" % ("PASS" if passed else "FAIL", name, detail))
print("\n%s (%d checks)" % ("ALL PASS" if passed_all else "FAILURES PRESENT", len(results)))
sys.exit(0 if passed_all else 1)
