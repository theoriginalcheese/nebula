---
name: nebula-ui
description: Building or changing Nebula's interface - panes, chrome, backdrop, cards, the v3/v4 design contract, or anything under design/ui-v3/, spike/web/, obsauto/gui.py or obsauto/design_v3.py. Use whenever a change is meant to look like the mockup, and whenever a visual defect needs finding. Carries the authority order, the hard rules that outrank the mockup, and the screenshot loop that verifies the result.
---

# Nebula UI

## Authority order

```
design/ui-v3/BUILD-SPEC.md  >  design/ui-v3/frames/*.png (and FRAMES.md)  >  everything else
```

The mockup states it itself: *"If a frame and this table disagree, this table wins."*

Numbers live in **`obsauto/design_v3.py`** and nowhere else. Never type a hex or a
radius at a call site. In the webview, `spike/gen_tokens.py` turns that module into
`spike/web/tokens.css` — change the Python and re-run it; never hand-edit the CSS.

`design/ui-v3/_ds/nocturne-*/styles.css` is a **decoy**. v3 overrides it wholesale.
Never link it, never take a token from it.

## Look before you write, and look after

Nebula is a visual product. Do not describe what you think the UI does — capture it.

```bash
python tools/frames.py --only 2b        # the design  -> design/ui-v3/frames/2b.png
python tools/shoot.py --out shots/2b.png   # what you built -> shots/2b.png
```

`Read` both PNGs and compare them as pictures. Then fix, re-capture, and look again.
Every fidelity defect in the 6.7 list — the aurora rendering at 3.6% instead of 19%,
stars over the chrome, missing second card layers — was invisible to the test suite
and obvious in a screenshot.

`shoot.py` captures **either** renderer (`gui.py` or `spike/app.py`); both are just
top-level HWNDs, so old-vs-new is a fair comparison.

If a change is meant to be visible and you have not looked at it, you are not done.

## The hard rules — these outrank the mockup

1. **Never animate the main `tk.Canvas` per-frame.** Any mutation costs one full
   *window* composite, ~100ms, flat — independent of how much changed. A 12fps
   decorative timer measured p50 110ms at 95% CPU. `tests/test_frame_pacing.py`
   fails if one returns. **This rule is Tk-only**: in `spike/`, animating
   `transform` and `opacity` is free (measured 0.00% CPU at 120fps) — but animating
   anything else there (width, top, filter, box-shadow) reintroduces layout and
   paint, so keep to those two properties.
2. **No fabricated numbers.** Build the source or omit the element. A plausible
   figure with nothing behind it is the one defect users cannot detect.
3. **Never `obs.connect()` on the Tk thread** — it blocks up to a 5s socket timeout,
   and at startup that is the normal case.
4. `except X as e:` **unbinds `e`** when the block exits. Bind to a plain local
   before building any deferred closure, or `root.after` dies with `NameError`.
5. Cards come from `dv.CARD_LAYERS`. A flat single-border card is a bug: every card
   is a tinted shell wrapping a darker core, and `inner radius = outer − padding`.
6. Anything async must be tested under a real `mainloop()`.

## Two renderers, one contract

| | `obsauto/gui.py` (v3, shipping) | `spike/` (v4 candidate) |
|---|---|---|
| Surface | `tk.Canvas` + PIL | WebView2 + CSS |
| Alpha | none — `dv.over()` flattens to hex | native `rgb(r g b / a)` |
| Motion | quarantined in `BACKGROUND_MOTION_UNUSED` | live, on the compositor |
| Measured | p50 16ms static, 513 MB | p50 8ms animating, 435 MB |

Read `spike/FINDINGS.md` before arguing about which to touch.

## Traps that have already cost time

- **`rgb(var(--x-rgb) / .3)` needs a SPACE-separated triplet.** `rgb(24, 20, 40 / .82)`
  is a parse error, the declaration is dropped silently, and the surface simply does
  not paint. This produced a window with no cards and an invisible aurora.
- **Never store a pywebview `Window` on the js_api object as a public attribute.**
  pywebview walks public attributes to expose them; a Window's
  `.native.browser.webview` COM properties throw off the UI thread and take the whole
  bridge down — every api call then fails with no message. Use `self._window`.
- **`pywebviewready` may have fired before your script parsed.** Poll for
  `window.pywebview.api` instead of only listening for the event.
- **A span's `live` flag means "no rec_stop was seen"**, not "recording now" — an
  abandoned span reads live forever. Check it is the last span and its `end` is within
  a few seconds of now.
- **Kill filters match themselves.** `python -c "...'spike'..."` has `spike` in its own
  command line; exclude `os.getpid()` or the script kills its own shell.
- **Check for duplicate windows before trusting a capture.** `python tools/shoot.py --list`.
  Two stale instances mean you are screenshotting a process you did not just change.

## Measuring

```bash
python tools/bench.py --launch spike --seconds 20 --minimised
python tools/bench.py --launch gui   --seconds 20
```

Compare **private (USS)**, not summed RSS — summed RSS counts Chromium's shared pages
once per process and inflates any webview by hundreds of MB against single-process Tk.

The number that governs Nebula is idle cost *while hidden*: it is a tray app that runs
the whole time a game is in the foreground, on a laptop with no free RAM slots.
