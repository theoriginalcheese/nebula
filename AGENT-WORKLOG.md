# Agent improvement loop — worklog

Autonomous improvement session started 2026-08-25 (Anthony away, endless loop requested).
Machine: Alien-PC. Repo: `C:\Users\antho\Downloads\nebula`, branch `cursor/wip`.

## Ground rules honoured
- OBS footage is sacred; nothing in this session touches recordings.
- Tests are the gate: every iteration ends with relevant tests green.
- Desktop-only features preserved through the merge: hero preview stills,
  wake-event second-launch focus, NAS legacy seed, quiet auto-sync on launch.

## Done

### 0. Merge laptop save into desktop WIP (29ea2bb)
- Fetched origin via `gh` credential helper (nebula SSH key is actually the
  claude-memory deploy key — auth fails for nebula; use HTTPS+gh instead).
- Merged `bcf23e1` (laptop) into `0955df2` (desktop WIP), resolved 29 hunks:
  - Took laptop's Save/Load update architecture (updater rewrite), webview_power,
    fault-isolated snapshot(), connecting-aware polling, focused window watch.
  - Kept desktop's real preview stills (laptop had honest stub), WAKE_EVENT focus,
    NAS seed thread, quiet auto-sync (`sync_source_checkout` kept as back-compat),
    updater worktree `.git`-file support, app.js per-section fail() isolation.
- `tools/install_nebula_shortcut.py`: laptop's `shortcut_args()` (no --dev on shortcut).
- Toast files were already converged between machines; trivial comment diffs.

### 1. GPU + load hardening (63e0066)
- `holdBackdropGpu(hold)` — display:none on `.backdrop` while asleep releases the
  composited aurora/wisp/star tiles; `.asleep` CSS only paused animations. This
  makes test_v4_gpu's aspirational "asleep drops backdrop GPU tiles" check real.
- `load()` promise-single-flight (`let loadPromise = null;`) — concurrent callers
  share one snapshot fetch; per-section fail() isolation retained.
- Reworded gui.py comments carrying U+2248/U+2264 → test_fidelity ALL PASS.
- test_v4_gpu.py: 32/32. test_fidelity 32/32. test_toast 59/59.

### 2. Pushed merged state to GitHub main
- main = cursor/wip fast-forward; pushed via HTTPS+gh helper (63e0066).

### 3. Fixed the three hanging tests + two real bugs (cd4fe17)
- test_games_pane / test_step7 hung on `_ask_display_name` modal (wait_window):
  promote flow grew a display-name dialog; tests only stubbed messagebox.
  Stubbed `app._ask_display_name` in both tests → PASS.
- REAL BUG via faulthandler stack: note_manual_stop ran on the Tk thread and
  could lazily trigger refresh_steam_index → synchronous Steam Store request
  on the UI thread (froze Nebula on Stop). Added Classifier.peek() (cache-only)
  + _find_new_game_target(peek_only=True) for UI-thread callers.
- REAL BUG 2: session_log.today() excluded culled clip durations from Recorded;
  spec (test_chassis, Aug-01) says time counts kept+culled, bytes kept-only.
- Full per-test sweep done: every tests/test_*.py now PASSES or completes.

### 4. setQuiet() entry point (f47acbb) + hygiene
- REAL BUG: host pushed `setAwake(); setQuiet()` but app.js never defined
  setQuiet on EITHER machine → evaluate_js threw every transition, .quiet
  play-mode CSS could never engage. Added window.setQuiet.
- .gitignore: recovery-session scratch (sort checkpoint + gallery note).
- Ruff clean; dead vars/_hero_preview_seq removed (5d7c64a).
- Verified sleep_aux/windows.py wiring; README/V4-GUIDE already current.

### 5. Restart now completes the Save/Load loop (d8c9eea, 21d88f4)
- updater.relaunch_source(): waiter in %TEMP% (never beside the repo - stray
  files would dirty the tree and ship on next Save), waits for pid drop,
  starts pythonw spike/app.py --show (Start Menu argv).
- Api.restart_source_update() quits for real via host.quit() after 0.8s
  (api.close() only hides to tray - old process would hold the mutex).
- Footer button Restart now + blurb/README copy updated.
- test_updater.py grew 7 relaunch checks (frozen refusal, non-checkout,
  TEMP-not-repo waiter location, argv shape, --show parity). 33/33.
- Verified: pushed-JS surface fully coherent (setAwake/setQuiet/openPalette/
  toastReplace/toastForceVisible), api.* calls all bound (toast/overlay have
  own Api classes), requirements.txt has no drift, gate selftest + run clean,
  toast audit 48/48 across 4 scales x 4 work-area shapes.
- WebView2 research: MemoryUsageTargetLevel API exists for script-must-run
  inactive webviews, but MS advises NOT mixing it with TrySuspend - Nebula's
  pure-TrySuspend design stays correct. No disable-gpu flags anywhere.

### 6. Clip cache auto-prune + Settings exposure (c4b773b, c65b3ef)
- REAL GAP: clip_cache was evict-manual only; Tailscale clip opens could eat
  tens of GB of C: silently. New `_prune_cache()` runs after each completed
  download: oldest-mtime index-known files first, active downloads skipped,
  just-fetched clip kept, orphans left for evict_all. Cap = config key
  `clip_cache_max_gb` (default 50 GB, 0 disables), exposed in Settings >
  Storage + README table.
- Audited offload delete path for the sacred-footage rule: checksum verify →
  atomic rename → index-before-delete → local remove only in move mode.
  Correct as shipped; no changes needed.
- Verified overlay/toast pushed-JS surfaces (setAsleep driven via
  _set_renderer_sleep; overlay has no JS push). No missing functions left.
- node tests/test_v4_drag.js passes (25 checks).

## Test status at last commit
ALL tests/test_*.py pass individually with PYTHONUTF8=1 (34 files).

## Known notes for next iterations
- Full-suite run times out >15 min sequentially — some test hangs; find which and
  fix or mark slow (candidates: anything touching network/OBS/webview).
- `.cursor/TOAST-GALLERY-RECOVERED.md` + `sort_recovered_state.json` left untracked.
- Push to GitHub main still pending (needs gh credential helper one-liner, not SSH).
- host.py watch loop has dead vars `started`/`seen_on_screen` from old grace logic.
- `_hero_preview_seq` in spike/app.py is now unused (host.preview_still_seq read inline).
