"""Backfill .cursor/handoff/token-ledger.jsonl from Cursor's attribution DB.

Nothing ever wrote that ledger automatically, so it holds three hand-made rows
from 2026-08-03 and stops at t002 - while the handoff lane ran to t013. The
history is recoverable: Cursor's ai-code-tracking.db is keyed by conversationId,
which is the same id sessions.json already stores per task.

What this cannot recover: cost. Cursor records attribution, not spend. Those
columns stay null here exactly as they do in the live hook.

Existing rows are never touched and never duplicated - a task already in the
ledger is skipped.

    python tools/backfill_ledger.py            # show what would be added
    python tools/backfill_ledger.py --apply
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, ".cursor", "handoff", "token-ledger.jsonl")
SESSIONS = os.path.join(ROOT, ".cursor", "handoff", "sessions.json")
TRACKING_DB = os.path.join(
    os.path.expanduser("~"), ".cursor", "ai-tracking", "ai-code-tracking.db"
)


def existing_tasks() -> set[str]:
    tasks = set()
    if not os.path.isfile(LEDGER):
        return tasks
    with open(LEDGER, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                task = json.loads(line).get("task")
            except ValueError:
                continue
            if task:
                tasks.add(task)
    return tasks


def gate_results() -> dict[str, bool]:
    """delegate.py's ledger.jsonl records a gate verdict per task."""
    path = os.path.join(ROOT, ".cursor", "handoff", "ledger.jsonl")
    out: dict[str, bool] = {}
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("event") == "gate" and rec.get("task"):
                out[rec["task"]] = bool(rec.get("ok"))
    return out


def rows_for(conn: sqlite3.Connection, task: str, chat_id: str, gates: dict) -> dict | None:
    stats = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT fileName), MIN(timestamp), MAX(timestamp) "
        "FROM ai_code_hashes WHERE conversationId = ?",
        (chat_id,),
    ).fetchone()
    if not stats or not stats[0]:
        return None
    models = sorted(
        m for (m,) in conn.execute(
            "SELECT DISTINCT model FROM ai_code_hashes "
            "WHERE conversationId = ? AND model IS NOT NULL",
            (chat_id,),
        )
    )
    count, files, first_ms, last_ms = stats
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(first_ms / 1000)),
        "chat_id": chat_id,
        "task": task,
        "model": models[0] if len(models) == 1 else (models or None),
        "gate_passed": gates.get(task),
        "gate_ts": None,
        "source": "backfill:ai-tracking",
        "transcript_chars": None,
        "est_tokens_chars_div_4": None,
        "claude_cost_usd": None,
        "charged_usd": None,
        "duration_ms": (last_ms - first_ms) if last_ms and first_ms else None,
        "final_status": None,
        "is_background_agent": None,
        "ai_authored_hashes": count,
        "ai_authored_files": files,
        "ai_models": models or None,
    }


def main(argv: list[str]) -> int:
    if not os.path.isfile(TRACKING_DB):
        print(f"no tracking db at {TRACKING_DB}")
        return 1
    if not os.path.isfile(SESSIONS):
        print(f"no sessions.json at {SESSIONS}")
        return 1

    with open(SESSIONS, encoding="utf-8") as handle:
        sessions = json.load(handle)
    have, gates = existing_tasks(), gate_results()

    uri = f"file:{TRACKING_DB.replace(os.sep, '/')}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    try:
        new = []
        for task, chat_id in sorted(sessions.items()):
            if task in have:
                continue
            row = rows_for(conn, task, chat_id, gates)
            if row:
                new.append(row)
    finally:
        conn.close()

    if not new:
        print("nothing to backfill - every task with data is already in the ledger")
        return 0

    print(f"{'task':8} {'hashes':>7} {'files':>6} {'gate':>6}  first activity")
    for row in new:
        gate = {True: "pass", False: "FAIL", None: "?"}[row["gate_passed"]]
        print(f"{row['task']:8} {row['ai_authored_hashes']:7} "
              f"{row['ai_authored_files']:6} {gate:>6}  {row['ts']}")

    if "--apply" not in argv:
        print(f"\n{len(new)} row(s) would be appended. Re-run with --apply.")
        return 0

    # Append in chronological order so the file stays a timeline.
    with open(LEDGER, "a", encoding="utf-8") as handle:
        for row in sorted(new, key=lambda r: r["ts"]):
            handle.write(json.dumps(row) + "\n")
    print(f"\nappended {len(new)} row(s) to {os.path.relpath(LEDGER, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
