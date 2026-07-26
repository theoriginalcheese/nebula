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
| `obsauto/settings_spec.py` | `FIELDS`, `parse()`, `render()` | Declares what the Settings view edits + pure validation (no Tk, so it's unit-testable) |
| `obsauto/paths.py` | `APP_DIR`, `RESOURCE_DIR` | Dev vs. frozen-onefile path resolution |
| `obsauto/app_log.py` | `setup_logging()`, `log_to_file()` | File logging (works under silent `pythonw`) |
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
Activity, Settings (edits `config.json` — see below). **Macropad is deliberately empty** —
there's no binding layer, and a mock keypad that does nothing would be a lie.

⚠️ Don't put fabricated numbers in the UI — the Games badge reads the classifier
(`_game_count()`) and returns `None` (no badge) rather than inventing a count.

### Settings view (editable, applies live)
Rows are generated from `settings_spec.FIELDS`, not hand-positioned — add a setting there
and the page grows a row. `parse()`/`render()` are pure inverses (a test asserts every
`DEFAULTS` value round-trips, so opening the page and pressing Save is a guaranteed no-op).

- **Validation is all-or-nothing on Save.** One bad field means nothing is written, so you
  can never half-apply a batch. `_settings_reload()` re-reads config on every visit to the
  page, which is what keeps it honest about the dashboard's idle slider and hand-edits —
  the flip side being that unsaved typing is dropped when you navigate away. That's the
  right way round: the page must never show a value that isn't in effect.
- **`_apply_settings(changed)` is the live-apply seam.** Most keys need nothing (the monitor
  re-reads `self.config` every tick, the offloader per item). It handles the objects that
  snapshot config — `OBSClient` host/port/password, `AudioKeepAlive.set_processes()`,
  `GameSync.configure()`, `Offloader.refresh()`, the global hotkey — plus the chrome that
  displays a config value (sidebar endpoint, keycap, folder chip, Sync tile).
- **Only `sync_folder` needs a restart** (`Field(restart=True)`), because `_apply_sync_folder()`
  repoints the classifier's data file before `Classifier()` is constructed.
- **A path that doesn't exist is a warning, never an error.** An unmounted NAS or a drive on
  the other machine must be configurable ahead of time — the offloader is explicitly built
  to queue and retry, so refusing the value would break the documented setup order.
- **Never log a secret's value.** The save line lists changed *key names* only;
  `github_token`/`obs_password` go through it and the activity log is on screen and on disk.
- ⚠️ **Repaint budget.** A text field costs one window composite per keystroke and there is
  no way around that — so spend exactly that and no more. Nothing here validates, restyles
  or updates the status line as you type. What made the old animation fatal was repainting
  *without* input; a form only costs while it's being used. Don't add live validation.

## Config (`config.json`)
- OBS: `obs_host` localhost, `obs_port` 4455, `obs_password` empty (obs-websocket v5)
- `recording_root`: `D:/OBS Recordings` · `sync_folder`: default **empty** (local only);
  set to `OneDrive/ObsAutoFolder` on this user's machines
- `idle_timeout_seconds` **4** · `min_clip_seconds` 10 · `poll_interval_seconds` 1
  (defaults per `obsauto/config.py`'s `DEFAULTS` — the live `config.json` may differ)

## Sync & offload invariants (don't weaken)
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
second, and only while recording. The tray icon still animates — separate surface, never touches
this window. `tests/test_frame_pacing.py` fails if a per-frame timer comes back.

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
  Corollary: a stop-then-start (repointing OBS from Settings) can't just call `autostart()`,
  which no-ops while `_connecting` — the in-flight attempt then resolves against the
  `_abort_connect` the stop just set and neither connects nor retries, leaving monitoring off
  for good. `_restart_monitoring()` waits (bounded) for the flight to land first.
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
  python tests/test_settings.py        # Settings round-trips, validates, and applies live
  ```
  ⚠️ Anything async **must** be tested under a real `mainloop()`. Tk refuses a cross-thread
  `root.after()` when driven by `update()`-pumping, and `_ui()` swallows that — so an
  `update()`-pumped test sees worker results never arrive. That has hidden real behaviour twice.
  Beyond the suite, verify against a live OBS instance.

## Codebase knowledge graph (token-saving)
A graphify graph of this project lives in `graphify-out/` (232 nodes, 441 edges). To answer
"where/how" questions cheaply, prefer:
```
graphify query "your question"
```
over reading files. Refresh after edits with `graphify update .` (local, no API key).
`.graphifyignore` keeps the graph code-only.
```
