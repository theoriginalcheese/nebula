"""Smoke the five dial rows, then try to make them do the wrong thing.

No window, no OBS, no footage. The handlers are the real ones.

    python tests/test_dial_actions.py
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spike.dial import DELETE_ROW, DialKnob
from spike.host import NebulaHost

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %s %s" % ("PASS" if ok else "FAIL", name, detail))


class Event:
    def __init__(self, name, scan, kind="down"):
        self.name = name
        self.scan_code = scan
        self.event_type = kind
        self.is_keypad = False


def press(knob, name, scan):
    _allow, action = knob.handle(Event(name, scan, "down"))
    knob.handle(Event(name, scan, "up"))
    return action


class Obs:
    def __init__(self, active=False, paused=False, path="D:/OBS Recordings/game/clip.mkv"):
        self.connected = True
        self.active = active
        self.paused = paused
        self.path = path
        self.calls = []
        self.boom = None

    def get_record_status(self):
        if self.boom == "status":
            raise RuntimeError("socket down")
        return {"outputActive": self.active, "outputPaused": self.paused}

    def stop_record(self):
        self.calls.append("stop")
        if self.boom == "stop":
            raise RuntimeError("stop failed")
        self.active = False
        self.paused = False
        if self.path is None:
            return {}
        return {"outputPath": self.path}

    def start_record(self):
        self.calls.append("start")
        self.active = True

    def pause_record(self):
        self.calls.append("pause")
        self.paused = True

    def resume_record(self):
        self.calls.append("resume")
        self.paused = False

    def accept_record_prompt(self):
        self.calls.append("accept")


class Monitor:
    def __init__(self):
        self._recording_target = ("zenless", "zenlesszonezero.exe", "Zenless Zone Zero")
        self._hold_off = False
        self._hold_off_pending = ("waiting",)
        self.notes = []
        self.log = lambda msg: None

    def note_manual_stop(self, basename=None, display_name=None):
        self.notes.append((basename, display_name))
        self._hold_off = True
        self._hold_off_pending = None

    def accept_record_prompt(self):
        self._hold_off = False

    def clear_hold_off(self):
        self._hold_off = False


class Replay:
    def __init__(self, armed=True):
        self.armed = armed
        self.saves = 0

    def save(self):
        self.saves += 1
        raise RuntimeError("buffer refused")


def host(obs, monitor=None, replay=None):
    box = NebulaHost.__new__(NebulaHost)
    box.obs = obs
    box.monitor = monitor if monitor is not None else Monitor()
    box.replay = replay
    box._transport_busy = False
    box._windows = type("W", (), {"toast_replace": lambda *a, **k: None})()
    box.logs = []
    box._log = box.logs.append
    box._poll_now = lambda: None
    box.shown = 0
    box.show = lambda: setattr(box, "shown", box.shown + 1)
    box._queued = []
    box.call_soon = box._queued.append
    return box


def settle(box):
    """Run the worker the handler just started, then its queued callback."""
    for thread in threading.enumerate():
        if thread is threading.current_thread():
            continue
        if thread.name in ("Thread", "DialDiscard") or thread.daemon:
            if thread.is_alive() and thread.name != "MainThread":
                thread.join(timeout=2)
    queued = list(box._queued)
    box._queued.clear()
    for fn in queued:
        fn()
    return queued


def test_rows_do_their_own_job():
    obs = Obs(active=True, paused=False)
    mon = Monitor()
    box = host(obs, mon)
    box._dial_run(0)
    check("start raises this window", box.shown == 1)

    box._dial_run(1)
    settle(box)
    check("pause pauses a live recording", obs.calls == ["pause"], obs.calls)

    obs.calls.clear()
    obs.paused = True
    box._dial_run(1)
    settle(box)
    check("pause again resumes", obs.calls == ["resume"], obs.calls)

    obs.calls.clear()
    obs.paused = False
    obs.active = True
    box._dial_run(2)
    settle(box)
    check("stop stops", obs.calls == ["stop"], obs.calls)
    check("stop holds off a restart", mon._hold_off is True)
    check("stop does not start", "start" not in obs.calls)

    replay = Replay(armed=True)
    box.replay = replay
    try:
        box._dial_run(3)
    except RuntimeError:
        pass
    check("save replay asks the buffer once", replay.saves == 1)

    box.replay = Replay(armed=False)
    box._dial_run(3)
    check("an unarmed buffer is not saved",
          any("Nothing armed" in line for line in box.logs), box.logs[-1:])


def test_stop_cannot_start():
    obs = Obs(active=False)
    mon = Monitor()
    box = host(obs, mon)
    box._dial_run(2)
    settle(box)
    check("stop while idle never starts", obs.calls == [], obs.calls)
    check("idle stop does not hold the monitor", mon.notes == [])

    obs.active = False
    mon._hold_off = True
    mon._hold_off_pending = ("prompt",)
    box._dial_run(2)
    settle(box)
    check("stop ignores a waiting record prompt",
          "accept" not in obs.calls and "start" not in obs.calls, obs.calls)


def test_stop_holds_off_before_the_ui_catches_up():
    """The monitor can poll in the gap after OBS has stopped and before
    the UI thread hears about it. Hold-off has to be in place by then."""
    obs = Obs(active=True)
    mon = Monitor()
    box = host(obs, mon)
    box._dial_run(2)
    for thread in threading.enumerate():
        if thread is not threading.current_thread() and thread.is_alive():
            thread.join(timeout=2)
    check("hold-off is set before the UI callback",
          mon._hold_off is True and box._queued != [],
          (mon._hold_off, len(box._queued)))
    # A poll in that gap must see the hold and not treat it as a fresh start.
    would_start = not mon._hold_off
    check("a poll in the gap does not start", would_start is False)
    settle(box)
    check("the UI callback does not note the stop twice", len(mon.notes) == 1, mon.notes)


def test_delete_only_the_live_file():
    removed = []
    real_remove = os.remove
    os.remove = lambda path: removed.append(path)
    try:
        obs = Obs(active=False)
        box = host(obs)
        box._dial_run(DELETE_ROW)
        settle(box)
        check("delete while idle does not stop", obs.calls == [], obs.calls)
        check("delete while idle removes nothing", removed == [])

        obs.active = True
        obs.paused = True
        recycled = []

        def recycle(path):
            recycled.append(path)

        import obsauto.recycle as recycle_mod
        old = recycle_mod.to_recycle_bin
        recycle_mod.to_recycle_bin = recycle
        try:
            box._dial_run(DELETE_ROW)
            settle(box)
        finally:
            recycle_mod.to_recycle_bin = old
        check("delete while paused stops first", obs.calls == ["stop"], obs.calls)
        check("delete recycles only the file OBS named",
              recycled == ["D:/OBS Recordings/game/clip.mkv"], recycled)
        check("delete never unlinks", removed == [], removed)
    finally:
        os.remove = real_remove


def test_delete_refuses_the_nasty_cases():
    import obsauto.recycle as recycle_mod

    def boom(path):
        raise AssertionError("recycled %s" % path)

    old = recycle_mod.to_recycle_bin
    recycle_mod.to_recycle_bin = boom
    try:
        obs = Obs(active=True, path=r"\\nas\share\clip.mkv")
        box = host(obs)
        box._dial_run(DELETE_ROW)
        settle(box)
        check("a network path is not recycled",
              any("no Recycle Bin" in line for line in box.logs), box.logs[-1:])
        check("the network stop still holds off", box.monitor._hold_off is True)

        obs = Obs(active=True, path=None)
        box = host(obs)
        box._dial_run(DELETE_ROW)
        settle(box)
        check("a nameless file stays put",
              any("did not name" in line for line in box.logs), box.logs[-1:])

        obs = Obs(active=True)
        obs.boom = "stop"
        box = host(obs)
        box._dial_run(DELETE_ROW)
        settle(box)
        check("a failed stop does not recycle", box._transport_busy is False)
        check("a failed stop is logged",
              any("stop failed" in line for line in box.logs), box.logs[-1:])

        obs = Obs(active=True)
        obs.boom = "status"
        box = host(obs)
        box._dial_run(2)
        settle(box)
        check("a dead socket does not stick the buttons", box._transport_busy is False)
        check("a dead socket did not stop or start", obs.calls == [], obs.calls)

        box = host(Obs(active=True))
        box.obs = None
        box._dial_run(DELETE_ROW)
        check("no OBS means nothing is deleted",
              any("not connected" in line for line in box.logs))

        box = host(Obs(active=True))
        box._transport_busy = True
        box._dial_run(DELETE_ROW)
        check("a busy transport refuses the delete",
              any("did not run" in line for line in box.logs))
        check("busy delete leaves the flag alone", box._transport_busy is True)
    finally:
        recycle_mod.to_recycle_bin = old


def test_second_press_and_a_turned_knob():
    knob = DialKnob()
    press(knob, "volume mute", 57376)
    for _ in range(DELETE_ROW):
        press(knob, "volume up", 57392)
    first = press(knob, "volume mute", 57376)
    check("the first delete press only arms",
          first is not None and first.get("type") == "arm", first)
    turned = press(knob, "volume down", 57390)
    check("turning the knob cancels the confirm",
          turned is not None and turned.get("type") == "move"
          and knob._armed is None, turned)
    landed = press(knob, "volume mute", 57376)
    check("that press runs the row you landed on, not delete",
          landed is not None and landed.get("type") == "activate"
          and landed.get("index") == DELETE_ROW - 1, landed)
    knob.note_closed(landed["token"])
    press(knob, "volume mute", 57376)
    for _ in range(DELETE_ROW):
        press(knob, "volume up", 57392)
    armed_again = press(knob, "volume mute", 57376)
    check("delete has to be armed again",
          armed_again is not None and armed_again.get("type") == "arm")
    second = press(knob, "volume mute", 57376)
    check("the second press is the one that runs",
          second is not None and second.get("type") == "activate")
    check("it runs delete",
          second is not None and second.get("index") == DELETE_ROW)


if __name__ == "__main__":
    test_rows_do_their_own_job()
    test_stop_cannot_start()
    test_stop_holds_off_before_the_ui_catches_up()
    test_delete_only_the_live_file()
    test_delete_refuses_the_nasty_cases()
    test_second_press_and_a_turned_knob()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
