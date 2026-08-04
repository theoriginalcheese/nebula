# t006 — Toast: three specific changes

Make exactly these three changes to `spike/web/toast.css` (and `toast.html` only
if markup is genuinely required). Do not investigate, do not survey, do not
propose alternatives. The diagnosis is done — this is the edit.

Reference: `shots/t005-toast.png` (current) vs `design/ui-v3/frames/2i.png`.
Anthony's feedback on the current one: **"very blocky and square"**.

## 1. The drain bar must fade at both ends

Currently a 1px ember line runs nearly the full width and hard-stops at each
end. Two hard horizontal terminations across the widest part of the panel is
the single biggest reason it reads square.

BUILD-SPEC: *"Rules and dividers fade at both ends over 32–48px. No
hard-stopped 1px greys."*

Use a `linear-gradient` mask or a gradient background that fades to transparent
over `var(--rule-fade)` at each end. The bar still has to shrink as the drain
runs — keep that on `transform: scaleX()`, not `width`.

## 2. Move from the tile radius family to panel

`toast.css` currently uses `--tile-shell-r` (16) / `--tile-core-r` (12). Tiles
are small inline stat boxes. This is a **482×150 floating window** and needs a
radius that scales with the surface — the main window uses 28/22 for the same
reason.

Change to `--panel-shell-r` (18) / `--panel-core-r` (14). Both come from
`dv.CARD_LAYERS`, and every row already satisfies `core == shell − padding`, so
the nesting rule stays intact. If 18/14 still reads tight against frame 2i, use
`--hero-shell-r` (22) / `--hero-core-r` (17) — but pick one and say which.

## 3. Make the two layers readable

It currently reads as one flat dark panel. The outer shell needs its neutral
wash — `rgb(var(--hairline-rgb) / var(--shell-fill-a))` with a
`var(--shell-border-a)` hairline border — so the darker core sits visibly
inside it, exactly as the Clips cards do.

## Do not change

- The replace-in-place behaviour, the single tick chain, or the 4s drain.
- `tests/test_v4_windows.py` must pass unchanged.
- The ember ring icon and the type hierarchy — both are already right.

## Rules

- Tokens only. No hand-typed hex, radii, durations or easings. A missing value
  goes into `obsauto/design_v3.py` followed by `python spike/gen_tokens.py`.
  Never edit `tokens.css`.
- `transform` and `opacity` only.
- **You may edit only** `spike/web/toast.css` and `spike/web/toast.html`.

## Definition of done

The standard gate, plus a screenshot of the toast that you **open and
describe** — say specifically whether the drain bar ends now fade and whether
the two layers are distinguishable.
