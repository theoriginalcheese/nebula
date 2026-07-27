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

**Updated:** 2026-07-27 — **v3 build complete on `main`; Cursor closed the last
implementable fidelity gaps.** Hand remaining live-OBS QA + packaging to Claude via
`CLAUDE-FINALISE-PROMPT.md`.

On branch **`main`** (includes the former `ui-v3` work + fine-detail + OBS meta).

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

**Done — step 3, tray + window chrome (frame 2j)**
- **Three tray icon states** from `icon_art.render_state_icon()` — idle = accent outline,
  recording = ember filled, disconnected = neutral with a slash. A test asserts they stay
  distinguishable **after shrinking to 16px**, which is why disconnected gets a slash and not
  just a colour change.
- **The permanent 12fps tray animation is gone.** The spec wants the icon to mean something;
  a spin meant nothing and redrew forever. `CLAUDE.md`'s old "the tray icon still animates"
  line was corrected.
- **Menu matches 2j**: a disabled two-line header (state, then `game · elapsed`), Show Nebula
  as the `default` item so a single click opens the window, Pause/Stop **only visible while
  recording** (Pause becomes Resume when paused), a Monitoring toggle carrying a checkmark,
  Open recordings, and Quit Nebula. Menu text is callables, so it is re-evaluated each time
  the menu opens; every action marshals back to the Tk thread via `root.after(0, ...)`.
- **Header block honesty**: the spec says it is "not a menu item — not hoverable, not
  clickable". A native Win32 tray menu can only contain items, so the true equivalent is a
  **disabled** item, which Windows neither highlights nor activates. Two of them, since an
  item can't be two lines. Verified with real pystray, not just the stub.
- 🐛 **Fixed a pre-existing bug**: `_obs_connected` was declared in `__init__` and then
  *never assigned* — it sat `False` for the entire run. Nothing read it until the tray needed a
  disconnected state, which would have pinned the icon to the slashed variant forever. It is
  now kept in step in both `_on_connection_change` and `_poll_obs_status`.
- `tests/test_tray.py` — 26 checks, no OBS and no real tray registration needed.

**Done — step 4, the single-slot toast (frame 2i)**
- **One Toplevel for the whole process life.** The first event builds it; every later event
  *mutates* it and resets the drain. v2 destroyed and rebuilt per event — a queue of one with
  extra steps, and it flickered because a fresh Toplevel maps at the new position instead of
  updating the one already on screen. `_toast_replace()` is the replace path and was built
  first, as the spec instructs.
- **4s life, 2px drain, reset to full on replace.** Hover freezes it, leaving resumes.
  Click anywhere calls `show()`.
- **Drain direction settled from the source, not guessed**: the mockup has exactly one
  `transform-origin: left` in the whole document and it's on the drain, so `scaleX(1)→scaleX(0)`
  anchors the bar left and its right edge travels leftward. That's what's implemented.
- **Tints from `dv.TOAST_TINTS`** — start/stop/error ember, pause/resume accent — with a
  matching Fluent glyph per event.
- **Positioned on the *active* screen**, 24px from both edges of the **work area** (so "above
  the taskbar" falls out for free). `_toast_workarea()` uses `MonitorFromPoint` on the cursor;
  v2 used `winfo_screenwidth()`, which is the *primary* monitor — on a multi-monitor setup the
  toast could appear on a screen you weren't looking at.
- **Entrance is a 16px rise + fade over 320ms; exit is a 200ms fade** (no slide). A replacement
  arriving mid-fade **cancels the dismissal** and takes the window back rather than racing the
  destroy — there's a test for exactly that.
- Animating here is free, unlike the main window: a Toplevel is its own surface, so the fade
  never composites the dashboard.
- `tests/test_toast.py` — 40 checks.
  ⚠️ **If you extend those tests, never call `_toast_tick()` by hand.** The toast keeps exactly
  one self-rescheduling tick chain; a manual call spawns a second and the life drains at double
  rate, which looks like a product bug and isn't. Set `remaining` and let the real chain run.
  There's a check that asserts the 1× drain rate.

**Done — step 5, the Clips pane (frame 2b)**
- Lists the **clips**, not v2's per-game folders: by-game sidebar with counts, search, sort
  (Newest / Oldest / Largest), and rows carrying a game-initials chip, filename, relative path,
  size and a relative "Recorded" label. Newest 400 shown; beyond that it says so rather than
  crawling a terabyte root into the UI.
- **Empty state is the min-clip note only**, exactly as the build order states.
- **Delete obeys copy-verify-then-delete.** If offload is on and the clip is still in the
  offloader queue — i.e. no byte-verified NAS copy yet — the delete is **refused outright**,
  not merely confirmed. Everything else asks first. `Offloader.pending_paths()` was added for
  this. A UI delete must not be a way around `obs-footage-sacred`.
- **Two frame columns omitted for want of a source**: **Length** and **thumbnails** both need
  ffprobe/ffmpeg, which this project does not depend on. The frame's leading chip is the game's
  initials (real data), so that stayed. Add ffmpeg and both can come back.
- Initials are word-initials: "Helldivers 2" → `H2`. The frame draws `HD`, which is not
  derivable from the name.
- `tests/test_clips.py` — 22 checks against a temp recording root.
  ⚠️ It runs under a **real `mainloop()`**: the scan is a worker that marshals back through
  `_ui()` → `root.after`, and Tk refuses a cross-thread `after()` under `update()`-pumping while
  `_ui()` swallows the failure. An `update()`-pumped version of this test sat on "Scanning…"
  forever. Same trap `CLAUDE.md` warns about; it cost time again here.

**Done — step 6, editable Settings (frame 2c) — merged with your branch**

Your `cursor/editable-settings-view-dd92` branched from `c1e4f37`, i.e. **before** all the
v3 work, so it was a parallel Settings editor on the old Aurora UI rather than a change on
top. Rather than pick one, the good parts were taken onto `ui-v3`:

- **`settings_spec.py` adopted wholesale.** It's the better source: pure and testable with no
  Tk window, covers **every** key in `DEFAULTS` (not only the thirteen in the v3 table), and
  carries validation bounds plus a `restart` reason per field. The pane now renders it.
  `dv.CONFIG_MAP` stays as the transcribed spec table that `test_design_v3` checks against
  `BUILD-SPEC.md`.
  ⚠️ **Deviation from the frame, on purpose**: the section rail is `settings_spec.GROUPS`
  (OBS / Recording / Hotkey / Game list sync / NAS offload / Legacy), not 2c's five names. A
  Settings page that can't edit `github_token` or `nas_offload_root` would be worse than one
  that departs from the frame's rail.
- **Live reconfigure adopted** (`hotkey.unregister`, `Offloader.refresh`,
  `GameSync.configure`, `AudioKeepAlive.set_processes`). `_settings_apply_live()` routes each
  edited key to its owner. Genuinely new capability; the v3 pane alone still needed a restart.
- **`test_settings_typing.py` adopted** — and it settled the open question in its own docstring.
  It was written on Linux where the claim couldn't be checked. Measured here: **0.1ms per
  keystroke**, event loop 49/s typing vs 48/s idle. The ~100ms composite rule is about **canvas
  mutations**; `CTkEntry` is a native widget and doesn't touch the canvas. An in-view form is
  fine. Its other point stands and is worth keeping: `test_frame_pacing`'s p50 is **blind** to
  per-keystroke cost, because keystrokes are sparse relative to the heartbeat.
- **Not taken**: your `gui.py`, `CLAUDE.md`, `README.md` and `tests/test_settings.py`, all of
  which target the pre-v3 UI. Your `offload.py` overwrote `pending_paths()` (added for the
  Clips delete rule) — restored.

The pane itself keeps 2c's rules: write on blur (and Return), saved timestamp in the header,
`seconds` suffix on `*_seconds`, mono config-key caption under every label, whole-dict write so
unknown keys survive. Junk in a bounded field is refused and reverted, reported to the log
rather than inline — that keeps typing at one composite per keystroke.

`tests/test_settings.py` — 27 checks, saves intercepted.

**Done — step 7: Games (2d), Macropad (2e), mini overlay (2k)**

- **Games**: three blocks — unclassified, games, ignored apps — with a real pending count in the
  header and a footer that says whether the list is GitHub-synced or local only.
  Right-click an ignored app to move it back to Games (confirms first, then re-marks and pushes
  to the shared list).
  **Read-only unclassified block on purpose**: deciding still happens in the existing modal
  flow, which owns the queue's `_in_review` bookkeeping. `Classifier.peek_pending_reviews()`
  was added so displaying an item can never swallow the prompt the user is waiting on —
  `pop_pending_reviews()` remains the only thing that drains.
  **Omitted for want of a source**: the Steam AppID beside each game (the classifier stores
  `{display_name, source}`, no id) and "seen 4×" (nothing counts sightings).
- **Macropad stays empty.** Frame 2e draws a *connected* pad with `HID 0x1209:0xA1B2`, a live
  3×3 key map and a last-keypress readout. There is still no HID code anywhere in `obsauto/`.
  The page says so. To build it properly you need, in order: an HID input layer, a persisted
  binding map in config.json, then the pane — and bindings must be by **scan code**, not
  character (`toggle_hotkey_scancode`; see the vault's `asus-m4-fan-key`).
- **Mini overlay**: 296×54, frameless, always-on-top, drag anywhere, snaps to the nearest
  corner within 32px, remembers its position **per monitor** (keyed by the monitor's work-area
  rect, so docking to a different display can't strand it off-screen), drops to 55% opacity
  after 3s and back to full on hover. Collapse restores the main window. **Never opens while
  idle** — it refuses out loud rather than vanishing the button, and closes itself the moment
  a recording ends. Entered from the new titlebar button (`arrows-in-simple`, per the icon
  legend). It mirrors the hero's clock rather than running its own, so the two can't disagree.
- `tests/test_step7.py` — 33 checks.
  ⚠️ **Two traps worth knowing.** CustomTkinter proxies `bind()` onto an inner widget, so
  `event_generate()` against a row never reaches the handler even though a real click does —
  hence `_promote_non_game()` exists as a directly callable action. And this test **redirects
  `classifier.DATA_FILE` to a temp dir**: it marks and promotes apps, and `Classifier._save()`
  *merges with what is on disk* (so a synced file never loses entries), which means popping a
  key in memory and saving quietly puts it back. Don't run classification tests against the
  real `games.json`.

**The v3 build order is complete.** Cursor (2026-07-27) also:
- Folded away the transitional standalone Activity view (dashboard block only).
- Wired real OBS metadata on a worker: `GetVersion` → titlebar, `GetVideoSettings` →
  hero res/fps chip, `GetCurrentProgramScene` → scene caption, handshake ms → Settings
  OBS footer + Test again. Helpers: `short_obs_version`, `format_video_label`
  (`tests/test_obs_meta.py`).
- Documented frame **2l** in `FRAMES.md` (it is the build-spec sheet, not a pane).
- Bumped titlebar circle hit targets to 30px.

**Still for Claude (see `CLAUDE-FINALISE-PROMPT.md`):** live-OBS visual QA, rebuild
`dist/Nebula.exe`, and the deliberate open gaps (ffmpeg Length/thumbs, Auto-culled /
Idle pauses counters, Mic meter, Mark clip, Macropad HID, Phosphor TTF vs Fluent).

<!-- STATE:END -->
