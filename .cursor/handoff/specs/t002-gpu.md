# t002 — Cut the GPU cost, then make the star dust drift like wind

This is a **measured performance task with a hard numeric target**, plus one
visual change. Do the performance work first; the visual change must not undo it.

## The problem

Nebula's webview is eating the integrated GPU. Measured on this machine:

| | before | after my fixes | target |
|---|---|---|---|
| visible | 76% | 42% | **under 15%** |
| minimised (tray) | 76% | **41%** | **under 3%** |

Minimised is the number that matters most: Nebula is a tray app that runs the
whole time a game owns the GPU.

## How to measure — do not skip this, and do not measure by process name

```powershell
$neb = Get-Process python | Select-Object -ExpandProperty Id
$all = Get-Process msedgewebview2
$mine = @(); foreach ($p in $all) {
  $anc = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)").ParentProcessId
  $d=0; while ($anc -and $d -lt 6) { if ($neb -contains $anc) { $mine += $p.Id; break }
    $anc = (Get-CimInstance Win32_Process -Filter "ProcessId=$anc" -EA SilentlyContinue).ParentProcessId; $d++ } }
$c = (Get-Counter '\GPU Engine(*)\Utilization Percentage').CounterSamples
$sum=0; foreach ($s in $c) { if ($s.InstanceName -match 'pid_(\d+)' -and $mine -contains [int]$Matches[1]) { $sum += $s.CookedValue } }
"{0:N1}%" -f $sum
```

There are ~20 `msedgewebview2.exe` processes on this machine and only **6** are
Nebula's. Summing by process name overstates the figure and hides the answer.
Verified: Nebula's six = 41.6%, every other webview = 0.0%.

## What is already done (do not redo)

1. The perf HUD's `requestAnimationFrame` loop is now opt-in via `?hud=1`. It
   was forcing a composite on every display refresh forever — a debug
   instrument that changed what it measured.
2. `will-change: transform` removed from all 12 layers. It pinned a GPU texture
   per element for the page's lifetime; on integrated graphics VRAM is system
   RAM, so it cost memory too.
3. `spike/host.py start_window_watch()` polls `IsIconic` / `IsWindowVisible`
   once a second and calls `setAwake(false)`, which adds `.asleep` to
   `<html>` and sets `animation-play-state: paused` on every layer.
   **`document.hidden` never fires for a Win32 minimise of a frameless
   WebView2**, which is why this watcher exists.

## Your job, part 1 — find why minimised is still 41%

Pausing the animations did not drop it. **First verify the pause is actually
taking effect** — confirm `.asleep` really lands on `<html>` when minimised and
that `evaluate_js` from the watcher thread is not silently failing. If it is not
working, fix that and re-measure before doing anything else.

If the pause *is* working and the GPU is still pinned, the prime suspect is the
blur, not the motion: 3 aurora blobs at `blur(54–110px)` plus 7 wisps over a
1898×1156 surface. Blur area, not animation ticks, is likely dominating.

Things worth trying, cheapest first — **measure after each, one at a time, and
report the number**:

- Stop compositing entirely while asleep (`content-visibility`, `display:none`
  on `.backdrop`, or similar) rather than only pausing animations. Restoring
  must not visibly jump — the spec's "nothing is removed, nothing goes flat"
  still applies when the user reopens the window.
- Reduce blur radius, or render the aurora once to a `<canvas>`/bitmap and
  transform that single layer instead of compositing ten blurred elements.
- Fewer, larger blobs rather than 3 blobs + 7 wisps.

`obsauto/design_v3.py` owns these numbers. If a value needs to change, change it
there and re-run `python spike/gen_tokens.py` — never edit `tokens.css`.

Record any spec deviation with its measured justification, the same way
`design_v3.py` already documents why blob alpha was raised above the spec's .22.

## Your job, part 2 — wind, not parallax

Right now the two star layers slide straight up at a constant speed. The wanted
effect: **all the dots drift as if a slow gust is passing through** — a shared
direction that changes gradually, so every dot moves together rather than each
doing its own thing, with the far layer lagging the near one.

Constraints:
- `transform` and `opacity` only. No per-dot elements, no JS animating position
  per frame. The starfield is one `box-shadow` per layer and must stay that way.
- It must cost **less** than what it replaces, not more. Measure it.
- Must pause with `.asleep` and with `prefers-reduced-motion`, like everything else.

A slow drift on a shared vector, with the two layers offset in phase and speed,
gets the effect for the price of the transforms already being paid.

## Definition of done

Everything in the standard gate, plus:

- the measurement command above, run and reported for **visible** and
  **minimised**, with the before/after numbers
- a screenshot of the Clips pane that you **actually open and describe**
- if you miss the targets, say so with the numbers rather than rounding up.
  A measured 12% that fell short is useful; a claimed 3% is not.
