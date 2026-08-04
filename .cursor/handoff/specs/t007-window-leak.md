# t007 — Auxiliary windows leak on unexpected exit

`spike/windows.py` creates the toast and mini overlay as always-on-top
frameless windows. `destroy()` exists and is called from `NebulaHost.quit()`,
but that only runs on a **clean** exit. When the process dies any other way —
crash, `taskkill`, a killed probe — the windows are orphaned and stay on screen
forever with no way to close them.

This is not theoretical. It has already happened: seven stray Nebula windows
were left on the desktop in one session, two of them *(Not Responding)*, one
from a process that had been wedged for **30 hours**.

## What to do

Make teardown unconditional. `atexit` alone is not enough — it does not run on
`SIGKILL`/`taskkill`, which is exactly the case that leaks. So combine:

1. **`atexit.register`** on `NebulaWindows` — covers normal and exception exits.
2. **A parent-liveness check inside each auxiliary window.** The toast and
   overlay are separate processes' windows driven over the bridge; give each a
   cheap periodic check (a few seconds is fine) that closes itself when the
   host is gone. Watching the parent PID with `os.kill(pid, 0)` /
   `psutil.pid_exists` is enough — `psutil` is already a dependency.
3. **Reclaim on startup.** At launch, close any pre-existing window titled
   `Nebula Toast` or `Nebula Overlay` that does not belong to this process.
   The single-instance mutex already guarantees only one Nebula runs, so any
   such window is by definition an orphan. `tools/shoot.py` has a working
   `EnumWindows` + `GetWindowThreadProcessId` pattern to copy.

Point 3 is the one that actually rescues a user whose machine already has
orphans — the other two only prevent new ones.

## ⛔ File ownership

**You may edit only** `spike/windows.py`, and you may ADD to
`tests/test_v4_windows.py`.
Do **not** touch `spike/host.py`, `spike/app.py`, or anything under
`spike/web/`. If a host change is genuinely required, say so in your report.

## Do not change

- The single-slot toast: replace in place, one tick chain, 4s drain.
- The overlay never showing while idle.
- Existing checks in `tests/test_v4_windows.py` must still pass.

## Definition of done

The standard gate, plus:
- kill the app with `taskkill /F` while a toast is on screen, then confirm
  `python tools/shoot.py --list` shows **no** orphaned Nebula windows
- start the app with an orphan already present and confirm it is reclaimed
- a test covering the reclaim path headlessly
