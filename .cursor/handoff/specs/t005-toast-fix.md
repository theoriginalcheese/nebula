# t005 — The toast window never appears. Find out why and fix it.

`spike/windows.py` is wired into `spike/host.py` and the gate is green, but the
toast **never registers a window with the shell**. It does not raise — it fails
silently, which is worse.

## Reproduce

```python
# probe: stub host, parent window, then toast_replace
nw = NebulaWindows(StubHost(), {})
nw.toast_replace("clip_saved", "Honkai Star rail", "1.2 GB")
```
Then `python tools/shoot.py --list` — no window titled "Nebula Toast" appears.
A probe that tried to print `toast._window` / `_ready.is_set()` / `_alive` died
during teardown with:
`ERROR:ui\gfx\win\window_impl.cc:172 Failed to unregister class Chrome_WidgetWin_0`

## Suspects, in order

1. `webview.create_window()` called from a **non-UI thread** after
   `webview.start()`. `_create()` runs from whatever thread called
   `toast_replace`; `NebulaHost.call_soon` marshals onto a worker thread, not
   the UI thread. pywebview may require window creation on its own loop.
2. `_on_ready` never fires, so `_push()` — which calls `self._window.show()` —
   never runs. `hidden=False` should make that moot, but verify it.
3. The second window is created but positioned off every monitor.
   `_toast_workarea()` returns the *active* monitor's work area; check the
   coordinates are real.

## ⛔ File ownership

**You may edit only:** `spike/windows.py`, `spike/web/toast.*`,
`spike/web/overlay.*`, and you may ADD `tests/test_v4_windows.py`.
**Do NOT touch** `spike/app.py`, `spike/host.py`, `spike/web/app.*`,
`spike/web/index.html` — another agent is in those right now.

If the fix genuinely needs a host change, say so in your report; do not make it.

## Contract that still holds (frame 2i)

- **One slot for the whole process life.** Replace in place, never stack, never
  queue. Build the replace path before the visuals.
- **Exactly one self-rescheduling tick chain** — a second one drains the life at
  double rate. This was a real v3 bug.
- 4s drain, frozen while hovered. Rise 16px/320ms in, fade 200ms out.
- Positioned against the **active** monitor's work area.

## Definition of done

The standard gate, plus:
- `python tools/shoot.py --list` shows a window titled **Nebula Toast** after a
  `toast_replace` call
- a screenshot of the toast you **actually open and describe**
- a second `toast_replace` while the first is on screen replaces it in place —
  prove there is still exactly one window
- `tests/test_v4_windows.py` covering the replace-in-place rule headlessly
