"""The session log - `sessions.jsonl`, spec 7b's data layer and 7g's step 1.

    "Write the log first. The ribbon is only a rendering of sessions.jsonl.
     Emit those five event types from the existing monitor and OBS handlers
     before building any of this UI - then 7c's forecast and 7e's clip search
     read from the same file for free."

Five event types, appended one JSON object per line:

    rec_start  a recording began          {game, appid}
    rec_stop   it ended                   {game, appid, path, duration, size, culled}
    idle_in    recording paused on idle   {game, reason}
    idle_out   it resumed                 {game}
    mark       a chapter/clip mark        {game, path, offset}

Append-only and line-oriented on purpose: two processes can write to it without
coordinating, a partial write costs one line rather than the file, and reading
"today" never needs the whole history parsed. Nothing here raises - a telemetry
file must never be able to stop a recording.

The stat tiles in 6.3 (Auto-culled, Idle pauses, Recorded) are the first
readers; the ribbon (7b), the storage forecast (7c) and the palette's recent
clips (7e) are the rest.
"""

import json
import os
import threading
import time

from .paths import APP_DIR

LOG_NAME = "sessions.jsonl"

EVENT_TYPES = ("rec_start", "rec_stop", "idle_in", "idle_out", "mark")

# One process, one lock. Appends are small and rare (a handful an hour), so the
# cost of holding it is irrelevant next to the cost of interleaved lines.
_lock = threading.Lock()


def log_path():
    """Read APP_DIR live rather than binding it at import: main.py repoints the
    data directory for sync *after* this module is first imported."""
    return os.path.join(APP_DIR, LOG_NAME)


def append(event_type, game=None, appid=None, path=None, **fields):
    """Record one event. Returns the row written, or None if it couldn't be.

    Never raises. A full disk or a locked file is not a reason to interrupt a
    recording, and the callers are the monitor's own hot handlers.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown session event {event_type!r}")
    row = {"ts": time.time(), "type": event_type}
    if game:
        row["game"] = game
    if appid:
        row["appid"] = appid
    if path:
        row["path"] = path
    row.update({k: v for k, v in fields.items() if v is not None})
    line = json.dumps(row, separators=(",", ":")) + "\n"
    try:
        with _lock:
            with open(log_path(), "a", encoding="utf-8") as f:
                f.write(line)
    except OSError:
        return None
    return row


def read(since=None, limit=None):
    """Events oldest-first, optionally only those at or after `since` (epoch).

    Skips malformed lines rather than failing on them: an append interrupted by
    a power cut leaves a partial last line, and losing one event is much better
    than losing the reader.
    """
    p = log_path()
    if not os.path.exists(p):
        return []
    rows = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or "ts" not in row:
                    continue
                if since is not None and row["ts"] < since:
                    continue
                rows.append(row)
    except OSError:
        return []
    return rows[-limit:] if limit else rows


def day_start(when=None):
    """Midnight local time for the day containing `when`."""
    t = time.localtime(when if when is not None else time.time())
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


def today():
    """The four figures the dashboard's stat tiles show (6.3).

    Every one is counted from events that were actually emitted - there is no
    fallback that invents a plausible number, so a fresh install shows zeros
    because zero is true, not because the source is missing.
    """
    rows = read(since=day_start())
    clips = culled = idle_pauses = 0
    recorded = 0.0
    bytes_written = 0
    for row in rows:
        kind = row.get("type")
        if kind == "rec_stop":
            recorded += float(row.get("duration") or 0)
            if row.get("culled"):
                culled += 1
            else:
                clips += 1
                bytes_written += int(row.get("size") or 0)
        elif kind == "idle_in":
            idle_pauses += 1
    return {"clips": clips, "recorded_seconds": recorded, "bytes": bytes_written,
            "culled": culled, "idle_pauses": idle_pauses}
