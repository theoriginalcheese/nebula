# OBS auto-folder

Windows desktop app (Python + CustomTkinter) that watches for the active game, drives
**OBS** recording over the obs-websocket v5 API, and sorts recordings into per-game folders.
Runs from the system tray. Active code lives in the `obsauto/` package; `main.py` is the entry point.

## Run (development)
```
pip install -r requirements.txt
python main.py          # or: pythonw main.py  (silent, no console — how it runs day-to-day)
```
Starts minimized to the tray and auto-connects/monitors on launch (`AppWindow.autostart`).

## Build (packaging)
```
pyinstaller nebula.spec   # -> dist/Nebula.exe (single-file, windowed, UPX-compressed, icon nebula_icon.ico)
```
One onefile exe — no separate install of Python/dependencies needed to run it. Targets
`main.py` (the real entry point; the legacy `obs_auto_game_folder.py`/`.spec` are gone).

⚠️ **Gotcha:** don't reintroduce `os.path.dirname(__file__)` for user data paths
(`config.json`, `games.json`, `steam_appid_cache.json`, `logs/`). Under a frozen onefile
build, module `__file__` resolves inside PyInstaller's temp extraction dir
(`sys._MEIPASS`), which is deleted on exit — anything written there vanishes every run.
Use `obsauto/paths.py`'s `APP_DIR` (next to `sys.executable` when frozen) for user data,
and `RESOURCE_DIR` (`sys._MEIPASS` when frozen) only for bundled read-only assets like
`nebula_icon.ico`.

## Architecture (module map)
| File | Key symbols | Role |
|------|-------------|------|
| `main.py` | `main()`, `_apply_sync_folder()` | Wiring: logging → config → Classifier → AppWindow + tray |
| `obsauto/monitor.py` | `Monitor` | Core loop: foreground/idle detection, ensure/launch OBS, start/stop + retarget recording |
| `obsauto/obs_client.py` | `OBSClient`, `OBSError` | Minimal obs-websocket **v5** client |
| `obsauto/classifier.py` | `Classifier` | Game vs non-game classification (Steam-aware hybrid) |
| `obsauto/steam_scanner.py` | `build_steam_game_index()` | Scan Steam libraries, parse VDF, classify AppIDs |
| `obsauto/gui.py` | `AppWindow` | CustomTkinter UI: "Aurora" shell (nav rail + tile-grid dashboard), glass/rounded chrome |
| `obsauto/gamesync.py` | `GameSync` | Game-list sync via GitHub contents API — pull on start, push on change, merge-never-clobber, fails soft |
| `obsauto/offload.py` | `Offloader` | NAS recording offload — copy → SHA-256 verify → (move mode) delete local; persisted queue, retries |
| `obsauto/audio_detect.py` | `AudioKeepAlive` | Detect whether a watched app (e.g. Discord) is producing audio |
| `obsauto/session_detect.py` | `moonlight_session_active()` | Detect a live Moonlight streaming session |
| `obsauto/config.py` | `load_config()`, `save_config()` | Config persistence |
| `obsauto/paths.py` | `APP_DIR`, `RESOURCE_DIR` | Dev vs. frozen-onefile path resolution |
| `obsauto/app_log.py` | `setup_logging()`, `log_to_file()` | File logging (works under silent `pythonw`) |
| `obsauto/design_v3.py` | `COLORS`, `CARD_LAYERS`, `CONFIG_MAP`, `over()` | UI **v3** design contract as code — see below |
| `obsauto/session_log.py` | `append()`, `spans()`, `today()` | Append-only `sessions.jsonl`: rec_start/rec_stop/idle_in/idle_out/mark. The stat tiles, ribbon and forecast all read it |
| `obsauto/replay.py` | `ReplayBuffer` | Instant replay (7a) — arms OBS's RAM buffer, files what it saves. Never holds video itself |
| `obsauto/thumbs.py` | `ThumbWorker`, `duration_of()` | Clip thumbnails + Length (7f). ffmpeg is an **optional** soft-dep |
| `obsauto/forecast.py` | `forecast()`, `cull_candidates()` | Storage forecast (7c) — GB/h → days left, and what a cull would take |
| `obsauto/palette.py` | `search()`, `subsequence()` | Command-palette matching + ranking (7e), no UI |
| `obsauto/profiles.py` | `sanitise()`, `plan()`, `apply()` | Per-game encoder profiles (7d), with the scope guard on read *and* write |
| `obsauto/tray_app.py`, `theme_art.py`, `icon_art.py` | — | Tray icon + generated icon/theme art |

Most-connected hubs (start here when orienting): `AppWindow`, `OBSClient`, `Monitor`, `Classifier`.

## UI layout — the "Aurora" shell (`obsauto/gui.py`)
A 1180×760 fixed-pixel canvas design (base design units; `self.scale` multiplies everything
for high-DPI — see the DPI notes below). Built by five `_build_*` methods:
- `_build_sidebar` — 236px nav rail: logo, WORKSPACE nav items, and at the bottom the OBS
  connection card + clickable "Monitoring on/off" toggle (same action as the hotkey).
- `_build_topbar` — title, Rescan / Game data ghost buttons, minimise + close.
- `_build_hero` — the cinematic status card. `_set_hero_state()` switches it between
  **offline / watching / recording / paused**, owning the badge, subtitle, border tint,
  readout visibility and transport buttons. `_poll_obs_status()` picks the state from OBS's
  own `GetRecordStatus` and fills the elapsed/size readouts.
- `_build_stats` — four tiles: Today (real scan of `recording_root`), Disk free, Idle timeout
  (holds the live slider), Sync.
- `_build_activity` — the real colour-tagged log (`self.console`).

### View switching
Every view's canvas items are tagged `view_<name>`, collected by diffing `find_all()` around
each builder — so builders stay plain drawing code with no bookkeeping. Switching is one
`itemconfigure` per tag. Two consequences to respect:
- Showing a tag un-hides items a view deliberately keeps hidden. `_show_view("dashboard")`
  re-applies `_set_hero_state()` and `_set_customise()` afterwards for exactly this reason.
- Each view rewinds `self._composite` to `_base_composite` before building, so embedded
  widgets sample the shell and not whichever view happened to paint there first.

### Rearrangeable dashboard
Dashboard panels are additionally tagged `blk_<name>`. A canvas `move()` shifts every item
with a tag (embedded widget windows included), so reordering is pure translation — which is
why block heights are **fixed** (`DEFAULT_BLOCKS`, `BLOCK_GAP`). Order persists as
`dashboard_layout` in config.json; `_saved_layout()` drops unknown names and appends missing
ones so a hand-edited file can never lose a panel.

Views backed by real data: Recordings (scans `recording_root`), Games (reads the classifier),
Activity, Settings (read-only). **Macropad is deliberately empty** — there's no binding layer,
and a mock keypad that does nothing would be a lie.

⚠️ Don't put fabricated numbers in the UI — the Games badge reads the classifier
(`_game_count()`) and returns `None` (no badge) rather than inventing a count.

## UI v3 pass 2 — the mockup grew (2026-07-27)

The Claude Design mockup went from 151 KB to 347 KB. Sections 01–05 are
unchanged; everything new is **§06** (a twelve-item fix list against the shipped
build) and **§07** (six new features + their build order). All thirteen steps are
done and on `main`. **`design/ui-v3/V3-PASS-2.md` is the record** — the plan, the
decisions, what each step found, and what is deliberately not built.

⚠️ **Re-importing the mockup:** the DesignSync MCP caps `get_file` at 256 KiB, so
it returns the file truncated mid-tag and sections 7c–7g vanish with no error.
The full copy is committed. Pull through the design RPC if you must re-fetch.

Things this pass established that are easy to break again:

- **The aurora measured literally zero.** `layer.paste(blob, pos, blob)` passes
  the blob's alpha as its own mask, squaring it. `tests/test_background.py`
  measures each layer against the one below rather than checking it renders.
- **The background is two surfaces.** `generate_backdrop_v3` returns the painted
  stack *and* a starless one; every panel composites over the starless copy, so
  the aurora reads through a card but the dust never does. `_composite` (what
  widgets sample for their corner blend) is seeded from it too.
- **Cards come from one table.** `dv.CARD_LAYERS` — never choose radii at a call
  site. `_card()` is the only thing that draws one.
- **Hero visibility goes through `_hero_vis()`.** `_poll_obs_status` calls
  `_set_hero_state` every second, so anything that un-hides a hero item without
  asking "is the dashboard showing?" reappears over whatever pane you navigated
  to. That was a real bug.
- **A classification merge cannot be a plain union.** See the sync section below.
- **ffprobe reports no duration for a file still being written** — Matroska
  writes it on finalisation. That is correct, not a failure; don't paper over it.

## UI v3 — complete on `main` (2026-07-27)

**All seven steps of the v3 build order are done** and merged to `main`: palette,
geometry, backdrop, titlebar, rail, pane header (frame 2a); the hero card with its four states
(2a, 2f–2h) plus stat tiles and activity header; the tray icon + menu (2j); the toast (2i); the Clips pane (2b); the editable Settings pane (2c); Games (2d); and the mini overlay (2k).
**Macropad (2e) is deliberately empty** — there is still no HID layer, and the frame draws a
connected device. Titlebar / hero / Settings now show real OBS version, res/fps, scene name
and handshake ms (worker-fetched). Final polish handoff: `CLAUDE-FINALISE-PROMPT.md`.
Full state: `CURSOR-PROMPT.md`.

**The toast is a single slot.** One `Toplevel` for the whole process life — the first event
builds it, every later event mutates it in place and resets the drain (`_toast_replace`).
Never a stack, never a queue. It keeps exactly **one** self-rescheduling tick chain, so don't
call `_toast_tick()` from outside: a second chain drains the life at double rate.
Animating a toast is free, unlike the main window — it's a separate surface.

**The tray is state-driven** (`icon_art.render_state_icon`, `AppWindow.tray_status()`): three
icons — idle accent outline, recording ember filled, disconnected neutral-with-a-slash — and a
menu whose text is callables, re-evaluated each time it opens. Quit exists **only** there; both
`−` and `×` hide. `tests/test_tray.py` covers it, including that the icons stay
distinguishable once shrunk to 16px.

**The hero is one enum.** `_set_hero_state()` owns the eyebrow, tint, both button labels *and*
both button bindings for `disconnected | watching | recording | paused` (v2's `"offline"` was
renamed). `_poll_obs_status()` deliberately no longer touches button labels — only enablement —
so there is exactly one place the state is expressed. Recording is **accent**, not red: v3 is a
two-hue system and ember leads only on a real disconnection.

⚠️ **Bitrate is derived, never drawn in.** `_update_bitrate()` computes it from the byte and
duration delta between successive `GetRecordStatus` polls and renders **nothing** until it has
two samples ≥500ms apart. Three frame elements were dropped rather than faked for the same
reason: the "Mark clip" button (no backend), and the `Auto-culled` / `Idle pauses` tiles (no
counters in `Monitor`).

What changed structurally: the titlebar is now full-width (h46) with the rail hanging beneath
it (v2 had a full-height rail and a content-column-only topbar), the window is 1280×808, and
`recordings` was renamed `clips`. `RAIL_VIEWS` is the five rail destinations — a **subset** of
the views, since v3 has no standalone Activity page.

Three things worth knowing before touching the chrome:
- **Fonts are probed, not assumed** (`dv.resolve_fonts`). "Segoe UI Variable" is three
  *optical-size* families, Tk truncates family names at 31 chars, and Cascadia Mono isn't
  installed here (falls back to Consolas). Font sizes are passed **negative** = pixels,
  because the spec's type scale is CSS px and the layout geometry is in the same units.
- **Icons are Segoe Fluent Icons**, not Phosphor (which isn't installed). `ICON_GLYPHS`
  translates the spec's roles; every codepoint was verified by rendering it.
- **The backdrop is generated once per launch** from a random seed
  (`theme_art.generate_backdrop_v3`, ~66ms). Frame pacing stayed at p50 16.1ms despite the
  bigger window.

Everything needed to build the rest:

- `design/ui-v3/` — the Claude Design mockup verbatim, plus **`BUILD-SPEC.md`** (section 05,
  "the contract" — the authority) and **`FRAMES.md`** (frames 2a–2k).
- `obsauto/design_v3.py` — that contract as code: the Nebula Deep palette, geometry, type
  scale, icon legend, config map, hero-state enum. `over()` composites an alpha to a flat hex,
  since canvas items have none. `tests/test_design_v3.py` (33 checks, no GUI needed) parses
  `BUILD-SPEC.md` back and fails if the two drift.
- **`CURSOR-HANDOFF.md`** — the full brief, including three places v3 collides with this repo.

The collisions, short form (long form in the handoff):
1. The spec's **living background** (aurora drift, star drift, pointer spotlight) is a browser
   compositor idiom and is **fatal here** — see "never animate the canvas per-frame" below.
   Resolution: render it **once at launch from a random seed**, which is what "randomised per
   launch, no two sessions alike" actually asked for. `BACKGROUND_MOTION_UNUSED` in
   `design_v3.py` quarantines the motion values; the test fails if `gui.py` reads them.
2. Most numbers in the frames are **mockup filler** (bitrate, auto-culled, idle pauses, and a
   whole connected macropad with an HID id). Build the source or omit the element.
3. v3 wants a **resizable** window (1280×808, min 1080×700) against today's fixed-pixel
   `ScaledCanvas`. Open decision — handoff §2.4 recommends keeping fixed-pixel.

## Settings editing (`obsauto/settings_spec.py`)

Fields are declared **once** in `settings_spec.py` - pure, testable without a Tk
window, covering every key in `DEFAULTS`, each with validation bounds and, where a
value can't apply live, the `restart` reason to show under the field. The pane walks
that list, so the two can't drift. `_settings_apply_live()` pushes edits into the
objects holding OS-level state: the hotkey hook must be torn down before rebinding
(a lingering `suppress=True` hook keeps swallowing the old key system-wide) and the
offload worker needs waking so a backed-off queue retries at once.

> ⚠️ **The ~100ms composite rule is about canvas mutations, not embedded widgets.**
> A worry that typing in a form would cost one full composite per keystroke was
> measured here: **0.1ms per keystroke**, event loop 49/s while typing vs 48/s idle
> (`tests/test_settings_typing.py`). CTkEntry is a native widget; it doesn't touch
> the canvas. Note that `test_frame_pacing`'s p50 is **blind** to per-keystroke cost
> - keystrokes are sparse relative to the heartbeat - which is why that test measures
> the keystroke directly.

## Single instance, and the two-data-directories trap

`main.py` claims a named mutex (`Nebula.SingleInstance`) at startup; a second
launch logs and exits. This is not theoretical - a dev `python main.py` running
alongside `dist/Nebula.exe` was observed fighting over the same OBS (the idle
timer flapped the recording on and off every few seconds, and one instance logged
`Start failed: SetRecordDirectory failed`), grabbing the same global hotkey, and
- because `APP_DIR` resolves **next to the executable** - reading *different*
`games.json` and `config.json` files, so one window's Games tab looked empty while
the other's was populated.

⚠️ **Frozen and dev runs do not share data.** The exe uses `dist/config.json`,
`dist/games.json`, `dist/logs/`; a source run uses the repo root. A setting changed
in one is invisible to the other. When checking whether a build works, read
`dist/logs/obsauto.log`, not `logs/obsauto.log`.

## Config (`config.json`)
- OBS: `obs_host` localhost, `obs_port` 4455, `obs_password` empty (obs-websocket v5)
- `recording_root`: `D:/OBS Recordings` · `sync_folder`: default **empty** (local only);
  set to `OneDrive/ObsAutoFolder` on this user's machines
- `idle_timeout_seconds` **4** · `min_clip_seconds` 10 · `poll_interval_seconds` 1
  (defaults per `obsauto/config.py`'s `DEFAULTS` — the live `config.json` may differ)

## Sync & offload invariants (don't weaken)
- **A classification merge must express removals, not just additions.** The two
  buckets are mutually exclusive, so a *reclassification* is a removal plus an
  addition — and a plain union reads the removal straight back out of the base.
  This ran in three places (local save, sync absorb, GitHub push), so promoting
  an ignored app left it filed as both, and the next pull did it again;
  `starrail.exe` was double-filed in two of the three real game lists here.
  There is now one `classifier.merge_classifications()`: a key lives in exactly
  one bucket, the newer view wins, other machines' additions still survive.
  `Classifier._heal()` repairs existing damage on load.
- **`GameSync.push()` must never PUT against an unknown remote.** If `fetch()` fails it
  returns None (refuse) rather than treating the remote as empty — otherwise a failed read
  overwrites and clobbers other devices' classifications (the stress test caught 156/160 lost).
  It loops fetch-merge-PUT on 409. `main.py` always pushes the **full** `classifier.snapshot()`
  and retries failures with backoff, so a dropped push is recovered by the next.
- **`Offloader` never deletes a local clip without a byte-verified NAS copy.** Copy → SHA-256
  both ends → only then (move mode) remove local. NAS unreachable / hash mismatch / short write
  → keep local, retry. Queue persists to `APP_DIR/offload_queue.json` (survives restart). This
  encodes [[obs-footage-sacred]] in code — don't relax it.
- **Logging is coalesced and thread-safe.** Workers call `_log` from their own threads; it only
  appends to a buffer under a lock, and `_flush_log` (Tk thread, ~80ms) batches the textbox
  write, capped to LOG_HISTORY with top-trim. A per-line textbox write is a window composite
  each — a burst pegged the UI at 371ms before this. Don't write the textbox from `_log` directly.

## Deferred-callback trap (bit us 2026-07-23 — check for it in review)
`except SomeError as e:` **unbinds `e` when the block exits** (Python deletes the except
target). So anything that captures `e` and runs *later* — a `lambda` handed to `root.after()`
or `_ui()` — dies with `NameError: cannot access free variable 'e'`. Bind it to a normal
local first (`error = exc`) before building the closure. This hit both the OBS connect
failure path and the Steam-rescan failure path.

Why it's dangerous here specifically: under `pythonw` (how the app really runs) Tk prints
callback tracebacks to a **stderr that doesn't exist**, so the crash is invisible. `AppWindow`
now installs `report_callback_exception` → `_on_callback_exception`, which writes them to the
app log instead. Don't remove that.

## ⛔ The big one: never animate the canvas per-frame
On this window, **any** canvas change forces a full *window-level* composite costing ~100ms at
1770×1140. The cost is **flat** — it does not scale with how much changed. Measured: moving the
full-window nebula image, swapping the 690px glow, and recolouring a single 2px star all cost
the same, and halving the canvas contents (187→141 items) barely moved it. It scales with
**window size**, which is why the Aurora redesign (1.6× the old area) is what exposed it.

So a ~12fps decorative animation timer wasn't "a bit expensive", it was fatal: **p50 110ms
frames (~9fps), one core at 95%**. Removing all of it gives **p50 16ms at ~4%**.

The backdrop (nebula drift, glow breathing, star twinkle), the hero equaliser and the REC dot
pulse are therefore all **static by design**. What remains mutates the canvas at most once a
second, and only while recording. `tests/test_frame_pacing.py` fails if a per-frame timer comes
back.

The tray icon used to animate — a separate surface, so it was never part of this problem — but
v3 retired the spin anyway: frame 2j wants the icon to *mean* something (idle / recording /
disconnected), and a permanent 12fps rotation said nothing while redrawing forever. It is now
three static icons swapped on state change.

> Two earlier diagnoses of this were **wrong** and cost time: "it's the big image moves" (no —
> a 2px star costs the same) and "it's the extra views' widgets" (no — dashboard-only is barely
> cheaper). Measure with the window **actually mapped**; profiling a withdrawn window skips real
> painting and understates everything by ~100×. And note that setting a timer method to a NOOP
> silently kills its reschedule loop, which invalidated a whole attribution run.

## Performance gotchas (fixed 2026-07-23 — don't reintroduce)
- **Never connect to OBS on the Tk thread.** `obs.connect()` blocks for up to its 5s socket
  timeout, and at startup that's the *normal* case (we've just launched OBS, it's still
  booting). `autostart()` used to do this inline and froze the whole window for seconds on
  launch, then again on every 10s retry. It now runs on a worker and marshals back via
  `_ui()`; `_abort_connect` stops a in-flight attempt from restarting monitoring after a stop.
- **`_regen_glass()` results are cached** (`_glass_cache`). Regenerating the hero panel costs
  ~35ms and it's re-rendered on every state change plus 5× per flash — uncached, a game
  switch stalled the UI ~200ms *and* leaked a PhotoImage per frame.
- **`generate_nebula` blurs downscaled** (`_blur_downscaled` in `theme_art.py`). Visually
  identical (max 2/255 per-pixel difference), meaningfully cheaper.
- **The Today-clips scan prunes by directory mtime** and polls every 5 min, so a terabyte-scale
  `recording_root` isn't crawled in full on a timer.

## Conventions & gotchas
- **Cross-machine sync:** `_apply_sync_folder()` repoints `games.json` and
  `steam_appid_cache.json` into `~/OneDrive/ObsAutoFolder` so classifications made on the
  laptop show up on the desktop. A *relative* `sync_folder` resolves against each machine's
  own `~`, so the same `config.json` works despite different Windows usernames.
- **Silent runs:** intended to run as `pythonw` (no console), so all diagnostics go through
  `app_log` to a file — don't rely on `print()`.
- **Tests** (need a desktop session, no OBS required):
  ```
  python tests/test_async_connect.py   # connect is async; nothing escapes into a Tk callback
  python tests/test_views.py           # every tab opens; modular layout reorders + persists
  python tests/test_list_views.py      # Recordings/Games actually populate (real mainloop)
  python tests/test_frame_pacing.py    # visible-window frame budget (briefly shows the window)
  python tests/test_design_v3.py       # v3 contract vs design/ui-v3/BUILD-SPEC.md (no GUI)
  python tests/test_tray.py            # tray icon states + menu contract (frame 2j)
  python tests/test_toast.py           # single-slot toast: replace-in-place, drain (2i)
  python tests/test_clips.py           # Clips pane + the delete rule (2b)
  python tests/test_settings.py        # editable Settings + config rules (2c)
  python tests/test_settings_typing.py # what a keystroke in a form really costs
  python tests/test_step7.py           # Games, Macropad honesty, mini overlay (2d/2e/2k)
  python tests/test_fidelity.py        # fine-detail conformance to BUILD-SPEC.md
  python tests/test_obs_meta.py        # GetVersion / GetVideoSettings string formatters
  python tests/test_transport.py       # start/stop/pause read OBS, not a stale flag
  python tests/test_games_pane.py      # promotion is reachable; the merge heals
  python tests/test_background.py      # each background layer, measured (6.1)
  python tests/test_chassis.py         # titlebar / stat tiles / activity / preview (6.3-6.6)
  python tests/test_customise.py       # the 12-column edit mode (6.8)
  python tests/test_replay.py          # instant replay (7a)
  python tests/test_thumbs.py          # thumbnails + Length, with and without ffmpeg (7f)
  python tests/test_forecast.py        # the ribbon model (7b) + forecast maths (7c)
  python tests/test_palette.py         # command palette matching + the no-destructive rule (7e)
  python tests/test_profiles.py        # per-game profiles + the scope guard (7d)
  ```
  Two known flakes, both environmental: `test_toast` asserts against the *active*
  monitor's work area and can fail if the active screen changes mid-run, and
  `test_settings_typing` measures event-loop beats and can dip under load. Both
  pass reliably run on their own.
  ⚠️ Anything async **must** be tested under a real `mainloop()`. Tk refuses a cross-thread
  `root.after()` when driven by `update()`-pumping, and `_ui()` swallows that — so an
  `update()`-pumped test sees worker results never arrive. That has hidden real behaviour twice.
  Beyond the suite, verify against a live OBS instance. Final polish: `CLAUDE-FINALISE-PROMPT.md`.

## Codebase knowledge graph (token-saving)
A graphify graph of this project lives in `graphify-out/` (232 nodes, 441 edges). To answer
"where/how" questions cheaply, prefer:
```
graphify query "your question"
```
over reading files. Refresh after edits with `graphify update .` (local, no API key).
`.graphifyignore` keeps the graph code-only.
```
