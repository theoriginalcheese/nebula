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


# The file is append-only and never rotated, so it grows for the life of the
# install - and the ribbon re-reads it on every refresh. Reading only the tail
# bounds that: nothing here looks further back than the forecast's 14 days, and
# a year of heavy use is far below this many events.
MAX_READ_BYTES = 4 * 1024 * 1024


def read(since=None, limit=None):
    """Events oldest-first, optionally only those at or after `since` (epoch).

    Skips malformed lines rather than failing on them: an append interrupted by
    a power cut leaves a partial last line, and losing one event is much better
    than losing the reader.

    Only the last MAX_READ_BYTES are parsed. Events are appended in time order,
    so the tail is the recent history every caller actually wants, and the cost
    of a refresh stops growing with the age of the install.
    """
    p = log_path()
    if not os.path.exists(p):
        return []
    rows = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            try:
                if os.path.getsize(p) > MAX_READ_BYTES:
                    f.seek(os.path.getsize(p) - MAX_READ_BYTES)
                    f.readline()      # drop the partial line the seek landed in
            except OSError:
                pass
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


def spans(rows=None, now=None):
    """Fold the event stream into recording spans - the ribbon's whole model.

    7b: "Write the log first. The ribbon is only a rendering of
    sessions.jsonl." So this is the rendering-independent half: each span is
    one recording, carrying the idle gaps inside it and the marks on it.

        {game, start, end, live, gaps: [(s, e)], marks: [ts], path, size}

    A span with no rec_stop is `live` and ends at `now` - that's the block the
    ribbon glows. A rec_stop with no matching rec_start still produces a span
    (the log can begin mid-recording, e.g. after a crash); it just starts at
    the stop minus its recorded duration rather than being thrown away.
    """
    rows = read() if rows is None else rows
    now = time.time() if now is None else now
    out, current = [], None
    for row in sorted(rows, key=lambda r: r.get("ts", 0)):
        kind, ts = row.get("type"), row.get("ts", 0)
        if kind == "rec_start":
            if current:                       # a start with no stop before it
                current["end"] = ts
                out.append(current)
            current = {"game": row.get("game") or "Unknown", "start": ts,
                       "end": None, "live": True, "gaps": [], "marks": [],
                       "path": None, "size": None, "_idle": None}
        elif kind == "rec_stop":
            if current is None:
                duration = float(row.get("duration") or 0)
                current = {"game": row.get("game") or "Unknown",
                           "start": ts - duration, "end": None, "live": True,
                           "gaps": [], "marks": [], "path": None, "size": None,
                           "_idle": None}
            current.update(end=ts, live=False, path=row.get("path"),
                           size=row.get("size"))
            if current["_idle"] is not None:  # idle when the recording ended
                current["gaps"].append((current["_idle"], ts))
                current["_idle"] = None
            out.append(current)
            current = None
        elif kind == "idle_in" and current is not None:
            current["_idle"] = ts
        elif kind == "idle_out" and current is not None:
            if current["_idle"] is not None:
                current["gaps"].append((current["_idle"], ts))
                current["_idle"] = None
        elif kind == "mark" and current is not None:
            current["marks"].append(ts)
    if current is not None:
        current["end"] = now
        if current["_idle"] is not None:
            current["gaps"].append((current["_idle"], now))
        out.append(current)
    for span in out:
        span.pop("_idle", None)
    return out


def span_recorded_seconds(span, now=None, window=None):
    """Seconds OBS actually wrote in this span: its extent minus idle gaps.

    A span's extent is wall clock, and it contains every idle pause inside
    the recording - time when the file is not growing at all. Anything that
    answers "how long did I record" has to take those out, or a session left
    paused over lunch reads back as an hour of footage that does not exist.

    `window` clips the answer to a (start, end) pair - the ribbon needs "of
    this span, how much landed inside today".
    """
    now = time.time() if now is None else now
    start = span.get("start") or 0
    end = span.get("end") or now
    if window:
        start = max(start, window[0])
        end = min(end, window[1])
    seconds = max(0.0, end - start)
    for gap_start, gap_end in span.get("gaps") or ():
        overlap = min(end, gap_end or now) - max(start, gap_start)
        if overlap > 0:
            seconds -= overlap
    return max(0.0, seconds)


def summarise(span_list):
    """"4h 12m recorded · 3 games · 7 marks" - the ribbon's header line.

    Idle gaps come out: this line used to read the span's wall-clock extent,
    so it counted every pause as footage.
    """
    recorded = sum(span_recorded_seconds(s) for s in span_list)
    return {"seconds": recorded,
            "games": len({s["game"] for s in span_list}),
            "marks": sum(len(s["marks"]) for s in span_list)}


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
    started = None
    live_gaps = 0.0        # idle time inside the recording still in progress
    idle_since = None
    kept_by_path = {}
    kept_anon = []
    culled_paths = set()
    for row in rows:
        kind = row.get("type")
        if kind == "rec_start":
            started = row.get("ts")
            live_gaps = 0.0
            idle_since = None
        elif kind == "rec_stop":
            started = None
            live_gaps = 0.0
            idle_since = None
            path = (row.get("path") or "").strip()
            if row.get("culled"):
                if path:
                    if path in culled_paths:
                        continue
                    culled_paths.add(path)
                culled += 1
                # A culled clip still records time: the Recorded tile answers
                # "how long did OBS write today", not "how much survived".
                # Bytes stay kept-only so storage figures never double-count.
                recorded += float(row.get("duration") or 0)
                continue
            if path:
                kept_by_path[path] = row  # last wins — later stop often has duration
            else:
                kept_anon.append(row)
        elif kind == "idle_in":
            idle_pauses += 1
            if started is not None and idle_since is None:
                idle_since = row.get("ts")
        elif kind == "idle_out":
            if idle_since is not None:
                live_gaps += max(0.0, float(row.get("ts") or 0) - idle_since)
                idle_since = None
    for row in list(kept_by_path.values()) + kept_anon:
        clips += 1
        recorded += float(row.get("duration") or 0)
        bytes_written += int(row.get("size") or 0)
    # A recording still in progress counts too. Without this the Recorded tile
    # read "0m today" beside "2 clips · 7.3 GB" an hour into a session, because
    # the duration only lands on rec_stop - which looked like a broken tile
    # rather than the honest "nothing has *finished* today".
    if started:
        now = time.time()
        live = now - started - live_gaps
        if idle_since is not None:   # still paused right now
            live -= max(0.0, now - idle_since)
        recorded += max(0.0, live)
    return {"clips": clips, "recorded_seconds": recorded, "bytes": bytes_written,
            "culled": culled, "idle_pauses": idle_pauses}
