# Paste-into-Cursor prompt — Nebula UI v3

**Purpose:** hand the v3 build to Cursor at any moment, mid-stream, without losing context.
Open `C:\Users\antho\nebula` in Cursor and paste everything below the line.

**This file is kept current.** The "State right now" section is updated as work lands, so
whatever it says is true at the moment you paste it. Check `git log --oneline -5` and
`git status` if you want to confirm.

---

Hi — you're picking up the **Nebula UI v3** build from Claude Code. Nebula is a Windows
desktop app (Python + CustomTkinter, drawing on a `tk.Canvas`) that watches for the active
game, drives OBS recording over obs-websocket v5, and sorts recordings into per-game folders.

## Read these first, in this order

1. **`CURSOR-HANDOFF.md`** (repo root) — the full brief. Section 2 is the important part:
   three places the v3 spec collides with hard, *measured* constraints in this repo.
2. **`design/ui-v3/BUILD-SPEC.md`** — section 05 of the mockup, "the contract". This is the
   authority for every number. The mockup says so itself: *"If a frame and this table
   disagree, this table wins."*
3. **`design/ui-v3/FRAMES.md`** — frames 2a–2k: what each screen contains and its rules.
4. **`CLAUDE.md`** — how the codebase actually works, and the performance history.
5. `obsauto/design_v3.py` — the contract as code. **Import from here; never re-declare a
   literal.** `over(fg, alpha, bg)` composites an alpha to a flat hex, because canvas items
   have no alpha channel.

`.cursor/rules/nebula-ui-v3.mdc` should load the essentials automatically — but read
`CURSOR-HANDOFF.md` properly before your first edit to `obsauto/gui.py`.

To see the design: open `design/ui-v3/Nebula UI Mockups v3.dc.html` in a browser (needs
network — it pulls Geist and Phosphor from CDNs).

## Two decisions already made — don't silently reverse them

- **The background is static, randomised per launch.** The spec's aurora drift, star drift and
  pointer spotlight are browser-compositor idioms. Here, *any* canvas change forces a full
  window composite at a **flat** ~100ms — a 2px star costs the same as the whole nebula. A
  12fps timer measured p50 110ms frames at 95% CPU; removing it gave 16ms at 4%. So: seed the
  RNG at launch, render the aurora + starfield **once** into the backdrop image. That still
  satisfies the spec's actual requirement — *"randomised per launch, never hard-code blob
  positions or star coordinates"*. `BACKGROUND_MOTION_UNUSED` in `design_v3.py` quarantines the
  motion values, and `tests/test_design_v3.py` fails if `gui.py` reads them.
- **The window stays fixed-pixel at 1280×808**, multiplied by `self.scale` for high-DPI as
  today. The spec's 1080×700 minimum is not honoured as a resizable floor, because every pane
  in the frames is drawn at exactly 1048×746 — nothing shows a second width. Going fluid later
  is additive; see handoff §2.4.

## The rule that matters most

**Never animate the `tk.Canvas` per-frame.** `tests/test_frame_pacing.py` exists to fail if a
per-frame timer comes back. Two earlier diagnoses of this were wrong and cost real time — the
cause is *window-level compositing*, not how much you changed. Don't reopen it.

Second most important: **no fabricated data.** Every number in the frames is mockup filler. If
a value has no real source, build the source or omit the element — never a plausible
placeholder, and never a `0` that silently means "not implemented". Frame 2e draws a
*connected* macropad with an HID id and a live key map; **there is no HID layer in this
codebase at all**. Handoff §2.2 audits every element into real / derivable / no-source.

The other repo invariants (async OBS connect, the `except X as e` closure trap, coalesced
logging, the glass cache, the offload copy-verify-delete rule) are listed in
`CURSOR-HANDOFF.md` §4 and explained in `CLAUDE.md`. They outrank the mockup.

## Build order — from the spec, follow it

1. **Chassis** — tray, core, titlebar, 232px rail, empty pane. Nothing else until it matches
   frame **2a**.
2. **Hero card + its 4 states from one enum** (recording / watching / paused / disconnected),
   then stat tiles, then the activity log.
3. **Tray + window chrome** — `−` and `×` both hide; **Quit only in the tray menu**.
4. **Single-slot toast** — replace-in-place, 4s drain, hover freeze. Build the replace path
   before the visuals.
5. **Clips pane.**
6. **Settings** — the mono config-key labels under each field are part of the design. Write on
   blur, not per keystroke. Merge over `DEFAULTS`; never drop an unknown key.
7. **Games, Macropad, mini overlay last.** Mini overlay never shows while idle.

## Running it

```
python main.py
pyinstaller nebula.spec          # -> dist/Nebula.exe; doesn't track source, rebuild after pulls
```

Tests need a desktop session, no OBS required. **Anything async must be tested under a real
`mainloop()`** — Tk refuses a cross-thread `after()` under `update()`-pumping and `_ui()`
swallows it, which has hidden real behaviour twice.

```
python tests/test_design_v3.py    # v3 contract vs BUILD-SPEC.md — no GUI needed
python tests/test_views.py        # every pane opens; layout reorders + persists
python tests/test_frame_pacing.py # visible-window frame budget — the guard rail
```

`graphify query "your question"` answers where/how questions off a local graph without reading
files.

## Notes and memory

The Obsidian vault at `C:\Users\antho\Claude Memories\claude-memory` is the **only** memory
store — never put durable notes in this repo. One atomic note per fact in `memory/`, wikilinks
between them, and a pointer line added to **both** `memory/index.md` and `memory/MEMORY.md`.
Mark your notes `metadata.origin: cursor`; add `last_touched_by: cursor` only on substantive
edits to someone else's note, and only inside an existing `metadata:` block. Preserve other
provenance fields. Rules of engagement: `memory/claude-cursor-coexistence.md`.

Existing Nebula notes: `nebula-ui-v3` (this work), `nebula-aurora-ui` (the v2 build and its
performance lesson), `nebula-dpi-scaling`, `nebula-roadmap-ideas`, `obs-auto-folder`.

---

## State right now

<!-- STATE:BEGIN — keep this block current; it is the whole point of the file -->

**Updated:** 2026-07-26 — **steps 1 and 2 are done and verified. Step 3 is next.**

**Done — the import and the contract**
- v3 design files imported to `design/ui-v3/` from Claude Design project
  `19d87879-67c8-4a4e-8eb1-d4fbd327a23a` via the DesignSync MCP.
- `BUILD-SPEC.md` + `FRAMES.md` transcribed; `CURSOR-HANDOFF.md` written with the collision
  analyses.
- `obsauto/design_v3.py` — tokens, geometry, type scale, icon legend, config map, hero-state
  enum, `over()` / `hairline()` / `font()` helpers.
- `tests/test_design_v3.py` — 33 checks. Parses `BUILD-SPEC.md` back and compares, so the
  transcription can't rot silently.

**Done — step 1, the chassis (matches frame 2a)**
- **Palette** is Nebula Deep, sourced from `design_v3`. v2's GREEN/AMBER/TEAL/BLUE/PINK are
  collapsed onto accent-vs-ember aliases rather than deleted, so every call site migrated in
  one move. `LOG_TAG_COLORS` keeps its own hues as literals — the spec's one sanctioned
  exception.
- **Structure changed**: the titlebar now spans the full window width (h46) with the rail
  hanging beneath it, where v2 had a full-height rail and a content-column-only topbar. New
  `CONTENT_Y0` / `_content_y0()`.
- **Backdrop** is `theme_art.generate_backdrop_v3()` — 3 aurora blobs, 2 star layers,
  vignette, all from the spec's values, seeded per launch, rendered **once** (~66ms). It
  replaced v2's three separate layers, which also removed the drifting bloom that
  `self._composite` couldn't sample.
- **Rail** (232 / pad 16,12 / item 38 / gap 3) with the five v3 destinations and a real
  storage card at its foot (path, fill bar, "X free of Y" from `shutil.disk_usage`).
- **Titlebar** carries the version badge (reads `obsauto.__version__`, newly added — the
  mockup's literal `0.9.2` would have been fabricated), the monitoring toggle + keycap, and
  the OBS readout. `−` and `×` both hide, as the spec requires.
- **Pane header** (h62, pad-x 26) with tracked eyebrow + title + right-aligned ghost actions.
- **Fonts**: `dv.resolve_fonts()` probes what Tk can actually see. Two real gotchas found —
  "Segoe UI Variable" is three *optical-size* families, not one, and Tk truncates family names
  at 31 chars (`Segoe UI Variable Display Semib`). **Cascadia Mono is not installed** on this
  machine, so the numeric face falls back to Consolas. Sizes are passed **negative** = CSS
  pixels, since the spec's type scale and the layout geometry are in the same units.
- **Icons**: the spec wants Phosphor Light, which isn't installed. `ICON_GLYPHS` maps the
  spec's roles onto **Segoe Fluent Icons** (Windows 11's own, already present). Every
  codepoint was verified by rendering it. Swapping in a real Phosphor TTF is a change to that
  one table.
- **`recordings` → `clips`** renamed throughout, including tests.
- **Tests all green**: design 33, views 41, list-views 5, gamesync 14, offload 15,
  async-connect 11, plus frame pacing — **p50 16.1ms**, i.e. unchanged from v2 despite the
  window being 16% larger. The static-backdrop decision holds.

**Done — step 2, the hero card and the dashboard blocks**
- **Hero is a double bezel** — outer tinted shell at r22, darker inner core at r17, 5px tray,
  22px padding. "A flat card is a bug"; the stat tiles got the same two-layer treatment.
- **Four states from one enum** (`_set_hero_state`), matching frames 2a and 2f–2h. Each swaps
  the eyebrow, the tint, both button labels **and both button bindings** —
  disconnected → `Retry now` / `Connection settings`, watching → `Record anyway` /
  `Pause monitoring`, recording → `Stop recording` / `Pause`, paused → `Resume` / `Stop & save`.
  `_poll_obs_status` no longer touches button labels at all; it only sets enablement, so the
  enum is the single place state is expressed. v2's `"offline"` was renamed `"disconnected"`.
- **Ember leads on exactly one state.** Recording is accent-tinted, not red — v3 is a two-hue
  system and 2h says disconnected is "the only place the ember hue leads".
- **Paused dims the timer to 60%**, composited against the card core (canvas items have no
  alpha).
- **The badge sizes itself to its eyebrow.** Fixed-width overflowed on two states and collided
  with the subtitle; `_text_w()` measures in base design units with a cached font object.
- **Bitrate is real.** The frame draws "14.2 Mb/s" and OBS's status carries no bitrate field,
  so `_update_bitrate()` derives it from the byte/duration delta between successive
  `GetRecordStatus` polls, and shows **nothing** until it has two samples ≥500ms apart. A test
  feeds it a known delta and asserts it lands on 14.2 Mb/s.
- **Stat tiles and the activity header** restyled to v3 type, icons and radii.
- **Tests: 137 checks + frame pacing, all green.** `test_views.py` grew to 59, including a
  four-state hero matrix and the bitrate derivation. Frame pacing still **p50 16.1ms**.

**Not started — step 3 onward**
- Steps 3–7: tray/chrome rework, single-slot toast, Clips, Settings, Games, Macropad,
  mini overlay. Step 3 is next: `−` and `×` already both hide, but the tray menu still needs
  the 2j treatment (header block that isn't a menu item, Quit only there, icon per state).
- **Transitional wart**: v3 has no standalone Activity page (it's a dashboard block), but the
  `activity` view is still registered and still mirrors the log, because `_log()` writes to
  both consoles. Not reachable from the rail — see `gui.RAIL_VIEWS`. Fold it away when
  convenient; it was left alone in step 2 to avoid churning the log plumbing.

**Deliberate departures from the frames — don't "fix" these without deciding**
- **No "Mark clip" button** (frame 2a shows three). There is no clip-marking backend, and a
  button that silently does nothing is worse than an absent one. Same reason v2 dropped it.
- **Stat tiles are Clips today / Disk free / Idle timeout / Sync**, not the frame's
  `Clips today / Recorded / Auto-culled / Idle pauses`. The last two have no counters anywhere
  in `Monitor`. Add the counters and they can have their tiles; don't ship them showing `0`.
- **The scene preview is still v2's stylised gradient tile**, including its static equaliser
  bars. It is decoration, not a claim about the capture — but the bars do imply audio levels
  we don't measure, so if you want strict honesty that is the thing to remove. The frame's
  `Live` chip and `2560×1440 · 60 fps` are obtainable from OBS `GetVideoSettings` if you want
  them for real; a periodic *thumbnail* is not (it's a repaint — see the background rule).

**Known open questions**
- Clip thumbnails (frame 2b) would need ffmpeg — new dependency, undecided.
- The rail has a large empty span between Settings and the storage card, exactly as frame 2a
  draws it. Left as designed; flag it if you'd rather it carried something.

<!-- STATE:END -->
