# Agent improvement loop â€” worklog

Autonomous improvement session started 2026-08-25 (Anthony away, endless loop requested).
Machine: Alien-PC. Repo: `C:\Users\antho\Downloads\nebula`, branch `main`.

## TL;DR for Anthony
1. **Merged your Strix-laptop save with the desktop WIP** â€” both feature sets
   survive (Save/Load updates + webview_power from laptop; preview stills,
   wake-focus, NAS seed, quiet auto-sync from desktop). Pushed to main.
2. **Fixed 4 real bugs**: UI froze on manual Stop (Steam API call on UI thread);
   `setQuiet()` never existed so play-mode GPU saving never engaged; culled
   clips' time vanished from the Recorded tile; pythonw crash path on second launch.
3. **Made the two aspirational GPU checks real**: asleep now drops backdrop
   tiles outright; snapshot fetch is promise-single-flight.
4. **New: "Restart now" button** â€” completes Save/Load between PCs without a
   manual restart dance.
5. **New: clip cache auto-prune** (50 GB default, Settings > Storage) so
   Tailscale clip opens can't silently fill C:. NAS originals never touched.
6. **New tool: `python tools/run_tests.py`** â€” whole suite under per-file
   watchdogs (three tests used to hang forever, hiding real regressions).
7. **Docs reality pass**: CLAUDE.md module map updated to v4/spike era.
8. Everything green: 50/50 test files, gate clean, ruff clean, toast audit
   48/48, 21/21 modules import, live data healthy.

## Ground rules honoured
- OBS footage is sacred; nothing in this session touches recordings.
- Tests are the gate: every iteration ends with relevant tests green.
- Desktop-only features preserved through the merge: hero preview stills,
  wake-event second-launch focus, NAS legacy seed, quiet auto-sync on launch.

## Done

### 0. Merge laptop save into desktop WIP (29ea2bb)
- Fetched origin via `gh` credential helper (nebula SSH key is actually the
  claude-memory deploy key â€” auth fails for nebula; use HTTPS+gh instead).
- Merged `bcf23e1` (laptop) into `0955df2` (desktop WIP), resolved 29 hunks:
  - Took laptop's Save/Load update architecture (updater rewrite), webview_power,
    fault-isolated snapshot(), connecting-aware polling, focused window watch.
  - Kept desktop's real preview stills (laptop had honest stub), WAKE_EVENT focus,
    NAS seed thread, quiet auto-sync (`sync_source_checkout` kept as back-compat),
    updater worktree `.git`-file support, app.js per-section fail() isolation.
- `tools/install_nebula_shortcut.py`: laptop's `shortcut_args()` (no --dev on shortcut).
- Toast files were already converged between machines; trivial comment diffs.

### 1. GPU + load hardening (63e0066)
- `holdBackdropGpu(hold)` â€” display:none on `.backdrop` while asleep releases the
  composited aurora/wisp/star tiles; `.asleep` CSS only paused animations. This
  makes test_v4_gpu's aspirational "asleep drops backdrop GPU tiles" check real.
- `load()` promise-single-flight (`let loadPromise = null;`) â€” concurrent callers
  share one snapshot fetch; per-section fail() isolation retained.
- Reworded gui.py comments carrying U+2248/U+2264 â†’ test_fidelity ALL PASS.
- test_v4_gpu.py: 32/32. test_fidelity 32/32. test_toast 59/59.

### 2. Pushed merged state to GitHub main
- main = cursor/wip fast-forward; pushed via HTTPS+gh helper (63e0066).

### 3. Fixed the three hanging tests + two real bugs (cd4fe17)
- test_games_pane / test_step7 hung on `_ask_display_name` modal (wait_window):
  promote flow grew a display-name dialog; tests only stubbed messagebox.
  Stubbed `app._ask_display_name` in both tests â†’ PASS.
- REAL BUG via faulthandler stack: note_manual_stop ran on the Tk thread and
  could lazily trigger refresh_steam_index â†’ synchronous Steam Store request
  on the UI thread (froze Nebula on Stop). Added Classifier.peek() (cache-only)
  + _find_new_game_target(peek_only=True) for UI-thread callers.
- REAL BUG 2: session_log.today() excluded culled clip durations from Recorded;
  spec (test_chassis, Aug-01) says time counts kept+culled, bytes kept-only.
- Full per-test sweep done: every tests/test_*.py now PASSES or completes.

### 4. setQuiet() entry point (f47acbb) + hygiene
- REAL BUG: host pushed `setAwake(); setQuiet()` but app.js never defined
  setQuiet on EITHER machine â†’ evaluate_js threw every transition, .quiet
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
- Audited offload delete path for the sacred-footage rule: checksum verify â†’
  atomic rename â†’ index-before-delete â†’ local remove only in move mode.
  Correct as shipped; no changes needed.
- Verified overlay/toast pushed-JS surfaces (setAsleep driven via
  _set_renderer_sleep; overlay has no JS push). No missing functions left.
- node tests/test_v4_drag.js passes (25 checks).

### 7. fsprobe negative memo + docs reality pass (8fe2ee0, 6c63b7e, 14b12bc)
- fsprobe.isdir_within leaked one OS-stuck thread per call on dead drives;
  polling callers would stack ~dozens. Negative verdicts now memoised 10s.
- CLAUDE.md module map updated to v4/spike reality (was Tk-era): added
  spike/app+host+windows+webview_power, updater Save/Load model,
  clip_catalog prune invariant, run_tests watchdog note.
- pythonw second-launch prints guarded (AttributeError on missing stdout).
- Audited laptop's monitor.py elevated-OBS hardening: clean, tested.

### 8. Research round: pywebview pitfalls
- pywebview #1439 (evaluate_js + persistent threads hang at close): Nebula's
  pushes are daemon-threaded + try/except + marshalled via _off_gui, so a
  stuck push cannot hold the process at exit. Acceptable.
- `window.run_js()` (fire-and-forget, no result marshalling) could further
  shrink the deadlock surface for setAwake/setQuiet-style pushes - future
  hardening option, not changed now (behavioural churn without a failing case).
- pywebview #1699 (blocking event handlers): snapshot() runs per-call on
  bridge worker threads by design; the >750ms slow-log covers regressions.
- Machine audit: NebulaLaunchOBS task Ready; Start Menu shortcut argv exactly
  matches shortcut_args(show=True, dev=False); installer idempotent.

### 9. Coverage sweep complete (190acdd)
- MultiGameSync fan-in/out spec-tested (was the only untested coordinator).
- Reviewed laptop's monitor.py elevated-OBS hardening, teracopy.py,
  gamesync dual-stack, host start_poll chain, renderHero connecting state,
  applyPreviewStill degradation paths, toast event mapping - all sound.
- Live data audit (read-only): config/index/sessions all healthy.
- Machine audit passed: NebulaLaunchOBS Ready, shortcut argv canonical.
- Handoff inbox empty; gate verdict green.

## Test status at last commit
ALL tests pass (50 files incl. new classifier_peek + fsprobe specs),
gate clean, ruff clean, token lint clean, toast audit 48/48.
ALL tests/test_*.py pass individually with PYTHONUTF8=1 (34 files).

## Known notes for next iterations
- Full-suite run times out >15 min sequentially â€” some test hangs; find which and
  fix or mark slow (candidates: anything touching network/OBS/webview).
- `.cursor/TOAST-GALLERY-RECOVERED.md` + `sort_recovered_state.json` left untracked.
- Push to GitHub main still pending (needs gh credential helper one-liner, not SSH).
- host.py watch loop has dead vars `started`/`seen_on_screen` from old grace logic.
- `_hero_preview_seq` in spike/app.py is now unused (host.preview_still_seq read inline).

## 2026-08-26 session (Ox Alpha Free, continuation)

1. **CI is live and green** - windows-latest, Python 3.12, ruff pinned 0.16.4,
   ffmpeg via choco, 	ools/run_tests.py --timeout 150. First fully passing
   run: 32958487145 (53/53 files).
2. **Remote switched SSH -> HTTPS + gh credential helper**: the
   github_nebula ed25519 key is rejected by GitHub (offered, refused) and
   the current token lacks admin:public_key to re-add it. Remote URL changed;
   key investigation queued for Anthony.
3. **Monitor races fixed (deep-read item)**:
   - All OBS transitions now serialise on _obs_lock (RLock). The toast
     "Record" button, the transport bar and a poll tick could previously enter
     start/stop concurrently -> double-start, then _recording_target=None
     while OBS records.
   - 
ote_manual_stop() bumps _stop_epoch; an auto-apply already past its
     debounce aborts honestly at its point of no return instead of overriding
     the user's Stop.
   - ccept_record_prompt never blocks the UI thread (0.35s acquire timeout,
     busy = honest refusal, prompt stays pending).
   - Tests: tests/test_manual_stop_race.py (11 checks).
4. **Startup import time 490ms -> 282ms (-42%)**: equests (urllib3 chain)
   deferred into steam_scanner.classify_appid; only call site that needs it.
5. **Offload retry loop covered**: tests/test_offload_backoff.py drives the
   real worker through NAS-down -> backoff -> recovery -> source-gone
   (10 checks), patching isdir_within/diagnose because fsprobe's negative
   memo would lie about timing with real dirs.
6. **clip_catalog**: resume on an already-finished download returns ok=True
   (was an error toast for pressing Resume one second late; also a CI flake).
7. **config**: DEFAULTS entry for clip_cache_max_gb (Settings rendered blank
   on fresh installs) + permanent spec test: every Field key must be backed
   by DEFAULTS or INTERNAL_KEYS.
8. **run_tests.py diagnostics**: failures now surface FAIL/error lines AND
   stderr tail - a hard crash prints nothing to stdout, and the old 3-line
   tail hid everything.

## 2026-08-26 session 2 (Ox Alpha Free, continued)

1. **Prior-art research** (Smart-Replay-Mover, ClipStudio, obs-twitch-mcp,
   SAN fork) -> vault ARTIFACTS/OBS-PRIOR-ART.md, 10 ranked targets.
   Trophy clips (T1) researched and REJECTED: realtime Steam unlock
   detection needs Steamworks injection / Web-API keys / fragile cache
   parsing - none fit. Replay re-arm (T2) audited: immune to SRM #22 by
   design; refused-disarm honesty fix shipped instead + test.
2. **NAS month folders**: 
as_offload_date_folders puts new copies under
   <Game>/YYYY-MM/ from the clip's own mtime; dedup and worker share one
   destination computation so the scan can't re-queue synced clips
   (tests/test_offload_dates.py).
3. **Scene-name hint**: an unclassifiable (anti-cheat) foreground exe whose
   OBS program scene exactly names a classified game now records under that
   game. Cached RPC, generic scenes can never fire, UI thread never asks
   OBS (tests/test_scene_hint.py). Classifier gains display_lookup().
4. **UDP replay trigger**: eplay_udp_port (0=off) binds loopback only;
   any datagram saves the buffer with a flood gap. For Stream Deck /
   home automation / the future macropad (spike/udp_trigger.py +
   tests/test_udp_trigger.py). Drift detector immediately caught the
   missing CLAUDE.md map row - added.
5. **CI timing hardening**: pause/resume-on-ready made idempotent in
   clip_catalog (finish-before-pause races on loaded runners);
   test_offload_backoff now runs the real backoff at 2s so the rate-limit
   assertion spans an actual second attempt.

## 2026-08-26 session 2 addendum

- **SSH verify path pinned** (tests/test_offload_ssh.py, 17 checks): injection
  guards, output parsing, BatchMode/quoting contract, dead-ssh falls back to
  SMB hashing (logged, never skipped), wrong-digest refuses the move.
- **Replay paused-save single-flight**: hotkey + UDP trigger double-fire can
  no longer race resume/pause; a request arriving mid-cycle is an ordinary
  save on the resumed encoder. test_replay.py now 56 checks.
- **Review-queue audit**: lifecycle is closed in both GUIs (every pop path
  reaches finish_review); unanswered items persist visibly by design.
- **Cleanup**: Classifier.pop_pending_item(key) replaces spike/app.py's
  direct reach into _lock/_pending_manual.
- **Measurements**: poll drift <=16 ms under 12-core load; CI suite ~140 s,
  slowest file 14 s; tokens.css regen byte-identical. Vault ARTIFACTS/
  MEASUREMENTS.md + DECISIONS.md hold the details.

### Session 2 final batch
- test_customise: Esc-revert now waits on state (loaded CI expired mid-revert).
- test_clip_catalog: cancel-vs-rename race accepted when the winner is a
  full-size cache; half-written files still fail hard.
- test_offload_backoff comment updated for Strix's _root_is_up recovery.
- Local full suite: 63/64 (test_teracopy transient - passes standalone and in
  every CI run; suspected TeraCopy background-process interference).
