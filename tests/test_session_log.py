"""session_log.today() — dashboard tiles, unique kept paths.

    python tests/test_session_log.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import session_log

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


def test_today_dedupes_duplicate_rec_stop():
    work = tempfile.mkdtemp(prefix="nebula-today-")
    path = os.path.join(work, "sessions.jsonl")
    session_log.log_path = lambda: path
    now = time.time()
    clip = os.path.join(work, "Roblox", "same.mkv")
    rows = [
        {"ts": now - 200, "type": "rec_start", "game": "Roblox"},
        {"ts": now - 100, "type": "rec_stop", "game": "Roblox",
         "path": clip, "size": 4784128},
        {"ts": now - 99.9, "type": "rec_stop", "game": "Roblox",
         "path": clip, "duration": 103.0, "size": 4784128},
        {"ts": now - 50, "type": "rec_stop", "game": "Other",
         "path": os.path.join(work, "Other", "b.mkv"), "duration": 10, "size": 1},
        {"ts": now - 40, "type": "rec_stop", "game": "Anon", "duration": 5},
        {"ts": now - 30, "type": "rec_stop", "game": "Anon2", "duration": 5},
    ]
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    stats = session_log.today()
    check("duplicate path counts as one clip", stats["clips"] == 4, stats)
    check("later stop supplies duration", stats["recorded_seconds"] == 123.0, stats)
    check("anonymous stops still count separately", stats["clips"] == 4, stats)


def test_read_skips_corrupt_lines():
    """The reader's documented contract: an append interrupted mid-write
    (power cut) leaves a partial last line, and junk must never take the
    reader down - losing one event beats losing every stat tile."""
    work = tempfile.mkdtemp(prefix="nebula-slog-corrupt-")
    path = os.path.join(work, "sessions.jsonl")
    session_log.log_path = lambda: path
    now = time.time()
    good = {"ts": now - 10, "type": "rec_start", "game": "Game"}
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(good) + "\n")
        f.write('{"ts": broken\n')            # invalid JSON
        f.write('["not", "a", "dict"]\n')     # valid JSON, wrong shape
        f.write('{"type": "rec_stop"}\n')     # dict without ts
        f.write("\n")                         # blank
        f.write(json.dumps({"ts": now - 5,
                            "type": "rec_stop"}) + "\n")
    rows = session_log.read()
    check("corrupt lines skipped, goods kept",
          [r["type"] for r in rows] == ["rec_start", "rec_stop"], rows)
    check("reader survived everything", isinstance(rows, list) and len(rows) == 2)


if __name__ == "__main__":
    test_today_dedupes_duplicate_rec_stop()
    test_read_skips_corrupt_lines()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
    print("ALL PASS")
