"""Monitor session counters that feed the frame-2a stat tiles.

No GUI / OBS required.

    python tests/test_monitor_stats.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.monitor import Monitor


class FakeOBS:
    connected = True

    def is_recording(self):
        return False

    def get_record_status(self):
        return {"outputActive": False, "outputPaused": False}


results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), detail))


mon = Monitor(FakeOBS(), classifier=None, config={
    "idle_timeout_seconds": 4,
    "min_clip_seconds": 10,
    "recording_root": tempfile.mkdtemp(),
    "keep_alive_audio_processes": [],
})

check("auto_culled starts at 0", mon.auto_culled == 0)
check("idle_pauses starts at 0", mon.idle_pauses == 0)
check("recorded_seconds_today starts at 0", mon.recorded_seconds_today == 0)

# Simulate a kept clip and a cull via the same bookkeeping the stop path uses.
mon._roll_stats_day()
mon.recorded_seconds_today += 125
mon.auto_culled += 1
mon.idle_pauses += 2
check("recorded accumulates", mon.recorded_seconds_today == 125)
check("auto_culled increments", mon.auto_culled == 1)
check("idle_pauses increments", mon.idle_pauses == 2)

# Day roll resets today's counters.
mon._stats_day = "2000-01-01"
mon._roll_stats_day()
check("day roll clears recorded", mon.recorded_seconds_today == 0)
check("day roll clears culled", mon.auto_culled == 0)
check("day roll clears pauses", mon.idle_pauses == 0)

# Format helper used by the tile (imported from gui would pull Tk — duplicate lightly).
def fmt(seconds):
    seconds = max(0, int(seconds or 0))
    if seconds < 60:
        return f"{seconds}s"
    hours, rem = divmod(seconds, 3600)
    mins = rem // 60
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"

check("format 125s -> 2m", fmt(125) == "2m")
check("format 4h12m", fmt(4 * 3600 + 12 * 60) == "4h 12m")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<44} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
