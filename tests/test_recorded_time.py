"""Recorded time means what OBS wrote, not how long the window was open.

Every "hours recorded" figure in the app used to be wall clock from
rec_start to rec_stop, which counts idle pauses as footage. With the idle
timeout set in minutes that is not a rounding error: a session that recorded
six seconds and then sat paused for six minutes logged as six minutes.

The same number decides whether the short-clip cull fires, so the two bugs
were one bug - a clip could sit under the threshold and never be culled
because the pause after it made the wall clock long.

Pinned here:

* `session_log.span_recorded_seconds` subtracts idle gaps, and can be
  clipped to a window (the ribbon needs "how much of this landed today").
* `summarise()` and `today()` both use recorded time, live spans included.
* `Monitor` logs OBS's own outputDuration, and culls on it.
* A cull goes to the Recycle Bin, and a file that could not be recycled is
  not reported as culled.
* `recycle.recyclable()` refuses network paths, which have no Recycle Bin.

    python tests/test_recorded_time.py
"""
from __future__ import annotations

import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import monitor as mon
from obsauto import recycle, session_log

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-54s %s" % ("PASS" if ok else "FAIL", name, detail))


# --- the shared helper ------------------------------------------------------

def test_span_recorded_seconds():
    span = {"start": 1000.0, "end": 2000.0, "gaps": [(1200.0, 1500.0)]}
    check("extent minus one gap",
          session_log.span_recorded_seconds(span) == 700.0,
          session_log.span_recorded_seconds(span))

    two = {"start": 0.0, "end": 100.0, "gaps": [(10.0, 20.0), (50.0, 60.0)]}
    check("gaps accumulate", session_log.span_recorded_seconds(two) == 80.0)

    nogaps = {"start": 0.0, "end": 100.0, "gaps": []}
    check("no gaps is just the extent",
          session_log.span_recorded_seconds(nogaps) == 100.0)

    live = {"start": 0.0, "end": None, "gaps": []}
    check("a live span runs to now",
          session_log.span_recorded_seconds(live, now=42.0) == 42.0)

    open_gap = {"start": 0.0, "end": None, "gaps": [(30.0, None)]}
    check("a gap still open runs to now too",
          session_log.span_recorded_seconds(open_gap, now=100.0) == 30.0,
          session_log.span_recorded_seconds(open_gap, now=100.0))

    # The ribbon asks "of this span, how much was inside today".
    check("a window clips the answer",
          session_log.span_recorded_seconds(
              two, window=(0.0, 30.0)) == 20.0,
          session_log.span_recorded_seconds(two, window=(0.0, 30.0)))
    check("a gap outside the window doesn't subtract twice",
          session_log.span_recorded_seconds(
              two, window=(60.0, 100.0)) == 40.0,
          session_log.span_recorded_seconds(two, window=(60.0, 100.0)))

    check("never negative",
          session_log.span_recorded_seconds(
              {"start": 0.0, "end": 10.0, "gaps": [(0.0, 999.0)]}) == 0.0)


def test_summarise_excludes_pauses():
    spans = [
        {"game": "A", "start": 0.0, "end": 3600.0, "gaps": [(600.0, 1200.0)],
         "marks": []},
        {"game": "B", "start": 4000.0, "end": 4600.0, "gaps": [], "marks": []},
    ]
    got = session_log.summarise(spans)["seconds"]
    check("the ribbon header drops paused time", got == 3600.0, got)


# --- today() ---------------------------------------------------------------

_LOG = {"path": None}


def _fresh_log(tmp):
    """Point session_log at a scratch file - never the real sessions.jsonl."""
    _LOG["path"] = os.path.join(tmp, "sessions.jsonl")
    session_log.log_path = lambda: _LOG["path"]
    if os.path.exists(_LOG["path"]):
        os.remove(_LOG["path"])


def _write(rows):
    import json
    with open(_LOG["path"], "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_today_live_span_excludes_idle():
    import tempfile
    tmp = tempfile.mkdtemp(prefix="nebula-time-")
    _fresh_log(tmp)
    now = time.time()
    start = max(session_log.day_start() + 1, now - 3600)
    _write([
        {"type": "rec_start", "ts": start, "game": "G"},
        {"type": "idle_in", "ts": start + 600},
        {"type": "idle_out", "ts": start + 1200},
    ])
    got = session_log.today()["recorded_seconds"]
    want = (now - start) - 600
    check("a live span's pause is not counted", abs(got - want) < 2.0,
          "%.0f vs %.0f" % (got, want))

    _write([
        {"type": "rec_start", "ts": start, "game": "G"},
        {"type": "idle_in", "ts": start + 600},
    ])
    got = session_log.today()["recorded_seconds"]
    check("time paused right now stops accruing", abs(got - 600.0) < 2.0, got)

    _write([
        {"type": "rec_start", "ts": start, "game": "G"},
        {"type": "idle_in", "ts": start + 60},
        {"type": "idle_out", "ts": start + 120},
        {"type": "rec_stop", "ts": start + 300, "game": "G",
         "path": "a.mkv", "duration": 240, "size": 10},
    ])
    got = session_log.today()["recorded_seconds"]
    check("a finished span uses its logged duration", got == 240.0, got)


# --- Monitor: duration and the cull ----------------------------------------

class StopOBS:
    """Just enough OBS to drive _stop_current_recording."""

    def __init__(self, duration_ms, path):
        self.connected = True
        self.duration_ms = duration_ms
        self.path = path
        self.stopped = 0

    def get_record_status(self):
        return {"outputActive": True, "outputPaused": False,
                "outputDuration": self.duration_ms, "outputBytes": 1}

    def stop_record(self):
        self.stopped += 1
        return {"outputPath": self.path}


def _stub_monitor(obs, min_clip, started_at):
    m = mon.Monitor.__new__(mon.Monitor)
    m.obs = obs
    m.config = {"min_clip_seconds": min_clip}
    m.on_notify = lambda *a, **k: None
    m.on_log = lambda msg: None
    m.offloader = None
    m._recording_started_at = started_at
    m._auto_paused = False
    m._auto_pause_reason = None
    m.logged = []
    m.log = m.logged.append
    return m


def _capture_stops(tmp):
    _fresh_log(tmp)
    rows = []
    real = session_log.append

    def fake(kind, **kw):
        rows.append(dict(kw, type=kind))
    session_log.append = fake
    return rows, real


def test_duration_is_obs_not_wall_clock():
    import tempfile
    tmp = tempfile.mkdtemp(prefix="nebula-dur-")
    clip = os.path.join(tmp, "clip.mkv")
    open(clip, "wb").write(b"x" * 4096)

    rows, real_append = _capture_stops(tmp)
    recycled = []
    real_recycle = mon.to_recycle_bin
    mon.to_recycle_bin = lambda p: recycled.append(p)
    try:
        # Recorded 6s, then sat paused: started 400 seconds ago by the clock.
        obs = StopOBS(duration_ms=6000, path=clip)
        m = _stub_monitor(obs, min_clip=15, started_at=time.time() - 400)
        m._stop_current_recording("Some Game")
        stop = rows[-1]
        check("the logged duration is what OBS wrote",
              abs(float(stop["duration"]) - 6.0) < 0.01, stop["duration"])
        check("a 6s clip under a 15s minimum is culled",
              stop.get("culled") is True, stop)
        check("and it went to the Recycle Bin", recycled == [clip], recycled)

        # Same wall clock, but OBS really did write 20 minutes.
        rows.clear()
        recycled.clear()
        obs = StopOBS(duration_ms=1_200_000, path=clip)
        m = _stub_monitor(obs, min_clip=15, started_at=time.time() - 1300)
        m._stop_current_recording("Some Game")
        check("a real session is not culled",
              rows[-1].get("culled") is None, rows[-1])
        check("and nothing was recycled", recycled == [], recycled)
    finally:
        mon.to_recycle_bin = real_recycle
        session_log.append = real_append


def test_wall_clock_is_the_fallback():
    import tempfile
    tmp = tempfile.mkdtemp(prefix="nebula-dur2-")
    clip = os.path.join(tmp, "clip.mkv")
    open(clip, "wb").write(b"x" * 4096)
    rows, real_append = _capture_stops(tmp)
    real_recycle = mon.to_recycle_bin
    mon.to_recycle_bin = lambda p: None
    try:
        obs = StopOBS(duration_ms=None, path=clip)   # OBS didn't say
        m = _stub_monitor(obs, min_clip=15, started_at=time.time() - 90)
        m._stop_current_recording("Some Game")
        check("falls back to wall clock when OBS has no answer",
              85 < float(rows[-1]["duration"]) < 95, rows[-1]["duration"])
    finally:
        mon.to_recycle_bin = real_recycle
        session_log.append = real_append


def test_a_clip_that_survives_is_not_reported_as_culled():
    import tempfile
    tmp = tempfile.mkdtemp(prefix="nebula-dur3-")
    clip = os.path.join(tmp, "clip.mkv")
    open(clip, "wb").write(b"x" * 4096)
    rows, real_append = _capture_stops(tmp)
    real_recycle = mon.to_recycle_bin

    def refuse(path):
        raise recycle.RecycleError("no bin on this volume")
    mon.to_recycle_bin = refuse
    real_sleep = mon.time.sleep
    mon.time.sleep = lambda s: None
    try:
        obs = StopOBS(duration_ms=3000, path=clip)
        m = _stub_monitor(obs, min_clip=15, started_at=time.time() - 3)
        m._stop_current_recording("Some Game")
        check("the file is still there", os.path.exists(clip))
        check("and the log does not claim it was culled",
              rows[-1].get("culled") is None, rows[-1])
        check("the reason is in the activity log",
              any("could not recycle" in line for line in m.logged), m.logged)
    finally:
        mon.time.sleep = real_sleep
        mon.to_recycle_bin = real_recycle
        session_log.append = real_append


# --- the bin itself ---------------------------------------------------------

def test_network_paths_have_no_bin():
    check("a UNC share is not recyclable",
          recycle.recyclable("\\\\192.168.68.59\\50tb\\OBS\\a.mkv") is False)
    check("a mapped network drive is not recyclable",
          recycle.recyclable("Z:\\OBS\\a.mkv") is False)
    check("the local recording root is",
          recycle.recyclable("C:\\Users\\x\\Videos\\a.mkv") is True)

    try:
        recycle.to_recycle_bin("Z:\\OBS\\a.mkv")
    except recycle.RecycleError as exc:
        check("and deleting one is refused rather than done another way",
              "Recycle Bin" in str(exc) or "no such file" in str(exc), exc)
    else:
        check("and deleting one is refused rather than done another way",
              False, "no RecycleError raised")


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
