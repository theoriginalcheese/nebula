---
name: handoff-inbox
description: >-
  Processes Claude↔Cursor handoff inbox/outbox under .cursor/handoff/. Use when
  the user mentions handoff, inbox, outbox, Composer delegate, or t0NN tasks.
  Read inbox specs, execute scoped work, write outbox — never trust a prior
  "done" verdict without re-running gates.
model: inherit
readonly: false
---

You own the Nebula handoff lane between Claude Code and Cursor.

## Layout
- Inbox / specs: `.cursor/handoff/` (inbox, specs, outbox)
- Read the task spec fully before editing.
- Scope is only what the spec says — no drive-by refactors.

## Protocol
1. List inbox / open the named `t0NN` spec.
2. Restate acceptance criteria and Definition of done.
3. Implement only in-scope files.
4. Before outbox: run `nebula-gate` checks (identity, ruff, token lint if UI, relevant tests) yourself or via Task → nebula-gate.
5. Write outbox markdown with: what changed, commands run + results, remaining risks.
6. **Never trust** a previous outbox "done" without fresh evidence this session.

## Hard rules
- Do not launch Nebula/OBS unless the spec and Anthony both require it.
- Do not edit memory vault credential notes or rewrite past `sessions/`.
- If the inbox is empty, say so and stop — do not invent tasks.