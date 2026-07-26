# Nebula UI v3 — handoff to Cursor

**Written by Claude Code, 2026-07-26.** Everything Cursor needs to continue the v3 UI work
without re-reading the design project or re-deriving the constraints.

Open this repo in Cursor. `.cursor/rules/nebula-ui-v3.mdc` loads the essentials automatically;
this file is the long form.

---

## 1. What was imported, and from where

Source: Claude Design project `19d87879-67c8-4a4e-8eb1-d4fbd327a23a`,
file **`Nebula UI Mockups v3.dc.html`**. Pulled with the `DesignSync` MCP tool
(`https://api.anthropic.com/v1/design/mcp`, auth via `/design-login`).

Landed under `design/ui-v3/`:

| Path | What it is |
|---|---|
| `Nebula UI Mockups v3.dc.html` | the mockup, verbatim (151 KB) — open it in a browser |
| `support.js` | the design-canvas runtime the HTML loads (generated, don't edit) |
| `_ds/nocturne-…/styles.css` | Nocturne design-system tokens + component classes |
| `_ds/nocturne-…/readme.md` | Nocturne written guidance |
| `_ds/nocturne-…/_ds_bundle.js` | the DS component bundle — **empty**, zero components |
| **`BUILD-SPEC.md`** | § 05 "the contract" as markdown — **the authority** |
| **`FRAMES.md`** | frames 2a–2k, content and per-frame rules |

To view the mockup: open `design/ui-v3/Nebula UI Mockups v3.dc.html` in a browser. It fetches
Geist and Phosphor from CDNs, so it needs a network connection to look right.

Not imported (binary, pull on demand with `DesignSync` `get_file` if wanted):
`screenshots/*.png` — those are **v1/v2** frames (`1b`…`1k`, `states.png`), not v3.

### Which document wins

The mockup states it itself: **"If a frame and this table disagree, this table wins."**
So the precedence is:

```
design/ui-v3/BUILD-SPEC.md  >  the frames in FRAMES.md / the .dc.html  >  Nocturne readme.md
```

Nocturne is the *house* system (`#161826` ground, Inter, `--space-*` at 0.7× density).
**v3 does not use it.** The mockup overrides it wholesale with its own palette
("Nebula Deep", `#100D1C`), its own type (Geist / Geist Mono → ship as Segoe UI Variable /
Cascadia Mono) and its own spacing. Nocturne is imported for provenance and for the
*principles* that did carry over — fading rules, outlined not flooded accents, no pure
black/white, elevation as edge + ambient darkness. **Do not link `styles.css` into anything.**

---

## 2. Three places the spec collides with this repo — read before writing code

v3 was drawn in HTML/CSS. This app is **Python + CustomTkinter drawing on a `tk.Canvas`**.
Most of the spec ports fine. Three parts do not, and two of them are things the repo has
already been burned by. `CLAUDE.md` is the long version of all of it.

### 2.1 🔴 The "living background" cannot be animated. This is measured, not cautious.

The spec asks for aurora blobs on a 46–92s cycle plus two star-drift layers on 120–260s
cycles, **rendered inside the app window**, plus a 300px pointer-tracking spotlight on cards
and a pointer "lean".

In a browser those are GPU-composited `transform`/`opacity` layers — which is exactly why the
spec's cost budget says "transform + opacity only". **Tk has no compositor.** From
`CLAUDE.md`:

> On this window, **any** canvas change forces a full *window-level* composite costing ~100ms
> at 1770×1140. The cost is **flat** — it does not scale with how much changed. […] a ~12fps
> decorative animation timer wasn't "a bit expensive", it was fatal: **p50 110ms frames
> (~9fps), one core at 95%**. Removing all of it gives **p50 16ms at ~4%**.

It scales with **window size**, and v3 is *bigger* than the layout that first exposed this
(1280×808 vs 1180×760). `tests/test_frame_pacing.py` exists specifically to fail if a
per-frame timer comes back. Two earlier diagnoses of this were wrong and cost real time —
don't reopen it.

**Resolution taken (assumption — flag it if you disagree):** honour the *randomisation*
requirement, drop the *motion*.

- Seed the RNG at launch and render the aurora + both star layers **once**, into the static
  backdrop image (`obsauto/theme_art.py` already generates the nebula this way).
  This satisfies "randomised per launch, never hard-code blob positions or star coordinates"
  and "no two sessions look alike" — the spec's stated *intent* — without a repaint loop.
- Drop the pointer spotlight and pointer lean entirely. Both are per-pointer-event full-window
  repaints; there is no cheap version.
- The spec's reduced-motion clause ("keeps the colour… nothing goes flat") is then satisfied
  unconditionally, which is the outcome it was asking for anyway.
- Keep `rgba(16,13,28, 0.72–0.92)` panel translucency — that's composited **once** into the
  glass tiles at build time (`_regen_glass`, already cached), so it costs nothing per frame
  and "a fully opaque panel over the aurora is a bug" still holds.

The tray icon may keep animating — separate surface, never touches this window.

### 2.2 🔴 Most numbers in the frames have no data source. Don't invent them.

Standing rule, from `CLAUDE.md` and [[nebula-aurora-ui]] in the vault:

> ⚠️ Don't put fabricated numbers in the UI — the Games badge reads the classifier
> (`_game_count()`) and returns `None` (no badge) rather than inventing a count.

This is why v2 dropped "Mark clip", the search pill and the resolution/fps chips, and why
**Macropad is deliberately an empty page**. Audit against v3:

| Frame element | Backed by | Verdict |
|---|---|---|
| Clips count / total size, per-game counts, row length+size+recency | scan of `recording_root` | ✅ real |
| Storage bar, `1.42 TB free of 3.63 TB` | `shutil.disk_usage` | ✅ real |
| Elapsed, file size, state | OBS `GetRecordStatus` | ✅ real |
| Games / Not-games lists, AppIDs, unclassified queue | `Classifier`, `steam_scanner` | ✅ real |
| Activity log rows | `self.console` | ✅ real |
| `OBS 30.2`, handshake ms | OBS `GetVersion` — obtainable | ✅ real (needs wiring) |
| **Bitrate `14.2 Mb/s`** | nothing | ⚠️ derivable (Δbytes/Δt) — do it properly or omit |
| **`2560×1440 · 60 fps`** | OBS `GetVideoSettings` — obtainable | ⚠️ wire it or omit |
| **Scene preview thumbnail** | OBS `GetSourceScreenshot` — obtainable, but it's a repaint | ⚠️ see 2.1; a periodic screenshot is a per-frame composite |
| **Clip thumbnails** | would need ffmpeg | ⚠️ new dependency — decide before building 2b |
| **`Auto-culled 3`, `Idle pauses 12`** | nothing counts these | ⚠️ add counters in `Monitor` or omit the tiles |
| **Macropad: `3×3 pad · connected`, `HID 0x1209:0xA1B2`, key map, last key press** | **nothing** | 🚩 see 2.3 |

Where the source doesn't exist yet: **build the source, or omit the element.** An honest
empty state beats a plausible placeholder. Do not ship a tile showing `0` that means
"not implemented".

### 2.3 🚩 Macropad is a whole new subsystem, not a screen

Frame 2e draws a connected HID device, a live 3×3 key map, drag-and-drop action binding, and
a last-keypress readout. **None of that layer exists.** There is no HID code in `obsauto/`.
The build order in the spec puts Macropad in step 7 for this reason.

Also relevant: `toggle_hotkey_scancode` exists because **bindings must be by scan code** on
this hardware — see the vault note `asus-m4-fan-key`. Any new binding UI inherits that.

Treat it as: *(a)* an HID input layer, *(b)* a persisted binding map in `config.json`,
*(c)* the pane. Until *(a)* and *(b)* exist, the pane stays honest about having no device.

### 2.4 🟡 The window is now resizable — that's an architecture change

Spec: **1280×808 with a 1080×700 minimum**. Today `AppWindow` is a **fixed-pixel canvas
design** — everything drawn at absolute coordinates, with one uniform `self.scale` derived
from monitor DPI multiplying every coordinate and font (`ScaledCanvas`; see `CLAUDE.md` and
the vault's `nebula-dpi-scaling`). A minimum size only makes sense if the layout reflows,
which this architecture does not do.

Pick one, deliberately:
- **(a)** Keep fixed-pixel, ship at 1280×808 × `self.scale`, drop the resize. Cheapest, keeps
  the DPI work intact, loses nothing the frames actually show.
- **(b)** Make the content pane reflow (rail + titlebar stay fixed, pane stretches). Real work:
  every `_build_*` becomes width-aware, and every resize is a full re-render — which under
  2.1 must be **debounced**, never live-dragged.

Recommendation: **(a)** now, **(b)** only if you actually want to drag the window.

If you touch scaling at all, keep these two traps in mind (both cost time before):
`ctk.set_widget_scaling()` **must** be called *after* the real `geometry()` — CTk pins
minsize *and* maxsize to the current size. And `tk.call("tk","scaling",96/72)` must stay, or
point-sized fonts get DPI-scaled **on top of** `self.scale`.

### 2.5 CSS idioms with no Tk equivalent — how to land them

| Spec asks for | In Tk |
|---|---|
| `blur 54–110px` on blobs | pre-blur in PIL at generation time (`theme_art.py` already does `_blur_downscaled`) |
| radial-gradient glow, vignette | bake into the backdrop image |
| Fading rules ("fade at both ends over 32–48px") | a 1px-tall PIL strip with an alpha ramp, not a `create_line` |
| Two-layer cards ("a flat card is a bug") | outer tinted rounded rect + inner darker rounded rect — `_regen_glass` output, **keep it cached** |
| `cubic-bezier(.32,.72,0,1)`, hover 500ms | there is no cheap tween here; use instant state swaps. See 2.1 |
| `:focus-visible` 2px accent ring | explicit `highlightthickness` / drawn ring on focus |
| Phosphor Light icon font | not installed. Either bundle the TTF as a resource, or draw the ~24 glyphs in `icon_art.py`. **Pick one and be consistent** — the spec is strict that only `ph-circle` and `ph-square` are Fill weight |
| Geist / Geist Mono | the spec already says ship **Segoe UI Variable** / **Cascadia Mono** |

---

## 3. State of play

**Done (this session):** design files imported to `design/ui-v3/`; the § 05 contract
transcribed to `BUILD-SPEC.md`; frames 2a–2k transcribed to `FRAMES.md`; the conflicts above
identified against `CLAUDE.md` and the Obsidian vault; `obsauto/design_v3.py` written — the
tokens, geometry, type scale, icon legend and config map from § 05 as one machine-checkable
module, with `tests/test_design_v3.py` asserting it matches the spec.

**Not started:** every `_build_*` in `obsauto/gui.py` still renders the v2 "Aurora" layout.
No pane has been rewritten. Toast, tray menu rework and mini overlay do not exist.

**Follow the spec's own build order** (§ *Build order & don't-forget*, restated in
`BUILD-SPEC.md`) — steps 1→7. It is a good order; step 1 explicitly says nothing else until
the chassis matches 2a.

Two decisions to make before step 1, both in section 2 above: **the background** (2.1) and
**resize vs fixed-pixel** (2.4).

---

## 4. Repo rules that outrank the mockup

Do not weaken these to make a frame match. All of them are in `CLAUDE.md`; the vault notes
`nebula-aurora-ui`, `nebula-dpi-scaling`, `obs-footage-sacred` carry the history.

1. **Never animate the canvas per-frame.** § 2.1. `tests/test_frame_pacing.py` guards it.
2. **No fabricated data in the UI.** § 2.2.
3. **Never connect to OBS on the Tk thread** — `obs.connect()` blocks up to 5s and at startup
   that's the *normal* case. Worker + `_ui()` marshal back.
4. **`except X as e` unbinds `e` at block exit** — bind to a local before building any
   closure that runs later via `after()` / `_ui()`. Under `pythonw` the resulting crash is
   **silent** (stderr doesn't exist); `report_callback_exception` → the app log is what makes
   it visible. Don't remove it.
5. **Logging is coalesced** — `_log` appends to a buffer under a lock; `_flush_log` batches
   the textbox write on the Tk thread. A per-line write is a window composite each; a burst
   pegged the UI at 371ms before this.
6. **`_regen_glass()` stays cached** — ~35ms a regen, re-rendered on every state change.
7. **`Offloader` never deletes a local clip without a byte-verified NAS copy.** If the Clips
   pane grows a delete action (frame 2b has one), it must respect this.
8. **`GameSync.push()` must never PUT against an unknown remote** — a failed fetch returns
   None rather than treating the remote as empty.
9. **Don't use `os.path.dirname(__file__)` for user data** — use `obsauto/paths.py`'s
   `APP_DIR`; under a frozen onefile build `__file__` is inside a temp dir that's deleted.

## 5. Running it

```bash
python main.py
```

```bash
pyinstaller nebula.spec
```

Tests need a desktop session (no OBS required). Anything async **must** be tested under a
real `mainloop()` — Tk refuses a cross-thread `after()` when driven by `update()`-pumping and
`_ui()` swallows it, which has hidden real behaviour twice.

```bash
python tests/test_views.py
```

```bash
python tests/test_frame_pacing.py
```

Cheap orientation without reading files — the graphify graph is current:

```bash
graphify query "where does the hero card set its state"
```

## 6. Memory / notes convention

Durable facts go to the Obsidian vault at `C:\Users\antho\Claude Memories\claude-memory`,
**not** into this repo. One atomic note per fact in `memory/`, wikilinks between them, and a
one-line pointer added to **both** `memory/index.md` and `memory/MEMORY.md`. Cursor marks its
own notes with `metadata.origin: cursor` and adds `last_touched_by: cursor` only on
substantive edits — see `memory/claude-cursor-coexistence.md`. Existing Nebula notes:
`nebula-aurora-ui`, `nebula-dpi-scaling`, `nebula-roadmap-ideas`, `obs-auto-folder`.
