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


def _moonlight_process_alive():
    """True if a Moonlight.exe process currently exists. False (not None)
    on any failure - this is only used to narrow an existing "live" verdict,
    never to grant one, so failing closed here is the safe direction."""
    try:
        from . import moonlight
        return bool(moonlight._moonlight_pids())
    except Exception:
        return False


def _moonlight_window_alive():
    """True if a Moonlight stream-surface window currently exists."""
    try:
        from . import moonlight
        return bool(moonlight._stream_window_present())
    except Exception:
        return False


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
    live = last_start > last_stop

    # The log can only say what Moonlight chose to write, and a crash / GPU
    # reset / network drop can kill the stream window without ever writing
    # "Stopping video stream...". If the process is confirmed still running
    # but has no stream window left, the log's stale "Starting" must not
    # keep reading as live forever. Only narrows True -> False: when the
    # process state can't be determined at all, this defers to the log
    # exactly as before (fails toward "assume active", per the module's own
    # rule above).
    if live and _moonlight_process_alive() and not _moonlight_window_alive():
        return False
    return live
