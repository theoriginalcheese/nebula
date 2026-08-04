# t003 — The toast (2i) and the mini overlay (2k)

Both are **separate pywebview windows** with their own HTML/CSS/JS files. This
is deliberate: another agent is working in `spike/web/app.*` and
`spike/host.py` at the same time.

## ⛔ File ownership — this matters more than usual

**You may create and edit only:**
```
spike/web/toast.html      spike/web/toast.css      spike/web/toast.js
spike/web/overlay.html    spike/web/overlay.css    spike/web/overlay.js
spike/windows.py          (new — the two window classes)
```

**Do NOT touch** `spike/web/app.js`, `spike/web/app.css`,
`spike/web/index.html`, `spike/app.py`, `spike/host.py`. If you need something
from the host, define the interface in `spike/windows.py` and say in your report
what needs calling — the other agent will wire it. A change to a shared file
will be reverted regardless of quality.

`spike/web/tokens.css` is generated and shared — **link it, never edit it.**

## The toast — frame 2i

Read `tests/test_toast.py` first. It encodes the v3 contract and the same rules
apply here.

- **One slot for the whole process life.** The first event builds it; every
  later event *mutates it in place* and resets the drain. Never a stack, never a
  queue. v3's note: "Build the replace path before the visuals."
- **Exactly one self-rescheduling tick chain.** A second chain drains the life
  at double rate — this was a real bug.
- Rise 16px over 320ms in, fade 200ms out (`--pane-change-rise`, `--ease`).
- 4s drain, **frozen while hovered**.
- Positioned against the *active* monitor's work area. `test_toast` is a known
  environmental flake for exactly this reason — do not "fix" it by hard-coding.

## The mini overlay — frame 2k

- 296×54, frameless, always-on-top, no taskbar entry.
- **Never shows while idle** — only during a recording.
- Timer + game + collapse, per the spec. Anthony's documented deviation adds
  **Pause/Resume, Stop & save, Mark clip** — keep those; they are a deliberate,
  recorded deviation, not drift.
- Position persists **per monitor** — `config.json` already has
  `mini_overlay_positions` keyed by monitor geometry. Reuse that key format
  exactly; `tests/test_step7.py` asserts it.
- Timer uses tabular figures and must not reflow its neighbours.

## Rules that still apply

- `transform` and `opacity` only. These are separate windows, so their
  animation does not composite the main window — but the cost budget stands.
- No fabricated numbers. No timer until there is a real recording to time.
- Two-layer cards; tokens only, no hand-typed hex, radii, durations or easings.
- Both windows must respect `prefers-reduced-motion` by **pausing**, not
  clearing.

## Definition of done

The standard gate, plus:
- `python tools/gpu_ab.py` unchanged from baseline — a new always-on-top window
  must not add measurable GPU cost while the main window is asleep
- screenshots of both windows that you **open and describe**
- a report listing exactly which host calls you need wired, since you cannot
  wire them yourself
