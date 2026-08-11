# Nebula Cursor hooks

Wired in `../hooks.json`. Hooks are spawned processes: JSON on stdin, JSON on
stdout. Everything here **fails open** — a broken hook must never wedge an agent.

| Script | Event | What it does |
|--------|-------|--------------|
| `session-brief.py` | `sessionStart` | Injects the checkout identity (`tools/nebula_identity.py`) and the current gate status as `additional_context`. Only facts that *change* — the static "what's wired" lives in `AGENTS.md`, which Cursor loads for free. |
| `guard-app-launch.py` | `beforeShellExecution` | Denies commands that would launch Nebula or OBS. Four agent files repeat this as prose; this makes it structural. |
| `gate.py` | `stop`, `subagentStop` | Runs ruff + the read-only token checks. On failure returns `followup_message`, so the agent auto-continues into fixing rather than stopping on a false "done". |
| `record-usage.py` | `sessionEnd` | Appends a row to `.cursor/handoff/token-ledger.jsonl`. |

## Why the gate does not shell out to `tools/lint_tokens.py`

That script's `check_tokens_in_sync()` **regenerates `spike/web/tokens.css` in
place** — a 35s subprocess with a write side effect. A stop hook must not do that
to a live working tree, and 35s per stop is unusable besides.

So `gate.py` imports the module and runs its read-only checks directly
(`check_script`, `check_stylesheet`, `check_reduced_motion`,
`check_hidden_attribute`), skipping the regenerating one. Same findings, **0.18s**,
no writes.

That couples the gate to `lint_tokens.py`'s internals. Deliberate: if it is ever
refactored, the gate reports `token lint (UNVERIFIED)` and treats it as a
**failure**, because a check that could not run is unverified, not passed. It will
not silently go green.

`NEBULA_GATE_FULL=1` opts back into the slow, writing sync check.

## Kill switch

```bash
touch .cursor/hooks/DISABLED
```

Every hook no-ops while that file exists. Delete it to re-enable.

## Escape hatches

- **Launching deliberately**: `NEBULA_ALLOW_LAUNCH=1` — read from the environment
  *and* from an inline `VAR=1 cmd` prefix, since the hook runs as its own process
  and never inherits an inline assignment.
- **Fuller gate**: `NEBULA_GATE_FULL=1` (token sync), `NEBULA_GATE_TESTS=1`
  (frame pacing).

## Self-tests

Each script runs standalone. No agent, no session, no writes:

```bash
python .cursor/hooks/guard-app-launch.py --selftest   # 12 allow/deny cases
python .cursor/hooks/session-brief.py --selftest      # prints the context it would inject
python .cursor/hooks/gate.py --selftest               # runs the real gate, reports failures
python .cursor/hooks/record-usage.py --selftest       # resolves chat_id -> task, writes nothing
```

## The ledger

Nothing ever wrote `token-ledger.jsonl` automatically — `delegate.py` has no code
for it, so its first three rows were backfilled by hand on 2026-08-03 and it went
dead after t002. The cost case for delegating to Composer rested on a file nobody
was filling in.

`record-usage.py` writes a row per session, keeping the original column names so
existing readers still work. `task` is resolved by inverting
`.cursor/handoff/sessions.json` (which maps task → chat_id). Cost columns stay
`null`: Cursor does not report spend to hooks, and a number there would be invented.

## Notes

- `afterFileEdit` deliberately isn't used. It returns **no output fields**, so a
  lint hook there would run silently and change nothing the agent can see. The
  gate lives on `stop`/`subagentStop` because those return `followup_message`.
- `failClosed` is off everywhere. Turning it on for `guard-app-launch.py` makes
  the OBS guard a hard guarantee, at the cost of blocking every shell command if
  the script itself ever fails. Worth flipping once it has some mileage.
- `loop_limit: 2` caps gate follow-ups. Cursor enforces it; the gate also tells
  the agent to stop and report rather than silently fixing unrelated failures.
- Changes to `hooks.json` are picked up on **new** sessions. Reload the window to
  apply them to an open one.
