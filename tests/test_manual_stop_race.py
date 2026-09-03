"""Races between the monitor worker loop and UI-thread record actions.

Two defects this locks down:

  1. A manual Stop landing while an auto-apply is seconds into its
     stop-then-start used to lose: the start completed anyway and the user's
     recording came straight back. The apply must notice the stop (epoch
     bump) at its point of no return and abort honestly.
  2. The toast "Record" button and a poll tick could both enter the OBS
     start path concurrently - double-start, then _recording_target=None
     while OBS records. All transitions now serialise on one lock, and
     Accept never blocks the UI thread waiting for it.

    python tests/test_manual_stop_race.py
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.monitor import Monitor

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class FakeOBS:
    def __init__(self):
        self.connected = True
        self.recording = False
        self.starts = 0
        self.stops = 0
        self.start_times = []

    def is_recording(self):
        return self.recording

    def get_version(self):
        # The loop asks this every tick to tell "OBS is up" from "OBS is up
        # but not accepting requests yet" (websocket 207).
        return "30.2.3"

    def get_record_status(self):
        # _stop_current_recording reads this for outputDuration: the length
        # OBS actually wrote, which is what the cull and the log go by.
        return {"outputActive": self.recording, "outputPaused": False,
                "outputDuration": 600_000, "outputBytes": 1}

    def stop_record(self):
        self.stops += 1
        self.recording = False
        return {"outputPath": None}

    def start_record(self):
        self.starts += 1
        self.recording = True
        self.start_times.append(time.time())

    def set_record_directory(self, path):
        pass


class FakeClassifier:
    def is_game(self, *a, **k):
        return True


config = {
    "poll_interval_seconds": 1,
    "idle_timeout_seconds": 9999,
    "min_clip_seconds": 0,
    "reconnect_interval_seconds": 10,
    "holdoff_same_game_seconds": 60,
    "keep_alive_audio_processes": [],
    "recording_root": os.environ.get("TEMP", "."),
    "obs_path": "",
}

obs = FakeOBS()
logs = []
mon = Monitor(obs, FakeClassifier(), config, on_log=logs.append)
mon._retarget_game_capture = lambda *a, **k: None
mon._output_active = lambda: False

target_a = (111, "gamea.exe", "Game A",
            os.path.join(config["recording_root"], "GameA"))
target_b = (222, "gameb.exe", "Game B",
            os.path.join(config["recording_root"], "GameB"))

# ---- 1. manual Stop lands mid-apply -> abort, never start ----
real_stop_current = mon._stop_current_recording


def slow_stop_then_user_clicks(prev_name):
    time.sleep(0.15)
    # The user hits Stop while the auto-apply is mid-transition.
    mon.note_manual_stop("gamea.exe", "Game A")
    return True  # the old recording did stop


mon._stop_current_recording = slow_stop_then_user_clicks
obs.recording = False
mon._recording_target = None
mon._apply_target(target_a)
check("mid-apply stop: OBS never started", obs.starts == 0, obs.starts)
check("mid-apply stop: target stays None", mon._recording_target is None,
      mon._recording_target)
check("mid-apply stop: abort is logged",
      any("aborted" in m.lower() for m in logs),
      logs[-1] if logs else "")

# ---- 2. Accept never blocks the UI thread on a busy transition ----
logs.clear()


def hold_lock_a_while():
    holder = threading.Thread(target=lambda: (
        mon._obs_lock.acquire(),
        time.sleep(0.8),
        mon._obs_lock.release()), daemon=True)
    holder.start()
    time.sleep(0.15)  # let the holder take the lock


mon._stop_current_recording = real_stop_current
mon.note_manual_stop("gamea.exe", "Game A")
mon._hold_off_pending = target_a
t0 = time.time()
hold_lock_a_while()
ok = mon.accept_record_prompt()
blocked = time.time() - t0
check("accept while busy: refuses fast", ok is False and blocked < 0.7,
      f"{blocked:.2f}s ok={ok}")
check("accept while busy: nothing started", obs.starts == 0, obs.starts)
check("accept while busy: prompt stays pending",
      mon._hold_off_pending == target_a, mon._hold_off_pending)

holder_join_deadline = time.time() + 3
while time.time() < holder_join_deadline:
    # RLock has no locked(); a non-blocking acquire doubles as the probe.
    if not mon._obs_lock.acquire(blocking=False):
        time.sleep(0.05)
        continue
    mon._obs_lock.release()
    break

# Once the transition clears, the same prompt still works.
ok = mon.accept_record_prompt()
check("accept after busy: starts", ok is True and obs.starts == 1,
      f"starts={obs.starts} ok={ok}")
check("accept after busy: state tracks OBS",
      mon._recording_target == target_a, mon._recording_target)

# ---- 3. two appliers never overlap inside the transition ----
logs.clear()
mon.clear_hold_off()
mon._recording_target = None
obs.recording = False
concurrent = {"now": 0, "max": 0}
conc_lock = threading.Lock()


def slow_real_stop(prev_name):
    with conc_lock:
        concurrent["now"] += 1
        concurrent["max"] = max(concurrent["max"], concurrent["now"])
    time.sleep(0.25)
    with conc_lock:
        concurrent["now"] -= 1
    return True


mon._stop_current_recording = slow_real_stop
starts_before_overlap = obs.starts
t1 = threading.Thread(target=lambda: mon._apply_target(target_a), daemon=True)
t1.start()
time.sleep(0.08)
mon._apply_target(target_b)
t1.join(timeout=10)
check("overlapping applies: never concurrent", concurrent["max"] == 1,
      concurrent)
check("overlapping applies: last target wins", 
      mon._recording_target == target_b, mon._recording_target)
# slow_real_stop pretends the stop happened without touching the fake OBS,
# so "sane" here = both applies started exactly once each, in order.
check("overlapping applies: OBS sane",
      obs.recording and obs.starts - starts_before_overlap == 2,
      f"recording={obs.recording} starts={obs.starts}")

# Monitoring off has the same race a manual stop has: the loop thread can be
# holding a target it already decided to record. note_manual_stop() always
# invalidated it through _stop_epoch; stop() did not, so a recording could be
# started by a Monitor that had just been torn down - and nothing left alive
# would ever stop it.
epoch_before = mon._stop_epoch
mon.stop()
check("stop() invalidates an in-flight apply", mon._stop_epoch > epoch_before,
      f"{epoch_before} -> {mon._stop_epoch}")

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
