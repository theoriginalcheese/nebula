# t008 — Customise mode (step 9, frame 6.8)

Let the Dashboard's blocks be reordered and resized, and persist it.

## The contract, already in code

`obsauto/design_v3.py` owns every number — do not invent any:

```
GRID_COLS = 12          GRID_GAP = 16
SPANS = (6, 8, 12)      SPAN_LABELS = {6: "½", 8: "⅔", 12: "Full"}
GRID_OVERLAY_ALPHA = 0.10     # "12 col, 1px accent @ .10, gap 16"
```

Only those three spans exist. There is no 3-column or 9-column option.

Persistence is **`dashboard_layout` in config.json**, already live and already
the v3 format:

```json
[{"id":"hero","span":12},{"id":"activity","span":6},
 {"id":"stats","span":6},{"id":"replay","span":6}]
```

Read `tests/test_customise.py` before starting — it encodes the v3 rules and the
same ones apply.

## Two rules that came from real v3 bugs

1. **A hand-edited config can never lose a panel.** v3's `_saved_layout()` drops
   unknown ids and appends any missing ones, so an out-of-date or corrupted
   `dashboard_layout` still yields a complete dashboard. Reproduce that.
2. **A removed block must not break its writers.** v3 shipped a bug where
   removing a panel left periodic timers writing to dead widgets forever — the
   activity log and the hero buttons both did it. Anything that updates a block
   must check the block still exists.

## What to build

- A **Customise** toggle on the Dashboard that enters edit mode.
- In edit mode: show the 12-column overlay (1px accent at `--grid-overlay-alpha`,
  `--grid-gap` between columns), make blocks draggable to reorder, and give each
  a span control offering only ½ / ⅔ / Full.
- Leaving edit mode writes `dashboard_layout` via the existing settings path and
  the layout survives a restart.
- Reordering is **`transform` only** — no width/height/top/left animation. The
  260ms sibling reflow the spec asks for uses `--pane-change-ms` and `--ease`.

## ⛔ File ownership

**You may edit only** `spike/web/app.js`, `spike/web/app.css`,
`spike/web/index.html`, and you may ADD `tests/test_v4_customise.py`.

Need an Api method to read or write `dashboard_layout`? **Say so in your report
— do not add it.** `spike/app.py` already has `set_setting` and `config`; check
whether they suffice before asking.

## Rules

- Tokens only. No hand-typed hex, radii, durations or easings. A missing value
  goes in `obsauto/design_v3.py` then `python spike/gen_tokens.py`.
- No fabricated numbers. Two-layer cards.
- `transform` and `opacity` only.

## Definition of done

The standard gate, plus:
- `python tools/gpu_ab.py` — visible must not regress past ~26% (baseline 24.1%)
- screenshots of edit mode **open and described**, showing the column overlay
- reorder, leave edit mode, restart the app, confirm the layout persisted
- a test covering the "never lose a panel" rule headlessly
