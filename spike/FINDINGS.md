# v4 spike — what the measurements say

**Verdict: the webview is cheaper than what Nebula ships today, and it runs every
animation the spec asked for.** Both halves of that were expected to go the other way.

Run it yourself:

```
python spike/app.py
```

## The numbers

All figures from `tools/bench.py`, 20-second samples, whole process tree, this laptop.
**Private (USS)** is the comparable memory figure — summed RSS counts Chromium's shared
pages once per process and would have inflated the webview by ~320 MB against
single-process Tk.

| | processes | CPU (median) | private (USS) |
|---|---|---|---|
| `gui.py` — shipping v3, backdrop **static** | 4 | 0.00 % | **513 MB** |
| `spike/app.py` — visible, backdrop **animating** | 7 | 0.00 % | **435 MB** |
| `spike/app.py` — minimised | 7 | 0.00 % | **288 MB** |
| `spike/app.py` — hidden, renderer **suspended** (step 11) | 7 | 0.00 % | **69 MB** |

### `evaluate_js` deadlocks if you call it from the GUI thread

One defect, two symptoms that looked unrelated: **the toast freezing the whole
app on its first event**, and **the mini overlay opening permanently blank**.

pywebview's Edge backend:

```python
self.webview.Invoke(... ExecuteScriptAsync(script).ContinueWith(
    callback, self.syncContextTaskScheduler))
semaphore.acquire()
```

The continuation is scheduled on the synchronisation context — the GUI thread —
and then the *caller* blocks on the semaphore. Call it from the GUI thread and
that thread waits forever on work only it can run.

Both paths did exactly that, because `_run_on_gui` had put them there:

| path | how it reached `evaluate_js` on the GUI thread |
|---|---|
| toast | `_replace_gui` → `_push` |
| overlay | `_show_gui` → `host.hide()` → `host._sleep(False)` |

The overlay case is the nastier one, because the thread it wedges is the thread
the *just-created* WebView2 needs in order to initialise. So the page never
loads, its script never runs, and the window renders nothing — while Windows
quietly substitutes a `class='Ghost'` stand-in over the top.

`_off_gui()` is the inverse of `_run_on_gui` and the fix. `evaluate_js` marshals
to the GUI thread by itself, so a worker thread is not merely safe, it is the
only correct caller.

**How it was found, because the shape recurs.** Three probes, each killing one
explanation rather than confirming a hunch:

1. `document.title` stage markers in `boot()` — never advanced. *Ambiguous:*
   could be "JS never ran" or "pywebview does not mirror title changes".
2. A magenta background set at **module scope**, needing neither the bridge nor
   the title. Never appeared → **`overlay.js` never executed at all**, so the
   fault was not in `boot()`.
3. Enumerating the windows with PID and class → `class='Ghost'`, a *different*
   PID, same rect. That is the OS stating the window is hung. There was never a
   duplicate overlay; the "second window" was Windows' not-responding stand-in.

The Ghost is also the regression test: it appears ~6s after the overlay opens
and, once the deadlock is gone, **disappears again** by ~21s as the window
resumes pumping. A Ghost that never withdraws means this is back.

⚠️ Capturing any of this needs `SM_XVIRTUALSCREEN` / `SM_YVIRTUALSCREEN`. PIL
crops relative to the virtual-screen origin, which is negative when a monitor
sits left of the primary (here: `-1920`). `GetWindowRect` is in the same space,
so an unshifted bbox samples a completely different part of the desktop — which
is what made several earlier captures look "blank" when they were simply
pointed somewhere else.

### pywebview's default `min_size` silently inflates small windows

`create_window` defaults to **`min_size=(200, 100)`**, and the winforms backend
applies it as `MinimumSize = min_size * scale`. Neither auxiliary window is
100px tall, so both were quietly clamped:

| window | asked | got | 
|---|---|---|
| toast (2i) | 336×88 | 336×**100** |
| mini overlay (2k) | 296×54 | 296×**100** |

On a `frameless` window that surplus is not visible chrome — it is an opaque,
always-on-top band hanging below the card, nearly as tall again as the overlay
itself. Pass `min_size` explicitly whenever a window is smaller than 200×100.

⚠️ The clamp also distorted the *width* reading and therefore the DPI scale
derived from it: the overlay measured 422px wide, implying a 1.4257 scale, when
the monitor is really **1.5** and the window was simply wrong in both
dimensions. With `min_size` set it measures 444×81 — exactly 296×54 at 1.5.
Don't infer scale from a window whose size you have not yet verified.

### The suspend was dead code until step 11

`_suspend_webview()` had shipped logging its own failure on every single launch, for
two reasons stacked on top of each other — and the second was invisible until the
first was fixed:

1. `.CoreWebView2` is *itself* a COM property read, and it sat **outside** the
   `native.Invoke(...)` that existed to marshal exactly that onto the UI thread. It
   threw E_NOINTERFACE before reaching the line meant to prevent it.
2. The method is **`TrySuspendAsync`**. There is no `TrySuspend`; the call raised
   `AttributeError` into the same generic `except`, which is why fixing (1) changed
   the error message rather than the behaviour.

WebView2 also refuses to suspend a *visible* control, so the control is hidden first.
`IsSuspended` is read on the way back out — it is the only direct evidence the suspend
took, since `TrySuspendAsync` completes after the host has stopped looking.

Attributed with `NEBULA_NO_SUSPEND=1`, two runs each, reproducible within 3 MB:

| renderer suspend | USS peak | USS final |
|---|---|---|
| disabled | 187 MB | **185 MB** — flat, nothing decays |
| enabled | 172 MB | **69 MB** |

**~115 MB, in the state the app spends almost all its life in.** The tell is the shape,
not the endpoint: without the suspend, USS never decays at all.

This is memory only. GPU while hidden was already 0.0 % — that is the `.asleep` CSS
pausing the animations, and it was measured separately (median-of-7, PID-attributed to
our own tree). Two independent mechanisms, two independent wins; don't credit either
with the other's.

Frame timing, from the in-window HUD: **p50 8.3 ms at 120 fps**, with the aurora
drifting, both star layers parallaxing, the spotlight tracking the pointer and the
live block pulsing. The same backdrop on `tk.Canvas` measured **p50 110 ms at 95 % CPU**
and had to be baked static.

Three things worth pulling out:

1. **The current app is the heavier one.** `gui.py` holds the generated backdrop, the
   starless second surface, `_composite`, the glass cache and the thumbnail cache as PIL
   images in the Python heap. The webview holds the same picture as GPU textures.
2. **Animation is free, and it stops when hidden.** CPU is 0.00 % visible *and*
   minimised, and USS drops ~150 MB when the window goes away. That is the constraint
   that governs Nebula — a tray app running while a game is in the foreground — and it
   lands on the right side of it.
3. **The comparison is slightly unfair to the spike, in the spike's favour to fix.**
   The spike does not yet run `Monitor`, the tray, hotkeys, the offloader or GameSync.
   Those are the same Python in both worlds, so they add to both equally, but the spike's
   435 MB will grow when they land.

## What was proved about the port

**`obsauto/` was not modified.** `spike/app.py` imports `session_log`, `forecast`,
`config` and `design_v3` exactly as they are. Real clips, real spans, real disk forecast,
real "not enough history" state — all first try.

**The design contract survived the renderer change.** `spike/gen_tokens.py` generates
`web/tokens.css` from `design_v3.py`, so a v3 number still lives in exactly one place.
The layout maths (blob counts, size fractions, alphas, motion cycles) is handed to JS as
JSON from the same module. No hex is typed by hand anywhere in the stylesheets.

**`dv.over()` becomes unnecessary.** That function exists only because a `tk.Canvas` item
has no alpha channel, so every "accent at 0.10" had to be composited to a flat hex against
whatever it sat on. CSS expresses it natively. The same is true of the starless second
backdrop surface, `_composite` corner-sampling, and the whole `theme_art.py` blit path.

**`BACKGROUND_MOTION_UNUSED` is no longer unused.** All nine values are live in
`web/tokens.css` and `app.js`.

## What the spike does not answer

- **Tray, hotkeys, single-instance, PyInstaller packaging.** All still Python, all
  unchanged in principle, none exercised here.
- **The mini overlay** (296×54, always-on-top) — a second pywebview window. Untested.
- **Startup time.** Not measured. WebView2 has a cold-start cost `tk` does not.
- ~~**Whether 288 MB minimised is good enough**~~ — **answered, and it is.** With the
  renderer suspend actually working it is **69 MB** hidden. A Rust shell would replace
  the ~40 MB Python host; the WebView2 processes are the rest and they are the same
  either way. Tauri is not worth the toolchain for this.

## Defects the screenshot loop found in one afternoon

Each of these was invisible to every existing test and obvious in a PNG.

1. **`rgb(var(--x-rgb) / .82)` with a comma-separated triplet is a parse error.** The
   declaration is dropped in silence. Result: a window with no card surfaces and no
   aurora at all. Now generated space-separated, with the reason recorded in
   `gen_tokens.py`.
2. **A pywebview `Window` stored as a public attribute on the js_api object kills the
   whole bridge.** pywebview enumerates public attributes; the Window's
   `.native.browser.webview` COM properties throw off the UI thread. Every API call then
   fails with no message on either side. Now `self._window`.
3. **`pywebviewready` had already fired** before `app.js` parsed, so a plain listener
   waited forever. Now polls for the api.
4. **A span's `live` flag is not "recording now."** It means no `rec_stop` was ever seen,
   which is also true of a span the log abandoned — `sessions.jsonl` has one from 28 July
   that reads live forever. The titlebar said "Recording" five days after the fact.
5. **Three stale instances were running at once**, so consecutive screenshots were of
   different processes and the results looked non-deterministic. `tools/shoot.py --list`
   now settles that in one command.

## Known deviations from the spec, deliberate

- **Star dust reads through the panels.** BUILD-SPEC wants the aurora to show through a
  card but never the dust — `gui.py` achieves it with a second, starless render. The
  spike has one backdrop, so both show through. Fix is a starless layer behind `.chrome`;
  not done, because it does not affect the measurements this spike exists to take.
- **Only the Clips pane is built**, and only its ribbon, tiles and rows. The rail switches
  panes but the other four are empty.
- **No thumbnails.** `thumbs.py` is wired in the API surface but the spike does not call
  ffmpeg.
