"""OBS readiness helpers — wait_until_ready, stuck recovery triggers.

    python tests/test_obs_ready.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import monitor as mon
from obsauto.obs_client import OBSError, is_not_ready_error

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


class FakeObs:
    def __init__(self, responses):
        self.responses = list(responses)
        self.connected = True
        self.killed = False

    def get_version(self):
        if not self.responses:
            return "30.0.0"
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def wait_until_ready(self, timeout=60.0, interval=0.5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self.get_version()
                return True
            except OBSError as exc:
                if not is_not_ready_error(exc):
                    raise
            time.sleep(interval)
        return False

    def disconnect(self):
        self.connected = False

    def is_recording(self):
        return False

    def connect(self):
        self.connected = True


def test_is_not_ready_error():
    check("detects 207 comment", is_not_ready_error(
        OBSError("SetRecordDirectory failed: OBS is not ready to perform the request.")))
    check("ignores other errors", not is_not_ready_error(
        OBSError("SetRecordDirectory failed: path not writable")))


def test_wait_until_ready_eventually():
    obs = FakeObs([
        OBSError("not ready"),
        OBSError("not ready"),
        "31.1.0",
    ])
    check("waits through not-ready", obs.wait_until_ready(timeout=5, interval=0.01))


def test_monitor_obs_requests_ready_tracks_not_ready():
    m = mon.Monitor(FakeObs([OBSError("not ready")]), None, {})
    check("not ready returns false", m._obs_requests_ready() is False)
    check("timestamp recorded", m._obs_not_ready_since is not None)


def test_monitor_obs_requests_ready_clears():
    obs = FakeObs(["31.0.0"])
    m = mon.Monitor(obs, None, {})
    m._obs_not_ready_since = 1.0
    check("ready clears latch", m._obs_requests_ready() is True)
    check("timestamp cleared", m._obs_not_ready_since is None)


def test_zombie_recovery_threshold():
    obs = FakeObs([OBSError("not ready")])
    m = mon.Monitor(obs, None, {})
    m._obs_was_running_at_start = True
    m._obs_not_ready_since = time.monotonic() - 20
    m._last_obs_recovery_at = 0.0
    m._recover_stuck_obs = lambda: True
    check("zombie triggers recovery", m._maybe_recover_stuck_obs() is True)


if __name__ == "__main__":
    test_is_not_ready_error()
    test_wait_until_ready_eventually()
    test_monitor_obs_requests_ready_tracks_not_ready()
    test_monitor_obs_requests_ready_clears()
    test_zombie_recovery_threshold()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        for name in FAIL:
            print("  FAIL:", name)
        sys.exit(1)
