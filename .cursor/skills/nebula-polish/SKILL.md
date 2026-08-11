---
name: nebula-polish
description: The aesthetic contract for Nebula - motion, easing, states, and the invariants that separate "the layout is right" from "it feels expensive". Use before calling any UI work finished, when a pane looks correct but feels cheap, and whenever adding a transition, hover, focus, disabled or empty state. These rules do not show up in a screenshot of the resting state, which is exactly why they get skipped.
---

# Nebula polish

Everything here is from `design/ui-v3/BUILD-SPEC.md` § Motion & states and
§ Living background, and every value has a token in `spike/web/tokens.css`
generated from `obsauto/design_v3.py`.

**This file exists because these were all written down and still got missed.**
The first cut of the v4 chassis passed a screenshot comparison and violated nine
of them, because a static capture cannot see an easing curve, a focus ring, a
press state or a paused animation. Layout is verified by the eye; polish has to
be verified by a checklist.

## The checklist

Run it before calling any pane done.

- [ ] **Easing is `var(--ease)`** — `cubic-bezier(.32,.72,0,1)`. Not `ease`,
      not `ease-in-out`, not a curve you invented.
- [ ] **Hover is `var(--hover-ms)` (500ms); press is `var(--press-ms)` (120ms)
      with `scale(var(--press-scale))`.** Press is a different, much faster beat
      than hover — not the same transition running backwards.
- [ ] **Pane change: opacity + `var(--pane-change-rise)` rise over
      `var(--pane-change-ms)`.** A pane that simply appears reads as a bug.
- [ ] **Live dot: `var(--live-dot-ms)` (1.9s), opacity .35 → .95.**
- [ ] **Focus ring: `var(--focus-ring-w)` solid accent, offset
      `var(--focus-ring-offset)`.** Use `:focus-visible`, and kill the
      webview's default ring on `:focus:not(:focus-visible)`.
- [ ] **Disabled: `opacity: var(--disabled-a)` and no hover** (`pointer-events:
      none`). A disabled control that still lights up on hover is a lie.
- [ ] **Never animate width / height / top / left.** Transform and opacity only.
- [ ] **The elapsed timer must not reflow its neighbours** —
      `font-variant-numeric: tabular-nums`, fixed width.

## Reduced motion — read this one twice

The spec does **not** want the usual "turn everything off":

> "Reduced motion keeps the colour. Under `prefers-reduced-motion` — or the
> Settings toggle — every layer stays exactly where it is via
> `animation-play-state: paused`. Nothing is removed, nothing goes flat."

`animation: none` is **wrong**: it resets every blob to its 0% keyframe, so the
aurora both stops *and* jumps to a different composition. Pause, do not stop.
`display: none` on a layer is wrong for the same reason, worse.

## Invariants — a violation is a bug, not a preference

- **No emoji. No gradient floods. No second accent hue.** Ember is
  live-and-errors only.
- **Every card is two layers**: tinted outer shell, darker inner core, with
  `inner radius = outer − padding`. Use the `--*-shell-r` / `--*-pad` /
  `--*-core-r` sets. A flat card is a bug.
- **Rules and dividers fade at both ends over 32–48px.** No hard-stopped 1px
  greys.
- **Trailing icons on primary pills get their own 26–28px circle**, flush to the
  right padding.
- **The background is randomised per launch.** Never hard-code a blob position
  or a star coordinate.
- **A fully opaque panel over the aurora is a bug.** In-window panels sit at
  0.72–0.92 alpha so the aurora reads through while text keeps contrast.
- **The pointer spotlight is cards only** — 300px, accent .22. Not the rail, not
  the titlebar. Implement it as one fixed-size element *inside* the card, moved
  by transform and clipped by the card's own `overflow: hidden`; a moving
  `background-position` or a per-event `radial-gradient` is a repaint on every
  mouse move and breaks the cost budget.

## Empty states are part of the design

"No fabricated numbers" is not only about accuracy — it is an aesthetic rule.
The mockup is full of filler: 418 clips, 1.9 TB, a connected macropad with an
HID id. Copying those produces a screen that looks finished and is a lie.

Build the source or render the honest empty state. Macropad stays empty because
there is no HID layer. `Settings` shows its config keys in mono under each
field — **that is design, not a debug aid**; do not remove them.

## Why this keeps happening

Aesthetic detail loses every prioritisation contest it enters. When a pane has
to render real data, handle an empty state, and not break the tray, the 500ms
hover curve reads as optional — and unlike a broken layout, nothing fails when
it is dropped. The screenshot loop will not catch it. The tests will not catch
it. Only this list will.

So run it explicitly, item by item, and say which ones you checked.
