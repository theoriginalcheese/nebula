# step2
status: done

## Changed
- `spike/host.py` — OBSClient + Monitor via `attach_backend()`; async connect; single poll chain; transport; real `tray_status()` / `hero_state()`; toggle hotkey bound
- `spike/app.py` — wire backend on boot; `_hero()` reads host readouts/meta; `hero_action()` API; settings OBS footer from real handshake
- `spike/web/app.js` — hero button transport; 1s poll while recording/paused; honest empty readouts (no placeholder dashes)
- `tests/test_v4_monitor.py` — 22 checks (tray states, transport re-read, async connect, bitrate honesty, hotkey bind)
- `shots/step2-disconnected.png` — dashboard disconnected hero (OBS not running / WS refused during capture)

## Deliberate deviations
- Toast on monitor notify events is step 8 — events are logged only for now.
- Disk-floor refusal before manual start (`can_start_recording`) not ported yet; transport otherwise matches v3 re-read semantics.
- Hero design token key remains `watching` in `HERO_STATES`; host exposes `idle`, mapped at the API boundary (same as v3 tray vs hero naming).

## Gate
```
python -m ruff check .
All checks passed!

python tools/lint_tokens.py
token lint: clean (1 stylesheet)

python tests/test_v4_tray.py
ALL PASS (31 checks)

python tests/test_design_v3.py
ALL PASS (48 checks)

python tests/test_v4_monitor.py
ALL PASS (22 checks)

python tools/shoot.py --out shots/step2-disconnected.png
Nebula  1898x1156  via PrintWindow  -> shots/step2-disconnected.png
```

Screenshot: `shots/step2-disconnected.png` — disconnected hero verified visually. OBS WebSocket was not accepting connections during capture (activity log shows launch + retry); recording / paused / idle states were not observable live and were covered by `test_v4_monitor.py` fakes instead.

## Notes for review
- `hero_state()` is the single enum; `tray_status()` and `Api._hero()` both derive from it.
- Connect + transport run on workers; poll uses one `threading.Timer` chain (`_poll_now` cancels before reschedule).
- `tests/test_v4_tray.py` unchanged — monitor-less host still defers all three hotkeys; host with `attach_backend()` binds toggle only.
