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
        return False
    return box[0]
