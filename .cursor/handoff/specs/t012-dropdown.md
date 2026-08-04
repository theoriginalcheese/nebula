# t012 — Replace the native `<select>` dropdowns

**Symptom (user):** "the drop down looks weird and blocky and doesnt fit the
style (out of place)."

They mean the Clips sort control. Screenshot: the closed control is styled and
fits, but the open list is a grey OS menu with square corners, a system
highlight bar and system fonts — sitting on top of the Nebula chrome.

## Why CSS alone cannot fix it

A native `<select>`'s popup is rendered by the OS, not the page. `option`
styling is almost entirely ignored, and the popup takes no border-radius, no
background, no font. There is no CSS route to a fitting dropdown. It has to be
replaced with a real listbox built from divs.

## Where they are

```js
// app.js:721 — the one the user is complaining about
<select class="clip-sort no-drag" id="clip-sort" aria-label="Sort clips">
  <option>Newest</option><option>Oldest</option><option>Largest</option>
</select>

// app.js:1047 and 1060 — per-game encoder profile fields
<select class="field-select no-drag" data-profile="...">

// fieldHtml()'s `choice` branch — Settings dropdowns
```

Convert **all** of them. They share `.field-select` styling and a user who
dislikes one will dislike the rest; leaving three of four is worse than leaving
all four.

## What to build

A small reusable listbox, used by every call site — not four copies:

- **Closed state**: keep exactly the look the styled `<select>` has now, so the
  resting appearance does not change. Include the chevron.
- **Open state**: a panel that belongs to the app. Use the card language —
  `--tile-core-r` or `--panel-core-r` for the corner, `--card-core-rgb` at the
  core alpha for the surface, a hairline border, and the same
  `--pane-change-ms` / `--ease` timing everything else uses.
- **Selected row**: mark it with the accent, the way `.palette-row.is-active`
  does. Do not invent a new highlight treatment — match the palette, which is
  the app's existing list idiom.
- **Hover**: as `.palette-row:hover`.

## Behaviour it must keep

The native control gives you these for free and they are easy to lose:

- Click opens; click a row selects and closes; click outside closes; **Esc**
  closes without changing the value.
- Keyboard: focusable, ↑/↓ move, Enter selects, Esc closes. The palette already
  implements this pattern — follow it rather than inventing one.
- `aria-label` preserved; use `role="listbox"` / `role="option"` and
  `aria-selected`. The control it replaces was accessible; the replacement must
  be too.
- The change event must still drive the existing handlers. `clipState.sort` and
  the profile/settings save paths must keep working unchanged — **do not touch
  the sorting logic** (`app.js:855-860`) or the profile save path.
- The panel must not be clipped by an ancestor's `overflow: hidden`, and must
  sit above the pane content.

## Rules

- **No hard-coded colours or timings in CSS.** Use the existing custom
  properties; `python tools/lint_tokens.py` enforces it and runs as a hook.
- **Only `transform` and `opacity` may be animated.** An open/close transition
  animates those two or neither — no height animation.
- ⛔ Do not touch `obsauto/design_v3.py`, `spike/gen_tokens.py`,
  `spike/web/tokens.css`, `spike/app.py`, `spike/host.py`, `spike/windows.py`,
  or `obsauto/settings_spec.py`.
- ⛔ **Do not touch the Macropad pane.** The user explicitly said it is right.
- t011 is editing `app.css` and `app.js` at the same time. Keep your changes to
  the dropdown; do not reformat or "tidy" anything around them.

## Definition of done

1. `python tools/lint_tokens.py` → clean
2. `python -m ruff check .` → clean
3. `python tests/test_palette.py` and `python tests/test_design_v3.py` → pass
4. Screenshot the Clips pane **with the dropdown open** and look at it:
   ```
   python spike/app.py --show
   python tools/shoot.py --out shots/t012-dropdown.png
   ```
   No grey OS menu, no square corners, no system font. It should read as part
   of the same app as the command palette.
5. Say which call sites you converted and whether keyboard control works.
