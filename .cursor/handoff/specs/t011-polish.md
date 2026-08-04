# t011 — Three visual defects the user called out

All three are diagnosed. Do not go hunting; make these changes.

---

## 1. Settings toggles stack below their label instead of sitting beside it

**Symptom (user):** "on the settings page i dont like how the switch toggle is
below and not to the side, it disturbs the flow of the page."

**Cause.** `fieldHtml()` renders a boolean as `<div class="field toggle">`.
Both classes set layout, and they fight:

```css
.field  { display: flex; flex-direction: column; gap: 4px; }   /* app.css:1407 */
.toggle { display: flex; align-items: center; justify-content: space-between;
          gap: 16px; padding: 4px 0; }                          /* app.css:1440 */
```

`.toggle` never resets `flex-direction`, so `column` from `.field` survives and
the switch drops onto its own line, centred by `align-items: center`.

**Fix.** Have `.toggle` state the direction it needs. One declaration. Do not
restructure the markup and do not touch `.field` — every non-boolean field
depends on the column layout.

Check a boolean *and* a text field afterwards: label and key on the left, hint
under them, switch right-aligned on the same row; text fields unchanged.

---

## 2. The "Record anyway" pill looks cut off

**Symptom (user):** "the 'record anyway' gets cut off short and looks wrong."

**Cause.** `.pill` reserves room on the right for a trailing icon circle:

```css
.pill { padding: 0 6px 0 16px; }        /* app.css:341 */
.pill .trail { width: 27px; height: 27px; ... }
```

Only `btn-refresh` ever gets a `.trail` (`app.js:741`). Every other primary
pill — "Record anyway", "Stop recording", "Retry now" — has 16px of left
padding and 6px of right, so the label sits almost against the edge and reads
as clipped. `.pill.ghost` already overrides to `0 16px`, which is why the ghost
buttons next to it look fine.

**Fix.** Make the symmetric padding the default and let the reduced right
padding apply only when a trail is actually present. `:has()` is available in
this WebView2. Do not change `--pill-h`, the radius, or `.trail` itself.

Verify "Record anyway" and "Stop recording" both have even padding, and that
the Refresh pill's trailing circle still sits correctly.

---

## 3. The toast is too square

**Symptom (user):** "i dont like the way the toast is square."

**Cause.** `toast.css` uses the **panel** card layer:

```css
.toast-shell { border-radius: var(--panel-shell-r); }   /* 18 */
.toast-core  { border-radius: var(--panel-core-r);  }   /* 14 */
```

The panel radii are specified for a card nested *inside* the window. The toast
is a standalone always-on-top window, and the thing it should match is the
window's own corner: `dv.CARD_LAYERS["tray"]` = **28 / 6 / 22**, already emitted
as `--tray-shell-r`, `--tray-pad`, `--tray-core-r`.

**Fix.** Move the toast onto the tray layer. Keep the shell/padding/core
*nesting* intact — `28 - 6 = 22` is the contract, so if you change the padding
you must change the core radius to match. The mini overlay is **not** in scope;
the user did not complain about it.

---

## Rules

- **No hard-coded values in the stylesheets.** Every number above already
  exists as a custom property. `python tools/lint_tokens.py` enforces this and
  runs as a hook.
- **Only `transform` and `opacity` may be animated.**
- ⛔ Do not touch `obsauto/design_v3.py`, `spike/gen_tokens.py`,
  `spike/web/tokens.css`, `spike/app.py`, `spike/host.py` or `spike/windows.py`.
  This is `app.css` / `toast.css` / `app.js` only.
- ⛔ **Do not touch the Macropad pane.** The user explicitly said it is right.

## Definition of done

1. `python tools/lint_tokens.py` → clean
2. `python -m ruff check .` → clean
3. `python tests/test_design_v3.py` → passes
4. Screenshots, and **look at them**:
   ```
   python tools/smoke.py --only settings
   python tools/smoke.py --only dashboard
   ```
   Settings: switch beside its label. Dashboard: pill padding even.
   The toast needs a live event, so state plainly that you changed its radius
   and could not photograph it rather than implying you saw it.
