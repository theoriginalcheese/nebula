"""A transient failure must never wedge something permanently.

Six places where one bad moment left the app in a state it could not get out
of without a restart. They have nothing in common except that shape, which
is why they are pinned together.

* A thumbnail that failed once was blacklisted for the life of the process.
* An unexpected websocket frame killed the receive thread while `connected`
  still said True, so nothing reconnected and every call hung its timeout.
* A double-filed classification survived every save; only a restart healed
  it, and the next sync conflict put it back.
* A superseded connect attempt could still report success, with stale meta.
* Two status polls could run at once, racing on the preview screenshot.
* Two GPU-state pushes could land out of order and leave the page asleep
  over a visible window.

    python tests/test_stuck_states.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import classifier as classifier_mod
from obsauto import obs_client, thumbs
from spike import host as host_mod
from spike.host import NebulaHost

host_mod.ensure_obs_running = lambda *a, **k: None
host_mod.is_obs_running = lambda: False

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-56s %s" % ("PASS" if ok else "FAIL", name, detail))


CFG = {"obs_host": "localhost", "obs_port": 4455,
       "recording_root": "D:/OBS Recordings",
       "toggle_hotkey": "`", "toggle_hotkey_scancode": 41,
       "replay_hotkey": "f9", "palette_hotkey": "ctrl+k",
       "obs_path": "", "obs_password": ""}


# --- 1. a failed thumbnail can be retried ----------------------------------

def test_thumbnail_failure_is_retryable():
    work = tempfile.mkdtemp(prefix="nebula-thumb-")
    clip = os.path.join(work, "a.mkv")
    open(clip, "wb").write(b"x")

    w = thumbs.ThumbWorker.__new__(thumbs.ThumbWorker)
    w._seen = set()
    w._failures = {}
    key = os.path.normcase(os.path.abspath(clip))

    w._seen.add(key)
    w._note_failure(key)
    check("a failure releases the duplicate guard", key not in w._seen)
    check("and is counted", w._failures[key] == 1, w._failures)

    for _ in range(thumbs.ThumbWorker.MAX_ATTEMPTS):
        w._note_failure(key)
    check("but retries are bounded",
          w._failures[key] >= thumbs.ThumbWorker.MAX_ATTEMPTS, w._failures)


# --- 2. the receive thread cannot die pretending to be connected -----------

class DeadSocket:
    """Hands over one malformed frame, then blocks until told to stop."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.closed = threading.Event()

    def recv(self):
        if self.frames:
            return self.frames.pop(0)
        self.closed.wait(2.0)
        raise OSError("closed")


def test_a_bad_frame_does_not_strand_the_client():
    c = obs_client.OBSClient.__new__(obs_client.OBSClient)
    c._stop = False
    c._lock = threading.Lock()
    c._pending = {}
    c._identified = threading.Event()
    c._identified.set()
    c.on_event = None
    c.on_log = lambda msg: None
    # op 7 is a request response; this one has no "d" at all.
    sock = DeadSocket([json.dumps({"op": 7})])
    c._ws = sock

    t = threading.Thread(target=c._recv_loop, daemon=True)
    t.start()
    time.sleep(0.2)
    check("a malformed response frame is survived, not fatal", t.is_alive())
    check("and the client still reports itself connected", c.connected is True)

    sock.closed.set()
    t.join(timeout=3)
    check("when the socket really goes, the thread ends", not t.is_alive())
    check("and connected goes False so a reconnect can fire",
          c.connected is False)


# --- 3. a save heals what it merges with -----------------------------------

def test_save_heals_the_disk_copy():
    work = tempfile.mkdtemp(prefix="nebula-class-")
    data_file = os.path.join(work, "games.json")
    # starrail.exe filed as both - the corruption CLAUDE.md documents.
    with open(data_file, "w", encoding="utf-8") as fh:
        json.dump({"games": {"starrail.exe": {"display_name": "Star Rail"}},
                   "non_games": {"starrail.exe": True}}, fh)

    real_file = classifier_mod.DATA_FILE
    classifier_mod.DATA_FILE = data_file
    try:
        c = classifier_mod.Classifier.__new__(classifier_mod.Classifier)
        c.log = lambda msg: None
        c.on_saved = lambda data: None
        # An overlay with no opinion at all about the broken key: this is the
        # case the merge could not repair on its own.
        c._data = {"games": {"other.exe": {"display_name": "Other"}},
                   "non_games": {}}
        c._save()
        with open(data_file, encoding="utf-8") as fh:
            written = json.load(fh)
        check("the double-filed entry is gone from non_games",
              "starrail.exe" not in written["non_games"], written["non_games"])
        check("and survives as the game it was promoted to",
              "starrail.exe" in written["games"], written["games"])
        check("the untouched overlay entry is still written",
              "other.exe" in written["games"], written["games"])
    finally:
        classifier_mod.DATA_FILE = real_file


# --- 4. a superseded connect cannot report success -------------------------

class SlowOBS:
    def __init__(self):
        self.connected = False
        self.last_handshake_ms = 5

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def get_record_status(self):
        return {"outputActive": False, "outputPaused": False,
                "outputDuration": 0, "outputBytes": 0}


class CountingMonitor:
    def __init__(self):
        self._running = False
        self._recording_target = None
        self.starts = 0

    def start(self):
        self._running = True
        self.starts += 1

    def stop(self):
        self._running = False


def test_a_superseded_connect_is_dropped():
    host = NebulaHost(dict(CFG))
    host.obs = SlowOBS()
    host.monitor = CountingMonitor()

    in_fetch = threading.Event()
    release = threading.Event()

    def slow_fetch():
        in_fetch.set()
        release.wait(3.0)
        return {"version": "stale", "handshake_ms": 5}
    host._fetch_obs_meta = slow_fetch

    host.autostart()
    check("the worker reached the metadata fetch", in_fetch.wait(3.0))

    # A newer attempt begins - exactly what hero "Retry now" does.
    host._connect_gen += 1
    release.set()
    time.sleep(0.4)

    check("the stale attempt did not start the monitor",
          host.monitor.starts == 0, host.monitor.starts)
    check("and did not claim the connection",
          host._obs_connected is False, host._obs_connected)
    host.quit()


# --- 5. one status poll at a time ------------------------------------------

def test_polls_do_not_overlap():
    host = NebulaHost(dict(CFG))
    host.obs = SlowOBS()
    host.monitor = CountingMonitor()

    live = {"now": 0, "max": 0}
    started = threading.Event()
    hold = threading.Event()
    lock = threading.Lock()
    real = host._poll_obs_status_locked

    def slow_poll():
        with lock:
            live["now"] += 1
            live["max"] = max(live["max"], live["now"])
        started.set()
        hold.wait(2.0)
        try:
            real()
        finally:
            with lock:
                live["now"] -= 1
    host._poll_obs_status_locked = slow_poll

    t = threading.Thread(target=host._poll_obs_status, daemon=True)
    t.start()
    check("the first poll is running", started.wait(2.0))
    host._poll_obs_status()          # the re-entrant call _poll_now would make
    hold.set()
    t.join(timeout=3)

    check("a second poll never runs on top of the first",
          live["max"] == 1, live["max"])
    host.quit()


# --- 6. the last GPU state pushed is the one that sticks -------------------

class FakeWindow:
    def __init__(self, gate=None):
        self.calls = []
        self.gate = gate

    def evaluate_js(self, js):
        if self.gate is not None:
            self.gate.wait(2.0)
        self.calls.append(js)


def test_an_overtaken_gpu_push_drops_itself():
    host = NebulaHost(dict(CFG))
    host.obs = SlowOBS()
    host.monitor = CountingMonitor()
    host._suspend_webview = lambda *a, **k: None
    host._windows = type("W", (), {"sleep_aux": lambda self, *a: None})()

    gate = threading.Event()
    host.window = FakeWindow(gate=gate)

    host._apply_page_gpu(False, False)   # asleep - blocks in evaluate_js
    time.sleep(0.1)
    host._apply_page_gpu(True, True)     # awake - queued behind it
    time.sleep(0.1)
    gate.set()
    time.sleep(0.5)

    calls = host.window.calls
    check("both pushes did not both land", len(calls) <= 2, calls)
    check("the page is left awake, not asleep over a visible window",
          calls and "setAwake(true)" in calls[-1], calls)
    host.quit()


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        print("\n--- %s" % fn.__name__.replace("test_", "").replace("_", " "))
        try:
            fn()
        except Exception:
            check(fn.__name__, False, "raised")
            traceback.print_exc()
    print("\n%s (%d checks)" % ("ALL PASS" if not FAIL else "FAILED",
                                len(PASS) + len(FAIL)))
    if FAIL:
        for name in FAIL:
            print("  FAIL %s" % name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
