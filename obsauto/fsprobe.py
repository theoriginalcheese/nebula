"""Bounded filesystem probes.

``os.path.isdir`` on a dead mapped drive or SMB UNC commonly blocks 20–60s
(Windows waiting on the redirector). The v4 snapshot runs on the JS-bridge
thread, so an unbounded probe freezes the whole UI — including Retry.

Callers that must not stall (snapshot, path pick, reachability cache) use
``isdir_within``. Live copy/verify on the offload worker may still want a
longer budget; pass ``timeout`` explicitly.
"""
from __future__ import annotations

import os
import threading
import time

# A dead redirector holds each probe's worker thread for the OS timeout long
# after we stopped waiting. Polling callers (snapshot reachability) would
# stack one stuck thread per tick - remember "not a dir" verdicts briefly so
# a dead path costs at most one thread per TTL window instead of per call.
_NEG_TTL_S = 10.0
_neg_until: dict[str, float] = {}
_neg_lock = threading.Lock()


def _key(path):
    return os.path.normcase(os.path.normpath(path))


def isdir_within(path, timeout=2.0):
    """``os.path.isdir`` but False if it has not returned within ``timeout``."""
    path = (path or "").strip()
    if not path:
        return False
    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        timeout = 2.0
    if timeout <= 0:
        timeout = 2.0

    key = _key(path)
    now = time.monotonic()
    with _neg_lock:
        until = _neg_until.get(key)
        if until is not None and now < until:
            return False

    box = []

    def check():
        try:
            box.append(bool(os.path.isdir(path)))
        except OSError:
            box.append(False)

    worker = threading.Thread(target=check, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive() or not box:
        with _neg_lock:
            _neg_until[key] = time.monotonic() + _NEG_TTL_S
        return False
    ok = box[0]
    if not ok:
        with _neg_lock:
            _neg_until[key] = time.monotonic() + _NEG_TTL_S
    return ok
