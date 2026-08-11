# Nebula — agent brief

Windows desktop app (Python + CustomTkinter + WebView2). Watches for the active
game, drives **OBS** recording over obs-websocket v5, files recordings per game,
runs from the tray. Code is `obsauto/`; `main.py` is the entry point.

This file is an **index**, not a manual. It stays small on purpose — everything
below loads on demand, so you pay for depth only when you need it.

## Automatic — you do not invoke these

| When | What happens |
|---|---|
| Session start | Live checkout identity + gate status are injected for you |
| Any shell command | Launching Nebula/OBS is **denied**; destructive commands denied or confirmed |
| You stop / a subagent stops | ruff + token lint + skill-sync run; failures come back as a follow-up |
| Session end | A usage row is appended to `.cursor/handoff/token-ledger.jsonl` |

So: don't announce "done" ahead of the gate, and don't plan a workflow around
starting the app. Kill switch: `touch .cursor/hooks/DISABLED`.

## Load on demand

Nothing here is in context until you ask for it. Reach for it by name.

| Need | Load |
|---|---|
| Hard work with more than one sensible approach — implementation, UI, refactor, architecture | skill **`best-of-n-specialists`** — three specialists in parallel worktrees, `delegate.py verify` picks the winner |
| Building/changing UI, or hunting a visual defect | skill **`nebula-ui`** — authority order, hard rules, screenshot loop |
| A pane looks right but feels cheap; adding transition/hover/focus/empty states | skill **`nebula-polish`** — the checklist a screenshot can't verify |
| "Is this the exe or the checkout?"; something looks stale after an edit | rule **`nebula-identity`** — full exe-vs-source contract |
| Working the handoff inbox / a `t0NN` task | rule **`handoff`** |
| Module map, invariants, performance history | **`CLAUDE.md`** (28KB — read the section, not the file) |
| The UI contract itself | **`design/ui-v3/BUILD-SPEC.md`** — outranks the frames, which outrank everything else |

`nebula-ui-v3` loads itself automatically when you touch `obsauto/` UI files,
`design/ui-v3/**` or `spike/web/**`.

## Delegate rather than doing it all inline

`nebula-gate` (Definition of done) · `nebula-ui-auditor` (toast/token/CSS claims) ·
`handoff-inbox` (`t0NN`) · `verifier` (after any "done") · `debugger` (races, hangs,
silent crashes) · `test-runner` · `pr-reviewer`. Don't rubber-stamp one — if the
gate fails, fix it and re-run.

## Traps — one line each, detail behind the links above

1. **Never animate the `tk.Canvas` per-frame.** Any change forces a full-window
   composite (~100ms), flat cost. Measured p50 110ms at 95% CPU → 16ms at 4%.
2. **`except X as e` unbinds `e`** when the block exits — a `lambda` capturing it
   for `after()`/`_ui()` dies with `NameError`, **silently** under `pythonw`.
3. **Never call `obs.connect()` on the Tk thread.** Blocks up to 5s; at startup
   that's the normal case. Worker thread, marshal back via `_ui()`.
4. **No fabricated data.** Build the source or omit the element — never a
   plausible placeholder, never a `0` meaning "not implemented".
5. **`print()` goes nowhere** — it runs as `pythonw`. Diagnostics via `app_log`.

## Definition of done

The first two run automatically when you stop.

```bash
python -m ruff check .
python tools/lint_tokens.py    # if you touched spike/web CSS or JS
python tests/test_<relevant>.py # smallest relevant subset, not the full suite
python tools/nebula_identity.py # which checkout am I
```

Never claim done on a previous session's evidence. Re-run the gate.

## The tooling, in one place

```bash
python tools/agent.py          # lists every tool and what it does
python tools/agent.py gate     # ruff + token lint + skill sync, ~0.2s
python tools/agent.py gate!    # full gate incl. the three test suites, ~4.4s
python tools/agent.py check    # gate + skill sync in one pass
python tools/agent.py budget   # what costs context every turn
```

Arguments pass straight through: `agent.py audit --task t013`. It is a lazy
dispatcher over the existing scripts, not a wrapper around them — the hooks still
call those scripts directly, so nothing on the hot path got slower.

Durable notes go to the Obsidian vault, never into this repo.
