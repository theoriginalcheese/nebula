# v4 step 2 — Monitor + OBS wiring

Make the hero card's four states real. Today `spike/host.py` reports
`disconnected` unconditionally because there is no `Monitor` and no
`OBSClient`; this step attaches them.

Read `V4-GUIDE.md` step 2 and `spike/host.py` first. `spike/host.py` is the
adapter that already drives the tray and hotkeys — extend it. Do not create a
parallel one.

## What to build

1. **Attach `OBSClient` and `Monitor` to `NebulaHost`.**
   `obsauto/obs_client.py` and `obsauto/monitor.py` are unchanged and must stay
   that way. `NebulaHost` already exposes `call_soon()`, `_log()` and
   `tray_status()` — wire the monitor's `on_log` / `on_state` / `on_notify`
   callbacks through those.

2. **`NebulaHost.tray_status()` must return the real state.**
   It currently hardcodes `disconnected` when `self.monitor is None`. Replace
   the placeholder branch with the actual derivation, same as
   `AppWindow.tray_status()` in `obsauto/gui.py` (read it — do not invent a
   different state machine):

       not connected            -> "disconnected"
       recording and paused     -> "paused"
       recording                -> "recording"
       otherwise                -> "idle"

   `monitoring` must reflect whether the monitor is actually running.
   When this returns something other than `disconnected`, the tray's
   Pause / Stop / Monitoring items unhide automatically — that logic already
   exists in `obsauto/tray_app.py`, do not touch it.

3. **The hero's four states, from one enum.**
   `spike/app.py` already ships `dv.HERO_STATES` to the front end. The window
   must render `disconnected | idle | recording | paused` from a single source —
   the host — exactly as `_set_hero_state()` does in v3. One place expresses the
   state; nothing else may branch on it.

4. **Transport: pause / resume / stop.**
   Replace the `_toggle_record` / `_toggle_pause` stubs in `spike/host.py`.

5. **Bind the toggle hotkey.**
   `host.start_hotkeys()` currently calls `self.hotkeys.defer("toggle", ...)`.
   Change it to a real `bind()` now that monitoring exists. Leave `replay` and
   `palette` deferred — they are step 7. Pass `scancode=` from
   `config["toggle_hotkey_scancode"]`.

## The five ways this step goes wrong

These are all documented in CLAUDE.md and all shipped as real bugs once.

1. **Never call `obs.connect()` on the UI thread.** It blocks for up to its 5s
   socket timeout, and at startup that is the *normal* case — OBS has just been
   launched and is still booting. v3 froze the whole window for seconds doing
   this, then again on every 10s retry. Connect on a worker and marshal the
   result back with `call_soon()`.

2. **Every transport command must re-read `GetRecordStatus` first, on a
   worker.** v3 branched on cached `_is_recording` / `_is_paused` flags
   refreshed by a 1s poll, so pressing Stop then Pause inside that window sent
   `PauseRecord` to a recording that had already ended. Read the truth, then act.

3. **`except X as e:` unbinds `e` when the block exits.** Anything capturing
   `e` in a closure that runs later dies with
   `NameError: cannot access free variable 'e'`. Bind to a plain local
   (`error = exc`) before building the closure. This hit the OBS connect
   failure path specifically.

4. **One poll chain only.** v3's `_poll_now()` had to cancel before
   rescheduling; two self-perpetuating timers drained the toast at double rate.
   Whatever polls `GetRecordStatus` must not be able to start a second chain.

5. **Bitrate is derived, never drawn in.** Compute it from the byte and
   duration delta between two successive `GetRecordStatus` polls, and render
   **nothing** until there are two samples at least 500ms apart. Do not show a
   zero, a dash-that-looks-like-data, or a guess.

## Honesty rules for this step

- No fabricated elapsed time, file size, bitrate, scene name or handshake ms.
  Every one of those comes from OBS or is not rendered.
- If OBS is unreachable, the disconnected hero state is correct and complete —
  it is not a degraded version of the connected one.
- The `Mark clip` button stays absent. There is still no backend for it.

## Tests

Add `tests/test_v4_monitor.py`, modelled on `tests/test_v4_tray.py` (read it
first — same hand-rolled PASS/FAIL harness, no pytest, no real OBS).

Cover at minimum:
- `tray_status()` returns each of the four states given a fake monitor
- a transport command re-reads status before acting, and refuses when the
  re-read disagrees with the cached flag
- connect never runs on the calling thread
- the deferred-closure pattern from trap 3 does not raise
- bitrate returns nothing with fewer than two samples, or samples <500ms apart
- the toggle hotkey is bound (not deferred) once a monitor exists

`tests/test_v4_tray.py` must still pass unchanged — 31 checks. If it fails you
have changed step 1's contract, which is a bug in this step, not in that test.

## Definition of done for this task specifically

Everything in the standard gate, plus:

    python tests/test_v4_monitor.py

and a screenshot of the Dashboard showing the disconnected hero — since OBS is
almost certainly not running while you work, that is the state you can actually
verify. Say so in your report rather than claiming you saw all four.
