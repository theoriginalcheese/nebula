# t013 — Customise mode is finicky and removed modules can't come back

**Symptom (user):** "the customise tab looks very finicky and it controls very
clunky and i cant add any tabs once they are removed."

This is the dashboard's edit mode (`setDashEditing`, frame 6h), not a pane.

## 1. Removed modules are unreachable — the important one

The mechanism exists and is wired: `paintAddModuleRow()` renders a chip per
missing module into `#dash-add-row`, and the delegated handler at `app.js:417`
calls `addDashBlock(add.dataset.add)`. So it is not missing — it is
**unreachable**.

In the user's screenshot the "ADD MODULE / + Activity" row sits at the very
bottom of the pane, overlapping the activity list and colliding with the
storage block in the rail. Once a module is removed the row is the only way
back, and it is the least reachable thing on screen.

Work out why it lands there (`.dash-add-row` at `app.css:536`, and where
`#dash-add-row` sits in `index.html:182` relative to `#dash-grid`) and give it a
position that is obviously part of edit mode. Options worth weighing — pick one
and say why:

- pinned directly under the grid, always in view while editing
- in the pane header next to **Done**, where the other edit affordances already are

Requirements either way:

- Visible **without scrolling** the moment a module is removed.
- Never overlaps the grid, the activity list, or the rail.
- Reads as part of edit mode, and disappears with it.

## 2. The controls feel clunky

Each block carries a handle strip with `½ / ⅔ / Full` span buttons and an `×`.
Concrete things to improve — do not redesign the grid:

- **Hit targets.** `dv.MIN_HIT_TARGET` is 30px and the strip controls are
  smaller. Bring them up to it without changing `--handle-strip-h`.
- **Removal is a cliff.** `×` deletes with no undo and no confirm, and the only
  recovery is the row from part 1. At minimum make the chip that comes back
  obviously connected to what was just removed.
- **Drag feedback.** `--drag-rotate` and the grid overlay already exist; make it
  clear what will happen where the block lands, rather than only what is being
  dragged.
- **The active span should read as selected**, matching how
  `.rail-item.is-active` and `.palette-row.is-active` mark state. Do not invent
  a third idiom.

## Rules

- **No hard-coded colours, timings or easings.** Everything is already a custom
  property; `python tools/lint_tokens.py` enforces it and runs as a hook.
- **Only `transform` and `opacity` may be animated.** The grid uses
  `grid-template-columns`; do not animate it.
- Layout persists as `dashboard_layout` through `set_dashboard_layout` /
  `normalise_dashboard_layout`. **Do not change the persistence format** — a
  hand-edited config must still never lose a panel.
- ⛔ Do not touch `obsauto/design_v3.py`, `spike/gen_tokens.py`,
  `spike/web/tokens.css`, `spike/app.py`, `spike/host.py`, `spike/windows.py`.
- ⛔ **Do not touch the Macropad pane, the toast, or the mini overlay.**
- ⛔ Do not touch `renderForecast` or `.meter` — being fixed separately, same files.

## Definition of done

1. `python tools/lint_tokens.py` → clean
2. `python -m ruff check .` → clean
3. `python tests/test_design_v3.py` → passes
4. Screenshot edit mode **with a module removed**, and look at it:
   ```
   python spike/app.py --show --url=customise=1
   python tools/shoot.py --out shots/t013-customise.png
   ```
   The add-module affordance must be plainly visible and not overlapping
   anything. Confirm you actually removed a module and added it back.
5. Say which placement you chose and why.

⚠️ A Nebula instance may already be running — use `--dev` to run alongside it,
and **kill your instances when you finish**. Leaving them alive starts real OBS
recordings of the user's game.

## ⚠️ Instance hygiene — the user is watching for this

A Nebula instance is already running and **the user can see it**. They have
already complained about two copies being open at once.

- Use `--dev` so you do not fight the single-instance mutex.
- Take your screenshot, then **kill every process you started**, immediately.
- Do not leave an instance alive between steps. Each one starts a real OBS
  recording of their game and shows up as a second window on their desktop.
