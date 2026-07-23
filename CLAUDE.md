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
| `obsauto/gui.py` | `AppWindow` | CustomTkinter UI: "Aurora" shell (nav rail + hero dashboard), glass/rounded chrome |
| `obsauto/audio_detect.py` | `AudioKeepAlive` | Detect whether a watched app (e.g. Discord) is producing audio |
| `obsauto/session_detect.py` | `moonlight_session_active()` | Detect a live Moonlight streaming session |
| `obsauto/config.py` | `load_config()`, `save_config()` | Config persistence |
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
Activity, Settings (read-only). **Macropad is deliberately empty** — there's no binding layer,
and a mock keypad that does nothing would be a lie.

⚠️ Don't put fabricated numbers in the UI — the Games badge reads the classifier
(`_game_count()`) and returns `None` (no badge) rather than inventing a count.

## Config (`config.json`)
- OBS: `obs_host` localhost, `obs_port` 4455, `obs_password` empty (obs-websocket v5)
- `recording_root`: `D:/OBS Recordings` · `sync_folder`: default **empty** (local only);
  set to `OneDrive/ObsAutoFolder` on this user's machines
- `idle_timeout_seconds` **4** · `min_clip_seconds` 10 · `poll_interval_seconds` 1
  (defaults per `obsauto/config.py`'s `DEFAULTS` — the live `config.json` may differ)

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
- **Tests:** `python tests/test_async_connect.py` (needs a desktop session; creates a hidden
  Tk window, no OBS required). Covers the connect path, deferred-callback error handling and
  reconnect state. Beyond that, verify changes by running the app against a live OBS instance.

## Codebase knowledge graph (token-saving)
A graphify graph of this project lives in `graphify-out/` (232 nodes, 441 edges). To answer
"where/how" questions cheaply, prefer:
```
graphify query "your question"
```
over reading files. Refresh after edits with `graphify update .` (local, no API key).
`.graphifyignore` keeps the graph code-only.
```
