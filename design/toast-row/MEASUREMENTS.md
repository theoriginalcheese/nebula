# Nebula Toast Row — measurements

Source: `Nebula Toast Row.dc.html` (project "Nebula UI mockups", file etag `1790844233099758`).
All numbers below are quoted straight from that file's inline styles and `data-dc-script` logic.

## Shared geometry (every toast)

- **Base capsule box:** `width: {{ t.w }}px; height: 60px`, drawn inside a scaled wrapper
  `transform:scale({{ scale }}); transform-origin:0 0`. The component prop `scale` is an enum
  `[1, 1.5, 2]`, **default 1.5**. Label text: `scale === 1 ? 'real size' : scale + '×'`.
- **Outer glass layer:** `inset:0; border-radius:30px; background:rgb(245 243 255 / .07);
  box-shadow:inset 0 0 0 1px rgb(245 243 255 / .10), 0 12px 32px rgb(0 0 0 / .35);
  backdrop-filter:blur(18px)`.
- **Inner fill layer:** `inset:3px; border-radius:27px; background:
  radial-gradient(90% 180% at 0% 0%, {{ t.wash }}, transparent 60%),
  radial-gradient(60% 160% at 100% 100%, rgb(64 48 150 / .22), transparent 70%),
  rgb(16 13 28 / .88); box-shadow:inset 0 0 0 1px rgb(245 243 255 / .075),
  inset 0 1px 0 rgb(245 243 255 / .06)`.
- **Page/backdrop base:** `#0A0812`, with three radial glows layered over it
  (`rgb(139 124 246 / .16)` at 78% 30%, `rgb(64 48 150 / .28)` at 92% 85%,
  `rgb(255 92 122 / .05)` at 60% 70%).
- **Row list layout:** outer column `display:flex; flex-direction:column; gap:20px`
  (vertical gap between toast rows). Each row: `display:flex; align-items:center; gap:14px`
  between the index label and the capsule.
- **Index label** (left of each capsule): `font-family:'Cascadia Mono',ui-monospace,monospace;
  font-size:11px; color:#736BA4`, text = zero-padded index (`01`…`07`).
- **Copy above the row** — eyebrow: `"Nebula toasts · locked row format"`
  (`font-size:11px; letter-spacing:.14em; uppercase; color:#736BA4`). Subcopy:
  `"Every toast is one row: same 60px height, chip, type size and centre. Status toasts are
  384px wide and prompts are 456px. Drawn at {{ scaleLabel }}, bottom-right, 24px from the
  edge."` (`font-size:13px; color:#9A93C4`).

## Chip (icon badge) — identical geometry on every toast

- **Size/position:** `width:28px; height:28px; border-radius:50%; left:16px; top:16px`.
- **Styling:** `background:{{ t.chipBg }}; box-shadow:0 0 0 5px {{ t.halo }}, 0 0 16px {{ t.glow }},
  inset 0 0 0 1px {{ t.chipRing }}`.
- **Icon:** inline SVG, `width="14" height="14" viewBox="0 0 24 24"`, stroke `{{ t.ink }}`
  (`stroke-width:2`) plus a filled path in the same `{{ t.ink }}`.

## Text block

- **Position/box:** `left:56px; top:0; height:60px; width:{{ t.textW }}px`, row flex with
  `gap:7px`, `white-space:nowrap`.
- **Title:** `font-size:14px; font-weight:500; line-height:18px; color:#F5F3FF`.
- **Game separator "·":** `font-size:14px; line-height:18px; color:#736BA4`.
- **Game name:** `font-size:13px; line-height:18px; color:#9A93C4` (ellipsis-truncated).
- **Meta readout** (stop toast only): `"10:47 · 1.7 GB"` — `font-family:'Cascadia Mono',
  ui-monospace,monospace; font-size:11.5px; line-height:18px; color:#9A93C4;
  font-variant-numeric:tabular-nums`, pushed right with `margin-left:auto; padding-left:6px`.

## Prompt buttons (prompt toasts only)

- **"Record":** `left:286px; top:17px; width:72px; height:26px; border-radius:13px;
  background:rgb(139 124 246 / .32); box-shadow:inset 0 0 0 1px rgb(245 243 255 / .09),
  inset 0 1px 0 rgb(245 243 255 / .06); color:#F5F3FF; font-size:12px; font-weight:500`.
  Active-state: `transform:scale(.98)`, transition `120ms cubic-bezier(.32,.72,0,1)`.
- **"Not now":** `left:366px; top:17px; width:72px; height:26px; border-radius:13px;
  background:rgb(245 243 255 / .045); box-shadow:inset 0 0 0 1px rgb(245 243 255 / .09);
  color:#9A93C4; font-size:12px; font-weight:500`. Same active-state/transition as Record.

## The drain

Bottom progress/tint bar, present on every toast: `position:absolute; left:24px; right:24px;
bottom:5px; height:2px; border-radius:2px; background:{{ t.tint }}`, masked with
`linear-gradient(90deg, transparent 0, #000 40px, #000 calc(100% - 40px), transparent 100%)`
(same gradient on both `mask-image` and `-webkit-mask-image`) — so it fades out over the first
and last 40px rather than ending in a hard edge.

## Dust

`DUST` is 7 fixed specks, each `[dx, dy, r, a]`:
`[20,-10,2.2,.78] [30,-4,1.5,.48] [16,9,1.8,.58] [-10,-12,1.4,.42] [36,8,1.2,.36]
[6,-14,1.1,.32] [26,12,1.0,.28]`.

Per speck, computed in `dust(cx, mirror, style, k)`:
- `x = cx + dx * k * mirror`, `y = 30 + dy * .7`, `s = max(1.5, r * 1.6)` (circle diameter, px).
- `mirror` is always `-1`. `k` defaults to `.7` for plain status toasts.
- Opacity = `a` (the 4th tuple value, direct). Box-shadow glow: `0 0 4px {{ t.speckGlow }}`.
- Animation: `nr-${style} ${DUR[style]}s ${style==='orbit' ? 'linear' : 'cubic-bezier(.32,.72,0,1)'} ${-i*.23}s infinite`
  — each of the 7 specks staggered by `-0.23s × index`.
- Durations (`DUR`): `burst 2.4s, sink 2.8s, drift 3.6s, rise 2.6s, scatter 1.8s, orbit 4.2s`.
- `cx` / `k` by toast kind: plain status `cx:348, k:.7` · meta (stop) `cx:372, k:.3` ·
  prompt `cx:34, k:.5`.

## Colour sets

**V (violet)** — used by pause / resume / both prompts:
`tint:#8B7CF6` `ink:#B9AEF9` `chipBg:rgb(139 124 246 / .16)` `halo:rgb(139 124 246 / .07)`
`glow:rgb(139 124 246 / .34)` `chipRing:rgb(139 124 246 / .28)` `wash:rgb(139 124 246 / .09)`
`speck:#B9AEF9` `speckGlow:rgb(139 124 246 / .9)`

**E (ember)** — used by start / stop / error:
`tint:#FF5C7A` `ink:#FF5C7A` `chipBg:rgb(255 92 122 / .16)` `halo:rgb(255 92 122 / .07)`
`glow:rgb(255 92 122 / .38)` `chipRing:rgb(255 92 122 / .30)` `wash:rgb(255 92 122 / .07)`
`speck:#FF8FA5` `speckGlow:rgb(255 92 122 / .9)`

---

## Per-toast table

All widths/heights are the unscaled base values (`t.w` × `60`); at the default 1.5× scale,
status toasts render `576 × 90`px and prompts `684 × 135`px (unscaled `457.5` rounds from `456×1.5=684`).

| # | Copy (title · game) | Colour | Width | Height | Radius (outer / inner) | textW | Anim / duration | Dust cx, k | Extras |
|---|---|---|---|---|---|---|---|---|---|
| 01 | "Recording started" · "Helldivers 2" | E (ember) | 384px | 60px | 30px / 27px | 302px | `nr-burst`, 2.4s | 348, .7 | — |
| 02 | "Recording paused" · "Helldivers 2" | V (violet) | 384px | 60px | 30px / 27px | 302px | `nr-drift`, 3.6s | 348, .7 | — |
| 03 | "Recording resumed" · "Helldivers 2" | V (violet) | 384px | 60px | 30px / 27px | 302px | `nr-rise`, 2.6s | 348, .7 | — |
| 04 | "Recording stopped" · "Helldivers 2" | E (ember) | 384px | 60px | 30px / 27px | 280px | `nr-sink`, 2.8s | 372, .3 | meta readout `"10:47 · 1.7 GB"` |
| 05 | "Something went wrong" · (no game) | E (ember) | 384px | 60px | 30px / 27px | 302px | `nr-scatter`, 1.8s | 348, .7 | `hasGame:false` — no "·"/game shown |
| 06 | "Record again?" · "Helldivers 2" | V (violet) | 456px | 60px | 30px / 27px | 218px | `nr-orbit`, 4.2s, linear | 34, .5 | Record (286,17,72×26) / Not now (366,17,72×26) buttons |
| 07 | "New game detected" · "Clair Obscur" | V (violet) | 456px | 60px | 30px / 27px | 218px | `nr-orbit`, 4.2s, linear | 34, .5 | Record (286,17,72×26) / Not now (366,17,72×26) buttons |

Chip (all 7, identical): `28×28px` circle at `left:16px; top:16px`.
