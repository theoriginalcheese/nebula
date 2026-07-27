"""Storage forecast - spec 7c.

    "Replaces the rail's bare percentage bar. States a date, not a ratio, and
     offers the two moves that change it. Every number here is derived from
     data Nebula already has - file sizes on disk and the session log from 7b."

The spec gives the arithmetic and says "implement exactly", so it is here in
one place, pure and unit-testable, with the UI reading the result:

    GB per hour   bytes written / hours recorded, last 14d
    Hours per day mean over days WITH activity, not all 14
    Days left     free_bytes / (gb_per_hour × h_per_day)

The "days WITH activity" detail is the one that matters. Averaging over all
fourteen days would quietly halve the rate for anyone who plays at weekends,
and a forecast that says twelve days when it means five is worse than no
forecast at all.
"""

import os
import time

from . import session_log

WINDOW_DAYS = 14
MIN_HISTORY_DAYS = 3          # "Forecast needs 3 days of history"
PROJECTION_DAYS = 7           # "Projected bar: next 7 days of growth"
GB = 1024 ** 3

DEFAULTS = {
    "cull_after_days": 30,        # 0 = off
    "cull_keep_marked": True,
    "cull_auto": False,           # ask first
    "offload_when_idle_only": True,
    "disk_warn_days": 3,          # toast threshold
    "disk_block_below_gb": 20,    # refuse to start below this
}


def _day(ts):
    t = time.localtime(ts)
    return (t.tm_year, t.tm_mon, t.tm_mday)


def rates(spans=None, now=None, window_days=WINDOW_DAYS):
    """GB/hour and hours/day over the trailing window.

    Returns {gb_per_hour, hours_per_day, days_with_activity, bytes, hours}.
    Any of the rates can be None, which means "not enough to say" - never 0,
    because zero is a claim and this doesn't have one to make.
    """
    now = time.time() if now is None else now
    spans = session_log.spans() if spans is None else spans
    cutoff = now - window_days * 86400

    total_bytes = 0
    total_hours = 0.0
    per_day = {}
    for span in spans:
        end = span.get("end") or now
        if end < cutoff:
            continue
        seconds = max(0.0, end - span["start"])
        # Idle gaps are paused time: the file isn't growing, so counting them
        # would understate GB/h and overstate how long the disk lasts.
        for gap_start, gap_end in span.get("gaps", ()):
            seconds -= max(0.0, (gap_end or end) - gap_start)
        seconds = max(0.0, seconds)
        hours = seconds / 3600.0
        total_hours += hours
        if span.get("size"):
            total_bytes += int(span["size"])
        per_day.setdefault(_day(span["start"]), 0.0)
        per_day[_day(span["start"])] += hours

    active_days = [h for h in per_day.values() if h > 0]
    gb_per_hour = (total_bytes / GB / total_hours) if total_hours > 0 and total_bytes else None
    hours_per_day = (sum(active_days) / len(active_days)) if active_days else None
    return {"gb_per_hour": gb_per_hour, "hours_per_day": hours_per_day,
            "days_with_activity": len(active_days),
            "bytes": total_bytes, "hours": total_hours}


def forecast(free_bytes, total_bytes=None, spans=None, now=None):
    """The whole card's numbers, or a reason there aren't any yet.

    `ready` is False until there are three days of activity - the spec shows a
    distinct "not enough history" state rather than a wild first-day guess.
    """
    now = time.time() if now is None else now
    stats = rates(spans, now=now)
    out = {
        "free": free_bytes,
        "total": total_bytes,
        "used": (total_bytes - free_bytes) if total_bytes else None,
        "gb_per_hour": stats["gb_per_hour"],
        "hours_per_day": stats["hours_per_day"],
        "days_with_activity": stats["days_with_activity"],
        "days_needed": max(0, MIN_HISTORY_DAYS - stats["days_with_activity"]),
        "ready": False,
        "days_left": None,
        "full_on": None,
        "projected_bytes": None,
    }
    if (stats["days_with_activity"] < MIN_HISTORY_DAYS
            or not stats["gb_per_hour"] or not stats["hours_per_day"]):
        return out

    per_day_bytes = stats["gb_per_hour"] * stats["hours_per_day"] * GB
    if per_day_bytes <= 0:
        return out
    out["ready"] = True
    out["days_left"] = free_bytes / per_day_bytes
    out["full_on"] = now + out["days_left"] * 86400
    out["projected_bytes"] = min(free_bytes, per_day_bytes * PROJECTION_DAYS)
    return out


def days_left_label(days):
    """"Rounding: <1d shows hours · >60d shows '60+ days'"."""
    if days is None:
        return ""
    if days < 1:
        hours = max(1, int(round(days * 24)))
        return f"{hours} hour" + ("" if hours == 1 else "s")
    if days > 60:
        return "60+ days"
    whole = int(round(days))
    return f"{whole} day" + ("" if whole == 1 else "s")


def full_on_label(when):
    if not when:
        return ""
    return time.strftime("%a %d %b", time.localtime(when))


def cull_candidates(recording_root, older_than_days, keep_marked=True,
                    marked_paths=(), now=None):
    """Files a cull would take: "sum of unmarked files older than N days".

    Replays are always excluded, marked clips too when keep_marked is on. The
    caller shows the count and the total before anything is touched - the spec
    requires it, and so does obs-footage-sacred.
    """
    now = time.time() if now is None else now
    if not older_than_days or not recording_root or not os.path.isdir(recording_root):
        return {"files": [], "count": 0, "bytes": 0}
    cutoff = now - older_than_days * 86400
    marked = {os.path.normcase(os.path.abspath(p)) for p in marked_paths}
    found, total = [], 0
    for folder, dirs, names in os.walk(recording_root):
        # Never the thumbnail cache, and never a Replays folder: "always
        # exclude marked clips and replays".
        dirs[:] = [d for d in dirs if d not in (".nebula", "Replays")]
        for name in names:
            if not name.lower().endswith((".mkv", ".mp4", ".flv", ".mov")):
                continue
            path = os.path.join(folder, name)
            if keep_marked and os.path.normcase(os.path.abspath(path)) in marked:
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            if stat.st_mtime >= cutoff:
                continue
            found.append(path)
            total += stat.st_size
    return {"files": found, "count": len(found), "bytes": total}


def cull_gain_days(freed_bytes, gb_per_hour, hours_per_day):
    """How much longer the disk lasts if `freed_bytes` came back - the "+46d"."""
    if not freed_bytes or not gb_per_hour or not hours_per_day:
        return None
    per_day = gb_per_hour * hours_per_day * GB
    return (freed_bytes / per_day) if per_day > 0 else None
