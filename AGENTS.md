# Nebula — agent brief

Windows desktop app (Python + CustomTkinter + WebView2) that watches for the active
game, drives **OBS** recording over obs-websocket v5, and files recordings per game.
Runs from the system tray. Active code is `obsauto/`; `main.py` is the entry point.

**This file is the 30-second version.** Code facts live in `CLAUDE.md` (long, and worth
reading before a first edit to `obsauto/gui.py`). UI work is governed by
`design/ui-v3/BUILD-SPEC.md`.

## Don't launch the app or OBS

Launching Nebula starts a **real OBS recording**; killing it orphans one. Ask first.
`.cursor/hooks/guard-app-launch.py` blocks this at the shell. To judge UI, use the
process that is already running, or the sanctioned demo tools
(`tools/demo_toast.py`, `tools/audit_toasts.py`).

## What runs automatically

`.cursor/hooks/` is wired (full detail in its `README.md`). You do not need to be
told about these each session — they are already running:

| When | What happens |
|---|---|
| Session start | The checkout identity and the current gate status are injected for you |
| Any shell command | Commands that would launch Nebula or OBS are **denied** |
| You stop, or a subagent stops | ruff + token lint run; a failure comes back as a follow-up |
| Session end | A usage row is appended to `.cursor/handoff/token-ledger.jsonl` |

Consequences worth internalising: a gate failure will be handed back to you, so
don't announce "done" ahead of it; and the launch block is real, so don't plan a
workflow around starting the app.

Kill switch: `touch .cursor/hooks/DISABLED`.

## Definition of done

`.cursor/hooks/gate.py` runs the first two automatically when you stop:

```bash
python tools/nebula_identity.py     # which checkout am I? quote kind + git_head
python -m ruff check .
python tools/lint_tokens.py         # if you touched spike/web CSS or JS
python tests/test_<relevant>.py     # smallest relevant subset, not the full suite
```

Never claim done on a previous session's evidence. Re-run the gate.

## Identity — the trap that wastes the most time

Two installs must never be mixed when judging UI:

| | Path | What it is |
|---|---|---|
| Source | `C:\Users\antho\nebula` | git checkout — what you edit |
| Frozen | `C:\Users\antho\Nebula\` | packaged exe, **its own** config/logs, UI baked at build time |

Never use the frozen exe's behaviour to decide whether source needs a fix.

## Five things that will bite you

1. **Never animate the `tk.Canvas` per-frame.** Any canvas change forces a full-window
   composite (~100ms), and the cost is *flat* — a 2px star costs what a full-window
   image move costs. A 12fps decorative timer measured p50 110ms at 95% CPU; removing
   it gave 16ms at 4%. `tests/test_frame_pacing.py` fails if one returns.
2. **`except X as e` unbinds `e` when the block exits.** Any `lambda` capturing it that
   runs later via `after()`/`_ui()` dies with `NameError`. Bind to a plain local first.
   Under `pythonw` this crash is **silent** — which is why `report_callback_exception`
   routes to the app log. Don't remove that.
3. **Never call `obs.connect()` on the Tk thread.** It blocks up to 5s, and at startup
   that is the normal case. Worker thread, marshal back through `_ui()`.
4. **No fabricated data.** Every number in the v3 frames is mockup filler. If a value
   has no real source, build the source or omit the element — never a plausible
   placeholder, never a `0` that means "not implemented". Macropad has no HID layer and
   stays honestly empty.
5. **Silent runs.** It runs as `pythonw`, so `print()` goes nowhere. Diagnostics go
   through `app_log` to a file.

## Where things are

| Path | What |
|---|---|
| `CLAUDE.md` | Full module map, invariants, performance history |
| `design/ui-v3/BUILD-SPEC.md` | UI authority. Outranks the frames, which outrank everything else |
| `obsauto/design_v3.py` | That contract as code — palette, geometry, type scale |
| `.cursor/rules/*.mdc` | Scoped rules; `nebula-ui-v3` loads on UI paths |
| `.cursor/hooks/` | Session hooks + their self-tests (`README.md` there) |
| `.cursor/handoff/` | Claude↔Cursor task lane: `inbox/` → `outbox/` → `done/` |

## Subagents

Delegate rather than doing everything in the parent: `nebula-gate` (Definition of done),
`nebula-ui-auditor` (toast/token/CSS claims), `handoff-inbox` (`t0NN` tasks), plus the
user agents `verifier`, `debugger`, `test-runner`, `pr-reviewer`. Don't rubber-stamp a
subagent — if the gate fails, fix it and re-run.

## Durable notes

Facts that outlive a session go to the Obsidian vault at
`C:\Users\antho\Claude Memories\claude-memory`, not into this repo.
