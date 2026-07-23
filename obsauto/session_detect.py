"""Detect whether a streaming/session app currently has a live session, so
recording can pause when the session drops (e.g. you disconnect a Moonlight
stream) and resume when it comes back - not just when the app process opens
and closes.

Moonlight has no API or status endpoint, but it writes a per-launch log to
%TEMP%\\Moonlight-*.log with a clean, reliable pair of markers around every
session:
    "Starting video stream..."   -> a stream became live
    "Stopping video stream..."    -> the stream ended (disconnect, the
                                     Ctrl+Alt+Shift+Q quit combo, network
                                     drop, or the host closing it)
So the session is live iff the *last* of those two markers in the newest
Moonlight log is a "Starting". A reconnect writes a fresh "Starting", which
is exactly the resume signal - no ambiguity about whether you're back.
"""

import glob
import os
import tempfile

MOONLIGHT_LOG_GLOB = os.path.join(tempfile.gettempdir(), "Moonlight-*.log")
_START_MARKER = "Starting video stream"
_STOP_MARKER = "Stopping video stream"


def _newest_moonlight_log():
    logs = glob.glob(MOONLIGHT_LOG_GLOB)
    if not logs:
        return None
    try:
        return max(logs, key=os.path.getmtime)
    except OSError:
        return None


def moonlight_session_active():
    """Return True if a Moonlight stream is currently live, False if it isn't,
    or None if it can't be determined (no log / unreadable). Callers treat
    None as "assume active" so we never silently miss a recording."""
    path = _newest_moonlight_log()
    if not path:
        return None
    try:
        # Reading a file Moonlight has open for append works fine on Windows
        # (it opens the log with shared-read). Whole-file read is cheap - even
        # a multi-hour log is only a few hundred KB - and, unlike a tail read,
        # it can't miss a "Starting" that happened long ago in a still-live
        # session with no intervening "Stopping".
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError:
        return None

    last_start = text.rfind(_START_MARKER)
    last_stop = text.rfind(_STOP_MARKER)
    if last_start == -1 and last_stop == -1:
        return False  # log exists but no session has started yet
    return last_start > last_stop
