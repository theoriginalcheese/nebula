"""K762 dial: knob swallow rules, the one pose, and one menu window.

Headless. Does not launch Nebula or OBS.

    python tests/test_dial.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spike import windows as nw
from spike.dial import (
    BG_HOLD_S,
    DELETE_CONFIRM,
    DELETE_ROW,
    POOL,
    ROW_COUNT,
    DialKnob,
    background_for_open,
    close_pose,
    corner_dy,
    dodge_lift,
    open_pose,
    pause_label,
    pick_background,
    status_word,
    toast_clearance,
    unit_ease,
)
from obsauto import hotkey as hotkey_mod

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


class Ev:
    def __init__(self, name, event_type, scan_code, is_keypad=False):
        self.name = name
        self.event_type = event_type
        self.scan_code = scan_code
        self.is_keypad = is_keypad


def down(name, scan):
    return Ev(name, "down", scan)


def up(name, scan):
    return Ev(name, "up", scan)


def test_words():
    check("recording word", status_word("recording") == "Recording")
    check("paused word", status_word("paused") == "Paused")
    check("idle word", status_word("idle") == "Idle")
    check("offline word", status_word("disconnected") == "Offline")
    check("monitoring pause is idle, not Paused",
          status_word("monitoring_paused") == "Idle")
    check("pause label", pause_label(False) == "Pause recording")
    check("resume label", pause_label(True) == "Resume recording")


def test_pose():
    check("ease endpoints", unit_ease(0) == 0 and unit_ease(1) == 1)
    o, y = open_pose(0)
    check("open starts below, hidden", o == 0 and y == 8, (o, y))
    o, y = open_pose(180)
    check("opacity is in at 180ms and the rise is not",
          abs(o - 1) < 1e-6 and y > 0, (o, y))
    o, y = open_pose(220)
    check("open settled at 220ms", abs(o - 1) < 1e-6 and abs(y) < 1e-6, (o, y))
    o, y = open_pose(530)
    check("open does not overshoot", abs(o - 1) < 1e-6 and abs(y) < 1e-6 and y >= 0, (o, y))
    o, y = close_pose(0)
    check("close starts put", o == 1 and y == 0, (o, y))
    o, y = close_pose(200)
    check("close fades and leaves 8px", abs(o) < 1e-6 and abs(y - 8) < 1e-6, (o, y))


def test_dodge():
    check("clearance is the toast plus the margin", toast_clearance(60, 24) == 84)
    check("no toast means the dial stays put", toast_clearance(0, 24) == 0)
    check("dodge starts where it is", dodge_lift(0, 0, 84) == 0)
    mid = dodge_lift(160, 0, 84)
    check("halfway up is between the corner and the gap", 0 < mid < 84, mid)
    check("dodge settles above the toast", dodge_lift(320, 0, 84) == 84)
    check("a late frame does not overshoot", dodge_lift(500, 0, 84) == 84)
    check("the way down settles on the corner", dodge_lift(320, 84, 0) == 0)
    back = dodge_lift(160, 84, 0)
    check("halfway down stays between", 0 < back < 84, back)
    check("the open rise still stacks on the lift",
          corner_dy(8, 84, 1.0) == -76, corner_dy(8, 84, 1.0))
    check("settled lift is the clearance, in physical px",
          corner_dy(0, 84, 1.5) == -126)


def test_hidden_menu_remembers_the_gap():
    host = StubHost()
    ctl = nw.DialController(host)
    ctl.note_toast(84)
    check("a hidden menu takes the gap without a glide",
          ctl._lift == 84 and ctl._lift_target == 84)
    ctl.note_toast(84)
    check("a second toast does not restart the move", ctl._lift == 84)
    ctl.note_toast(0)
    check("once the toast is gone the corner is free again",
          ctl._lift == 0 and ctl._lift_target == 0)


def test_dead_toast_releases_the_corner():
    host = StubHost()
    ctl = nw.DialController(host)
    ctl._lift = 84
    ctl._lift_target = 84
    ctl._reconcile_lift()
    check("no toast means the corner is free",
          ctl._lift == 0 and ctl._lift_target == 0)

    class _Form:
        def __init__(self, disposed):
            self.IsDisposed = disposed

    class _Win:
        def __init__(self, disposed):
            self.native = _Form(disposed)

    class _Toast:
        _showing = True
        _window = _Win(True)

    class _Windows:
        toast = _Toast()

    host._windows = _Windows()
    ctl._lift = 84
    ctl._lift_target = 84
    ctl._reconcile_lift()
    check("a disposed toast does not keep the gap",
          ctl._lift == 0 and ctl._lift_target == 0)

    host._windows.toast._window = _Win(False)
    ctl._lift = 84
    ctl._lift_target = 84
    ctl._reconcile_lift()
    check("a live toast keeps the gap",
          ctl._lift == 84 and ctl._lift_target == 84)


def test_pool():
    check("six likes", len(POOL) == 6 and POOL[0] == "trail" and POOL[5] == "hdusk")
    seen = {pick_background(None, lambda: 0.0)}
    for i in range(len(POOL)):
        nxt = pick_background(POOL[i], lambda: 0.0)
        check("zero roll is not the one just shown", nxt != POOL[i], (POOL[i], nxt))
        check("zero roll stays in the pool", nxt in POOL)
        seen.add(nxt)
    check("a full pass can reach more than one", len(seen) > 1)

    import random
    rng = random.Random(4)
    previous = None
    bad = []
    for _ in range(80):
        nxt = pick_background(previous, rng.random)
        if nxt not in POOL or (previous is not None and nxt == previous):
            bad.append((previous, nxt))
        previous = nxt
    check("eighty rolls stay in the pool and never repeat", not bad, bad[:4])

    bg, at = background_for_open(None, None, 1000.0, lambda: 0.2)
    kept, at2 = background_for_open(bg, at, 1000.0 + BG_HOLD_S - 1, lambda: 0.9)
    check("opening again inside the hold keeps the same one",
          kept == bg and at2 == at, (bg, kept))
    rolled, at3 = background_for_open(bg, at, 1000.0 + BG_HOLD_S, lambda: 0.0)
    check("once the hold is over the next open is a different one",
          rolled != bg and rolled in POOL and at3 == 1000.0 + BG_HOLD_S,
          (bg, rolled))

    check("a 1.0 roll does not walk off the end",
          pick_background(POOL[-1], lambda: 1.0) in POOL
          and pick_background(POOL[-1], lambda: 1.0) != POOL[-1])
    check("a negative roll does not walk off the front",
          pick_background(POOL[0], lambda: -1.0) in POOL)


def test_knob():
    logs = []
    knob = DialKnob(on_log=logs.append)

    allow, action = knob.handle(down("volume up", 57392))
    check("closed notch is not swallowed", allow is True and action is None)
    knob.handle(up("volume up", 57392))
    check("first volume-up is logged",
          any("first volume_up" in line and "vk=0xaf" in line for line in logs),
          logs)

    allow, action = knob.handle(down("a", 30))
    check("unrelated key passes", allow is True and action is None)

    allow, action = knob.handle(down("volume mute", 57376))
    check("mute press swallowed", allow is False)
    check("mute opens on row 0",
          action and action["type"] == "open" and knob.index == 0)

    allow, _action = knob.handle(down("volume mute", 57376))
    check("mute repeat does not open again", allow is False and _action is None)
    knob.handle(up("volume mute", 57376))

    allow, action = knob.handle(down("volume up", 57392))
    check("open notch swallowed", allow is False)
    check("clockwise moves to row 1",
          action and action["type"] == "move" and action["index"] == 1)
    allow, action = knob.handle(down("volume up", 57392))
    check("auto-repeat does not move again", allow is False and action is None)
    knob.handle(up("volume up", 57392))

    allow, action = knob.handle(down("volume down", 57390))
    check("anticlockwise moves back",
          allow is False and action and action["index"] == 0)
    knob.handle(up("volume down", 57390))
    allow, action = knob.handle(down("volume down", 57390))
    check("notch at the top stays put", allow is False and action is None)
    knob.handle(up("volume down", 57390))

    allow, action = knob.handle(down("esc", 1))
    check("escape swallowed", allow is False)
    check("escape closes without a row",
          action and action["type"] == "close" and "index" not in action)
    token = action["token"]
    knob.note_closed(token)
    check("close releases the knob", knob.phase == "closed")

    allow, action = knob.handle(down("volume up", 57392))
    check("volume works again once closed", allow is True and action is None)
    knob.handle(up("volume up", 57392))

    knob.handle(down("volume mute", 57376))
    knob.handle(up("volume mute", 57376))
    knob.handle(down("volume up", 57392))
    knob.handle(up("volume up", 57392))
    _allow, action = knob.handle(down("volume mute", 57376))
    check("second press runs row 1",
          action and action["type"] == "activate" and action["index"] == 1)
    check("running a row starts the close", knob.phase == "closing")
    # Key-up of that mute must stay swallowed after the phase changes.
    allow, _action = knob.handle(up("volume mute", 57376))
    check("mute key-up stays swallowed", allow is False)
    knob.note_closed(action["token"])
    allow, _action = knob.handle(down("volume down", 57390))
    check("volume down passes after the run", allow is True)


def _open(knob):
    knob.handle(down("volume mute", 57376))
    knob.handle(up("volume mute", 57376))


def _notch(knob, name, scan):
    knob.handle(down(name, scan))
    knob.handle(up(name, scan))


def test_five_rows_and_delete():
    check("five rows", ROW_COUNT == 5 and DELETE_ROW == 4)
    knob = DialKnob(on_log=lambda _msg: None)
    _open(knob)
    for _ in range(4):
        _notch(knob, "volume up", 57392)
    check("the last row is delete", knob.index == DELETE_ROW)
    allow, action = knob.handle(down("volume up", 57392))
    check("the bottom notch does not wrap", allow is False and action is None)
    knob.handle(up("volume up", 57392))
    allow, action = knob.handle(down("volume mute", 57376))
    check("the first delete press only arms",
          allow is False and action and action["type"] == "arm"
          and knob.phase == "open")
    knob.handle(up("volume mute", 57376))
    allow, action = knob.handle(down("volume mute", 57376))
    check("the second delete press runs it",
          allow is False and action and action["type"] == "activate"
          and action["index"] == DELETE_ROW and knob.phase == "closing")
    knob.note_closed(action["token"])

    knob = DialKnob(on_log=lambda _msg: None)
    _open(knob)
    for _ in range(4):
        _notch(knob, "volume up", 57392)
    knob.handle(down("volume mute", 57376))
    knob.handle(up("volume mute", 57376))
    _notch(knob, "volume down", 57390)
    check("turning away clears the confirm", knob._armed is None and knob.index == 3)
    allow, action = knob.handle(down("volume mute", 57376))
    check("that press runs save, not delete",
          allow is False and action and action["type"] == "activate"
          and action["index"] == 3)
    check("confirm copy", DELETE_CONFIRM == "Press again to delete")


def test_live_k762_scans():
    logs = []
    knob = DialKnob(on_log=logs.append)
    allow, action = knob.handle(down("volume up", -175))
    check("live clockwise notch is volume up",
          allow is True and action is None and knob.phase == "closed")
    check("live scan logs vk 0xaf",
          any("vk=0xaf" in line and "scan=-175" in line for line in logs), logs)
    knob.handle(up("volume up", -175))
    allow, action = knob.handle(down("", -173))
    check("live press with no name is mute",
          allow is False and action and action["type"] == "open")


def test_numpad_ins():
    knob = DialKnob(on_log=lambda _msg: None)
    allow, action = knob.handle(Ev("insert", "down", 82, is_keypad=True))
    check("numpad ins opens the menu",
          allow is False and action and action["type"] == "open"
          and knob.phase == "open")
    knob2 = DialKnob(on_log=lambda _msg: None)
    allow, action = knob2.handle(Ev("insert", "down", 82, is_keypad=False))
    check("the real insert key still inserts",
          allow is True and action is None and knob2.phase == "closed")
    allow, action = knob2.handle(Ev("0", "down", 82, is_keypad=True))
    check("num lock on still types zero",
          allow is True and action is None and knob2.phase == "closed")


def test_hook_pairs():
    class Keys:
        def __init__(self):
            self.cb = None
            self.suppress = None
            self.removed = False

        def hook(self, callback, suppress=False):
            self.cb = callback
            self.suppress = suppress

            def remove():
                self.removed = True
                self.cb = None

            return remove

    keys = Keys()
    previous = hotkey_mod.keyboard
    previous_flag = hotkey_mod._AVAILABLE
    hotkey_mod.keyboard = keys
    hotkey_mod._AVAILABLE = True
    seen = []

    def cb(event):
        seen.append(event.name)
        return event.name != "volume mute"

    handle = hotkey_mod.hook(cb, suppress=True, on_log=lambda _m: None)
    check("hook installed suppress", keys.suppress is True and callable(handle))
    check("unrelated key allowed", keys.cb(down("a", 30)) is True)
    check("false return swallows", keys.cb(down("volume mute", 57376)) is False)
    try:
        hotkey_mod.unhook(handle)
        check("unhook removes it", keys.removed and keys.cb is None)
        check("unhook of nothing is safe", hotkey_mod.unhook(False) is False)
    finally:
        hotkey_mod.keyboard = previous
        hotkey_mod._AVAILABLE = previous_flag


class FakeWindow:
    def __init__(self, title):
        self.title = title
        self.shown = False
        self.hidden = False
        self.destroyed = False
        self.js = []

    def show(self):
        self.shown = True
        self.hidden = False

    def hide(self):
        self.hidden = True
        self.shown = False

    def move(self, x, y):
        self.x, self.y = x, y

    def evaluate_js(self, script):
        self.js.append(script)

    def destroy(self):
        self.destroyed = True


class FakeNative:
    InvokeRequired = False

    def Invoke(self, fn):
        fn()


class FakeMaster:
    def __init__(self):
        self.native = FakeNative()


class StubHost:
    def __init__(self):
        self.window = FakeMaster()
        self.log = []
        self._dial = DialKnob()

    def _log(self, msg):
        self.log.append(msg)


def test_one_window():
    created = []

    def fake_create(title, url, **kw):
        win = FakeWindow(title)
        created.append((win, kw))
        return win

    old = nw.webview.create_window
    nw.webview.create_window = fake_create
    try:
        host = StubHost()
        ctl = nw.DialController(host)
        payload = {
            "status": "Idle",
            "pauseLabel": "Pause recording",
            "index": 0,
            "seed": 4,
        }
        ctl.open(payload)
        check("open creates one window", len(created) == 1, len(created))
        check("window is the dial", created[0][0].title == "Nebula Dial")
        check("does not take focus", created[0][1].get("focus") is False)
        check("not a transparent white form",
              created[0][1].get("transparent") in (None, False))
        ctl._on_ready()
        time.sleep(0.12)
        text = " ".join(created[0][0].js)
        check("payload reaches the page", "Idle" in text and "dialOpen" in text, text[:180])
        ctl.open(dict(payload, status="Paused", pauseLabel="Resume recording"))
        time.sleep(0.12)
        check("second open reuses the window", len(created) == 1)
        check("status is not stuck on Recording",
              "Paused" in " ".join(created[0][0].js))
        ctl.highlight(2)
        time.sleep(0.08)
        check("highlight is a script, not a new window",
              len(created) == 1 and any("dialHighlight(2)" in j for j in created[0][0].js))
        host._dial.phase = "closing"
        host._dial._close_token = 1
        ctl.close(1)
        time.sleep(0.08)
        check("close hides the slot", created[0][0].hidden and not created[0][0].destroyed)
        check("close releases the knob", host._dial.phase == "closed")
    finally:
        nw.webview.create_window = old


def test_close_beats_a_late_reveal():
    created = []

    def fake_create(title, url, **kw):
        win = FakeWindow(title)
        created.append(win)
        return win

    old = nw.webview.create_window
    nw.webview.create_window = fake_create
    try:
        host = StubHost()
        ctl = nw.DialController(host)
        payload = {
            "status": "Idle",
            "pauseLabel": "Pause recording",
            "index": 0,
            "seed": 4,
        }
        ctl.open(payload)
        ctl._on_ready()
        time.sleep(0.12)
        win = created[0]
        opened_gen = ctl._generation

        def hang_pose(direction, gen, token):
            ctl._pose_dir = -1 if direction == "close" else 1
            ctl._close_token = token

        ctl._start_pose = hang_pose
        ctl.close(7)
        check("close invalidated the open", ctl._generation != opened_gen)
        check("close stays up until the leave ends",
              ctl._closing and ctl._showing and not win.hidden)
        ctl._reveal(opened_gen)
        check("stale reveal does not restart the open", ctl._pose_dir == -1)
        ctl._reveal(ctl._generation)
        check("reveal during the leave does not restart the open",
              ctl._pose_dir == -1)
        before = len(win.js)
        ctl._push(dict(payload), opened_gen)
        ctl._push(dict(payload), ctl._generation)
        time.sleep(0.12)
        check("a late push does not reopen the page", len(win.js) == before, win.js)
        host._dial.index = 2
        ctl._closing = False
        ctl._showing = True
        ctl._push(dict(payload, index=0), ctl._generation)
        time.sleep(0.12)
        check("the page follows the knob, not the frozen index",
              any('"index": 2' in line for line in win.js), win.js[-1:])
    finally:
        nw.webview.create_window = old


def test_activate_still_closes():
    from spike.host import NebulaHost

    closed = []

    class Wins:
        def dial_close(self, token):
            closed.append(token)

    class Host:
        def __init__(self):
            self._dial = DialKnob()
            self._windows = Wins()

        def _log(self, msg):
            pass

        def dial_status(self):
            return {"status": "Idle", "pauseLabel": "Pause recording"}

        def _dial_row_name(self, index):
            return "Pause recording"

        def _dial_run(self, index):
            raise RuntimeError("transport failed")

    host = Host()
    raised = False
    try:
        NebulaHost._dial_perform(
            host, {"type": "activate", "index": 1, "token": 4})
    except RuntimeError:
        raised = True
    check("a failing row still raises", raised)
    check("and the menu still closes", closed == [4], closed)


def test_abandon_ignores_a_newer_open():
    knob = DialKnob()
    knob.handle(down("volume mute", 57376))
    first = knob._epoch
    knob.phase = "closed"
    knob.handle(up("volume mute", 57376))
    knob.handle(down("volume mute", 57376))
    knob.abandon(first)
    check("a newer open survives the old deadline", knob.phase == "open")
    knob.abandon(knob._epoch)
    check("the matching deadline releases it", knob.phase == "closed")


def test_shell_on_disk():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(root, "spike", "web", "dial.html"), encoding="utf-8").read()
    css = open(os.path.join(root, "spike", "web", "dial.css"), encoding="utf-8").read()
    check("start path copied", "M14 4h6v6M20 4l-8 8" in html)
    check("pause path copied", "M8 5v14M16 5v14" in html)
    check("save path copied", "M5 4h11l3 3v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4z" in html)
    check("stop and delete are on the menu",
          "Stop recording" in html and "Delete this clip" in html)
    check("five rows", html.count('class="row"') == 5)
    check("no gallery chrome", "prefs-dial-menu" not in html and "LIKE" not in html)
    check("canvas is the background", 'id="bg"' in html and "dial-bg.js" in html)
    check("reduced motion pauses", "animation-play-state: paused" in css)
    check("rows are in with the panel", "--row-d0" not in css)
    js = open(os.path.join(root, "spike", "web", "dial-bg.js"), encoding="utf-8").read()
    for key in ("trail", "twin", "twinTR", "hpatches", "hrose", "hdusk"):
        check("pool key %s is in the painter" % key, key in js)


def test_painter_holds_up():
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(root, "tests", "test_dial_bg.js")
    proc = subprocess.run(
        ["node", script], cwd=root, capture_output=True, text=True, timeout=30)
    check("painter survives the break pass", proc.returncode == 0,
          (proc.stdout + proc.stderr)[-500:])


def main():
    test_words()
    test_pose()
    test_dodge()
    test_pool()
    test_knob()
    test_five_rows_and_delete()
    test_live_k762_scans()
    test_numpad_ins()
    test_hook_pairs()
    test_one_window()
    test_hidden_menu_remembers_the_gap()
    test_dead_toast_releases_the_corner()
    test_close_beats_a_late_reveal()
    test_activate_still_closes()
    test_abandon_ignores_a_newer_open()
    test_painter_holds_up()
    test_shell_on_disk()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
