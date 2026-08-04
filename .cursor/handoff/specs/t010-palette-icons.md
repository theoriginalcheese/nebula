# t010 — Command palette row icons (frame 7e)

## The gap

Frame `design/ui-v3/frames/7e.png` gives **every palette row a leading glyph** —
a record ring on "Start recording", a rewind on "Save the last 30s", a folder on
"Open recordings folder", a thumbnail on a clip row, a sliders glyph on a setting.

Our rows render label + hint only. `spike/web/app.js`, in `paintPalette()`:

```js
html += `<div class="palette-row ${active ? "is-active" : ""}" data-palette-idx="${pos}">
  <span class="palette-label">${boldLabel(row.label, row.spans)}</span>
  ${row.hint ? `<span class="palette-hint">${esc(row.hint)}</span>` : ""}
```

Add the icon. That is the whole task.

## How to pick the glyph — from the action, never from the label

Each row carries `row.action` = `[kind, arg]`. `kind` is one of exactly these,
and they are produced by `obsauto/palette.py` — read it, do not guess:

| kind | meaning | suggested Segoe Fluent glyph |
|---|---|---|
| `goto` | jump to a pane | per-pane, or one generic navigation glyph |
| `transport` | record / pause | record ring |
| `replay` | save the last 30s / arm the buffer | rewind |
| `open` | reveal a folder | folder |
| `game` | per-game encoder profile | game controller |

**Do not parse `row.label` to choose an icon.** The label is display text; the
action is the contract. A label-sniffing branch breaks the moment a label is
reworded, and it will be.

If a kind arrives that you have no glyph for, render **no icon** and let the row
fall back to label-only. Do not invent a placeholder glyph — a wrong icon is
worse than none, and this repo's standing rule is to omit rather than fabricate.

## The icon set

**Segoe Fluent Icons**, not Phosphor. `design_v3.py`'s `ICONS` table names
Phosphor roles, but Phosphor is not installed on this machine — the roles are
translated to Fluent codepoints. The existing search glyph in the palette proves
Fluent renders here:

```html
<span class="palette-glyph" aria-hidden="true">&#xE721;</span>
```

⚠️ **Verify every codepoint by actually rendering it.** This repo has been bitten
by glyphs that resolve to a blank box or the wrong pictogram. A codepoint that
looks right in a table is not evidence. Screenshot the palette and *look* at each
row before you claim it works.

## Styling

Match `.palette-glyph`'s treatment (colour, size, optical alignment) so the row
icon and the search glyph read as one family. Rows must stay vertically aligned
with each other whether or not they have an icon — an icon-less row must not
shift its label. Keep `aria-hidden="true"` on decorative glyphs.

Icon column sits left of `.palette-label`. Do not change row height
(`PALETTE_ROW_H = 38` in `design_v3.py`) or the 560px palette width.

## Rules that apply here

- **No hard-coded colours in the stylesheet.** Use the existing custom
  properties. `python tools/lint_tokens.py` enforces this and runs as a hook.
- **Only `transform` and `opacity` may be animated.** If you add a hover or
  active treatment on the icon, it animates one of those two or neither.
- Do not touch `spike/app.py`, `spike/gen_tokens.py`, `obsauto/design_v3.py`,
  or `obsauto/palette.py`. ⛔ The matcher and the token source are out of scope;
  this is a rendering change in `app.js` + `app.css` only.

## Definition of done

1. `python tools/lint_tokens.py` → clean
2. `python -m ruff check .` → clean
3. `python tests/test_palette.py` → passes (matching logic must be untouched)
4. Palette open, screenshotted, and **every row's icon visually confirmed** —
   no blank boxes, no wrong pictograms:
   ```
   python spike/app.py --show --url=palette=1
   python tools/shoot.py --out shots/t010-palette.png
   ```
   Compare against `design/ui-v3/frames/7e.png`.
5. Say plainly which kinds got an icon and which deliberately did not.
