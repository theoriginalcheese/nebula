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
pyinstaller obs_auto_game_folder.spec   # -> dist/obs_auto_game_folder.exe (windowed, UPX-compressed, icon black_obs.ico)
```
⚠️ **Gotcha:** the `.spec` still targets the legacy single-file `obs_auto_game_folder.py`,
but real development is in `main.py` + `obsauto/`. Confirm which entry point is current
before trusting a build — the spec may need updating to `main.py`.

## Architecture (module map)
| File | Key symbols | Role |
|------|-------------|------|
| `main.py` | `main()`, `_apply_sync_folder()` | Wiring: logging → config → Classifier → AppWindow + tray |
| `obsauto/monitor.py` | `Monitor` | Core loop: foreground/idle detection, ensure/launch OBS, start/stop + retarget recording |
| `obsauto/obs_client.py` | `OBSClient`, `OBSError` | Minimal obs-websocket **v5** client |
| `obsauto/classifier.py` | `Classifier` | Game vs non-game classification (Steam-aware hybrid) |
| `obsauto/steam_scanner.py` | `build_steam_game_index()` | Scan Steam libraries, parse VDF, classify AppIDs |
| `obsauto/gui.py` | `AppWindow`, `Pill` | CustomTkinter UI, status card, glass/rounded chrome |
| `obsauto/audio_detect.py` | `AudioKeepAlive` | Detect whether a watched app (e.g. Discord) is producing audio |
| `obsauto/session_detect.py` | `moonlight_session_active()` | Detect a live Moonlight streaming session |
| `obsauto/config.py` | `load_config()`, `save_config()` | Config persistence |
| `obsauto/app_log.py` | `setup_logging()`, `log_to_file()` | File logging (works under silent `pythonw`) |
| `obsauto/tray_app.py`, `theme_art.py`, `icon_art.py` | — | Tray icon + generated icon/theme art |

Most-connected hubs (start here when orienting): `AppWindow`, `OBSClient`, `Monitor`, `Classifier`.

## Config (`config.json`)
- OBS: `obs_host` localhost, `obs_port` 4455, `obs_password` empty (obs-websocket v5)
- `recording_root`: `D:/OBS Recordings` · `sync_folder`: `OneDrive/ObsAutoFolder`
- `idle_timeout_seconds` 60 · `min_clip_seconds` 10 · `poll_interval_seconds` 1

## Conventions & gotchas
- **Cross-machine sync:** `_apply_sync_folder()` repoints `games.json` and
  `steam_appid_cache.json` into `~/OneDrive/ObsAutoFolder` so classifications made on the
  laptop show up on the desktop. A *relative* `sync_folder` resolves against each machine's
  own `~`, so the same `config.json` works despite different Windows usernames.
- **Silent runs:** intended to run as `pythonw` (no console), so all diagnostics go through
  `app_log` to a file — don't rely on `print()`.
- **No test suite** currently. Verify changes by running the app against a live OBS instance.

## Codebase knowledge graph (token-saving)
A graphify graph of this project lives in `graphify-out/` (232 nodes, 441 edges). To answer
"where/how" questions cheaply, prefer:
```
graphify query "your question"
```
over reading files. Refresh after edits with `graphify update .` (local, no API key).
`.graphifyignore` keeps the graph code-only.
```
