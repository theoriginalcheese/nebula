# Code audit pass — customise mode (`Nebula Code Audit.dc.html`)

The Claude Design document audited `spike/web` at **863efe18** and listed fifteen
fixes in four groups. All fifteen are done. This file is the record: what was
built, what the audit got wrong, and what was deliberately not built.

Run order was the audit's own, because steps 1–3 are what make the mode *feel*
different and everything else is cheap once they land.

## The acceptance test

> Enter customise mode, drag Session stats between two half-width modules, and
> watch the placeholder. If it tracks the cursor monotonically, nothing twitches
> behind it, and the drop lands where the dashed box was — F1, F2 and F3 are all
> closed at once.

That gesture is now `tests/test_v4_drag.js`, which runs `app.js` in a `vm`
context against a stub `getComputedStyle` and a map of block heights. The
geometry is pure arithmetic after the fix, so it is testable without a window —
which is the whole reason the fix is shaped the way it is.

```bash
node tests/test_v4_drag.js
```

## What changed

| # | Fix | Where |
|---|-----|-------|
| F1 | `measureBlockRect()` deleted. `dashGridMetrics()` measures once at grab; `dashRowBoxes()` turns a layout into boxes with no DOM reads at all. | `app.js` |
| F2 | `dropIndexFor()` finds the row band, then counts columns within it. | `app.js` |
| F3 | The dragged block stays in the grid at `opacity: 0` and *is* the placeholder. `#dash-drop-marker` deleted. | `app.js`, `app.css`, `index.html` |
| F4 | The strip's grip is a real `<button>`; Space/arrows/Shift-arrows/Delete all work; one `div[aria-live=polite]` announces whole sentences. | all three |
| F5 | `.dash-scrim` deleted. One dimming mechanism, and edit mode is at the `--edit-content-a` the token actually declares. | `app.css`, `index.html` |
| F6 | Guides are `border-left` only, `:first-child` none, `z-index: 0`. | `app.css` |
| F7 | Add module is a dashed half-width tile in the last grid slot. The pane header no longer reflows. | all three |
| F8 | Reset layout beside Done, and a 6s "Layout saved · Undo" toast. | all three |
| F9 | The hero's segment renders `disabled` with a title instead of vanishing. | `app.js`, `app.css`, `index.html` |
| F10 | `showPane()` leaves customise mode and commits when you leave the dashboard. | `app.js` |
| F11 | Four appearance keys over tokens that already existed. | `design_v3.py`, `gen_tokens.py`, `config.py`, `settings_spec.py`, `app.py`, `app.js`, `app.css` |
| F12 | `packGridRows` and `moveKbdHeld` wired up; `dashKbdFocus`, `@keyframes rise`, `.blob`, `.wisp` and the dead `.row` grid deleted. | `app.js`, `app.css` |
| F13 | `.tiles` is `repeat(auto-fit, minmax(112px, 1fr))`. | `app.css` |
| F14 | The ghost is a stand-in — one label node, not a clone of the module's subtree. | `app.js`, `app.css` |
| F15 | Nothing assigns a layout property per index change any more, and `lint_tokens.py` now checks JavaScript for it. | `app.js`, `lint_tokens.py` |

## Three places the audit was wrong

Worth writing down, because each one would have been accepted on the document's
authority alone.

**F2 — the old hit test was not non-monotonic.** The audit said "the index is
not monotonic in cursor position". Brute-forced over every ordering of four
blocks and every choice of dragged block (96 combinations, sampled at 5px in
both axes), the old formula never goes backwards in x or in y. What it does is
**disagree with where the cursor visibly is at ~19% of positions**, because
`cy > this block's own midpoint` fires at a different height for every block in
a row and blocks in a row have different heights. That is the real defect and
it is the same fix, but the mechanism in the document is not what was happening.
`tests/test_v4_drag.js` asserts the property that actually has teeth — a cursor
over the first block's left half inserts *before* it — alongside monotonicity,
which the old code also satisfied.

The audit also said the guard `Math.abs(cy - mid) < r.height / 2` "does
nothing". It does: it restricts the horizontal clause to cursors inside that
block's vertical extent. What it does not do is make the test two-dimensional.

**F4 — keyboard reordering was not unreachable.** "`dashKbdHeld` is only ever
assigned `null`, and no keydown handler picks a module up" was not true at
863efe18: `app.js:2094` had a Space handler that set `dashKbdHeld`, collapsed
the block and showed the marker, and ↑/↓ called `moveKbdHeld`. What was actually
missing — and is now built — is the `aria-live` region, Shift-arrow span
stepping, Delete, ←/→, and an accessible name: the strip was a `div[tabindex]`
with no role. `dashKbdFocus` was genuinely written-and-never-read.

**F14 — the ghost does not disappear.** "If F3 is fixed the ghost disappears
entirely" leaves nothing under the cursor. The audit's own alternative is taken
instead: a cheap stand-in with the module's name, one node instead of a deep
clone of thumbnails and log rows.

## Deliberately not built

- **Motion does not auto-switch to Off while recording.** F11's prose argues for
  it ("an automatic one while recording is the same argument"), but the
  deliverable was four settings keys and this is a fifth behaviour the user
  never chose. A preference that changes itself is a support question. The
  switch is there to be thrown; wiring it to `hero_state == "recording"` is one
  `classList.toggle` away if that turns out to be wanted.
- **No hex field, and no themable ground.** `--ground`, `--panel` and
  `--card-core` are not in the appearance layer, and `--ember` is untouched, so
  a real disconnection still reads as one at every accent.

## Two deviations worth knowing

- **Key names are flat.** The audit writes `appearance.accent`; the keys are
  `appearance_accent`, `appearance_density`, `appearance_radius`,
  `appearance_motion` — `config.DEFAULTS` is a flat snake_case dict and
  `settings_spec` walks it, so a dotted key would have been the only one of its
  kind for no gain.
- **`.rows` and `.empty` were not dead.** The stylesheet's
  `/* legacy clip rows (unused) */` header covered three live rules as well as
  the dead ones. Only the `.row` grid and its children went; the header was
  itself the stale thing and now says what the block is for.

## What the gate learned

Three of the fifteen were invisible to every check the project had. Two new ones
close that:

- **`lint_tokens.py` now reads the JavaScript.** Rule 2 ("only transform and
  opacity") was only ever enforced against stylesheets, and F15 was an
  *assignment* to `style.width`, not a transition on it. A run of writes can
  share one `// lint-allow:` reason.
- **`lint_tokens.py` checks that `display` has not defeated `hidden`.** Found
  during this pass, in code written during this pass: `.dash-drag-ghost` was
  given `display: flex`, which outranks the UA stylesheet's
  `[hidden] { display: none }`, and left a panel-coloured rectangle parked over
  the hero at the last drag's size. It looks exactly like a layout mistake.

## Second pass — what using it actually found

The audit found fifteen things by reading. Ten minutes of using the result
found four more, three of which were older than the audit.

**The drag ghost was never under the cursor.** `.dash-drag-ghost` is
`position: fixed` and set neither `left` nor `top`, so it was laid out at its
**static position** - where it would have sat in normal flow, inside
`#pane-dashboard` - and `translate3d(clientX, clientY, 0)` ran from there. The
thing in your hand sat a pane origin away from your hand, about 264px right and
113px down, for the whole drag. This predates the audit and is probably the
single largest reason customise mode "felt wrong": no amount of correct index
maths reads as correct when the object is not where the pointer is. Two lines
of CSS.

**The 5s poll rewrote the dashboard mid-edit.** `renderTiles` and
`renderActivity` replace the innerHTML of `#tiles` and `#activity` on every
poll. In customise mode that re-packs the grid while you are aiming at it, and
invalidates the block heights the drag measured at grab time - so the
placeholder answers against a layout that no longer exists. This is what "it
randomly updates" was. The dashboard now freezes while you are arranging it and
catches up on exit (`dashContentFrozen()`).

**`.switching` was never removed.** `showPane` adds the entrance-animation
class and only removes it at the *start* of the next switch, so the active pane
permanently carries an animation that applies a transform. Harmless today, but
an element with a transform is a containing block for `position: fixed`
descendants, so it is a trap sitting under every fixed child of a pane. It now
comes off on `animationend`, with a timeout fallback because
`prefers-reduced-motion` cancels the animation and no event ever fires.

**A forced layout per pointermove.** `dropIndexFor` called
`pane.getBoundingClientRect()` on every move, right after a DOM reorder had
dirtied layout. The pane origin is cached in the drag metrics now.

### And the thing the audit asked for without asking

Restoring a removed module appended it to the end, which is not "put it back".
Customise mode now behaves like a home screen in jiggle mode:

- **the whole module is the handle**, not a 26px strip you have to find first;
- **Add module chips are draggable** - drag one into the grid and it lands
  where you drop it, with the dashed slot showing its real footprint while a
  chip-sized stand-in rides the cursor;
- **a tap still just adds it**, so the quick path survives. A 4px slop
  threshold is what separates the two gestures.

## Third pass — the Games pane, the ribbon, and a form

Four things from using the built result.

**Icons in the Games pane** (`obsauto/app_icons.py`). The obstacle was that the
classifier keys everything by exe **basename** and an icon needs a **path** -
and a path cannot go in `games.json`, because that file syncs to GitHub and
merges across machines. So paths live in a local `app_paths.json` sidecar the
Monitor writes as it sees processes, and there are three layers: the cached
PNG, the executable's own icon, and a monogram tile derived from the name. The
tile draws its colour from `design_v3.ACCENTS`, so the pane cannot introduce a
hue the design system does not already own, and the colour is hashed from the
name so adding a game never re-colours the others.

Two things worth knowing. `backfill_from_running()` resolves paths for anything
already running at launch - 21 of 33 rows on this machine, immediately - so the
pane is useful before you relaunch anything. And a monogram is **not** cached to
disk: it is arithmetic on the name, so a cache entry would only be a file to
invalidate on the day the executable turns up.

The extraction had a bug worth recording: `GetSystemMetrics` is `win32api`'s,
not `win32gui`'s, and the `except Exception` around the GDI work swallowed the
resulting `AttributeError`. Every extraction quietly produced a monogram and
the feature looked like it had simply decided there were no icons anywhere. A
broad `except` around a block that does five different things will hide a typo
in any one of them.

**The session ribbon** was one flat bar with the game, the duration and the
clock time all inside a native `title`. It now has three-hourly gridlines, a
"now" marker so the empty right-hand half reads as "not yet" rather than
"nothing recorded", in-span labels where there is room, and a legend of what
was recorded and for how long. Hovering writes the detail into the header in
one fixed place instead of a tooltip. No second hue was needed for any of it.

**Form fields.** `.field-input` had no horizontal padding while
`.listbox-trigger` beside it had `0 12px`, so a row like Resolution / Frame
rate read as two different controls and the left edge of the form zig-zagged.
The padding belongs on the input only - the listbox is a wrapper whose trigger
already carries it.

## A false green in the gate itself

`tools/smoke.py` reported `customise ok` under a screenshot of the **Settings**
pane. Its palette and customise shots need their own boot (they are entered by
a URL switch), and `launch()` polled for *a window titled Nebula* without
checking whether the process it had just started was still alive. With another
instance running, the second one exits on the single-instance mutex inside a
second and the poll finds the **first** instance's window - so the tool
photographs whatever pane that happens to be on and calls it the surface you
asked for.

This is the precise failure the file's own docstring says it exists to prevent
("eight delegated jobs in a row passed the gate with a visible defect"). It now
checks `p.poll()` before looking for a window and fails with the reason.

## Looking at it without launching Nebula

Launching the app drives live OBS, so this pass was checked against a harness:
`Api().config()` and `Api().snapshot()` dumped to JSON, stubbed in as
`window.pywebview.api`, and the real `app.js`/`app.css` loaded over the top.
Every fix above was verified in a browser that way — drag, drop, undo, reset,
pane-leave, and all four appearance keys — before anything was called done.
