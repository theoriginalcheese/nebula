"""sessionEnd - append a row to .cursor/handoff/token-ledger.jsonl.

Nothing has ever written that ledger automatically: delegate.py has no code for
it, so the three existing rows were backfilled by hand on 2026-08-03 and it has
been dead since t002. The whole case for delegating to Composer rests on cost,
and cost was not being measured.

Keeps the original column names so anything already reading the file still
works, and adds duration/status. Cost columns stay null - Cursor does not report
spend to hooks, so a number here would be invented.

Self-test: python record-usage.py --selftest
"""

from __future__ import annotations

import json
import os
import sys
import time

from _common import disabled, emit, project_dir, read_input

LEDGER = os.path.join(".cursor", "handoff", "token-ledger.jsonl")
SESSIONS = os.path.join(".cursor", "handoff", "sessions.json")
GATE_STATE = os.path.join(".cursor", "handoff", ".gate-state.json")


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def task_for(root: str, chat_id: str) -> str | None:
    """sessions.json maps task -> chat_id; invert it to label this session."""
    if not chat_id:
        return None
    for task, cid in _read_json(os.path.join(root, SESSIONS)).items():
        if cid == chat_id:
            return task
    return None


def transcript_size(path: str | None) -> int | None:
    """Character count of the transcript, when Cursor exposes one."""
    if not path or not os.path.isfile(path):
        return None
    try:
        return len(open(path, encoding="utf-8", errors="replace").read())
    except OSError:
        return None


def build_row(root: str, data: dict) -> dict:
    chat_id = str(data.get("conversation_id") or data.get("session_id") or "")
    chars = transcript_size(data.get("transcript_path") or os.environ.get("CURSOR_TRANSCRIPT_PATH"))
    gate = _read_json(os.path.join(root, GATE_STATE))

    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "chat_id": chat_id,
        "task": task_for(root, chat_id),
        "model": data.get("model_id") or data.get("model"),
        "gate_passed": gate.get("passed"),
        "gate_ts": gate.get("ts"),
        "source": "hook:sessionEnd",
        "transcript_chars": chars,
        "est_tokens_chars_div_4": (chars // 4) if chars is not None else None,
        "claude_cost_usd": None,
        "charged_usd": None,
        "duration_ms": data.get("duration_ms"),
        "final_status": data.get("final_status") or data.get("reason"),
        "is_background_agent": data.get("is_background_agent"),
    }


def append(root: str, row: dict) -> bool:
    try:
        path = os.path.join(root, LEDGER)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        return True
    except OSError:
        return False


def main() -> int:
    if "--selftest" in sys.argv:
        root = project_dir()
        sample = {
            "conversation_id": "eca9f8d7-91a6-43cf-a564-579491e4f533",  # t002, from sessions.json
            "model_id": "composer-2.5",
            "duration_ms": 12345,
            "final_status": "completed",
            "is_background_agent": False,
        }
        row = build_row(root, sample)
        print(json.dumps(row, indent=2))
        if row["task"] != "t002":
            print(f"\nFAIL: expected task t002 from sessions.json, got {row['task']!r}")
            return 1
        print("\nok (resolved chat_id -> task; nothing written in selftest)")
        return 0

    if disabled():
        return emit()

    data = read_input()
    if not data:
        return emit()

    append(project_dir(), build_row(project_dir(), data))
    return emit()


if __name__ == "__main__":
    raise SystemExit(main())
