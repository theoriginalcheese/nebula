"""A deliberate pause must never read as a fault, and an idle pause waits
for the game to come back before it resumes.

Two things are pinned here:

1. "Pause monitoring" used to go through `NebulaHost._stop()`, which drops
   the OBS websocket. The hero card then showed frame 2h - the ember
   `Can't reach OBS` / `Retry now` - for a connection that was never lost,
   with no way back to monitoring. It now keeps the socket and reports its
   own `monitoring_paused` state.
2. An idle auto-pause used to resume on *any* input, so answering a Discord
   message put the recording back on while the game sat in the background.
   It now holds until the recorded game owns the foreground window - and
   fails open when that question cannot be answered, because a check that
   cannot answer must never be what keeps a recording paused for ever.

    python tests/test_pause_status.py
"""
from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spike import host as host_mod
from spike.host import NebulaHost
from spike.app import Api
from obsauto import monitor as mon

# Never launch or probe real OBS from tests.
host_mod.ensure_obs_running = lambda *a, **k: None
host_mod.is_obs_running = lambda: False

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


CFG = {"obs_host": "localhost", "obs_port": 4455,
       "recording_root": "D:/OBS Recordings",
       "toggle_hotkey": "`", "toggle_hotkey_scancode": 41,
       "replay_hotkey": "f9", "palette_hotkey": "ctrl+k",
       "obs_path": "", "obs_password": "",
       "idle_timeout_seconds": 4, "reconnect_interval_seconds": 10}


class FakeOBS:
    def __init__(self):
        self.connected = True
        self.recording = False
        self.paused = False
        self.last_handshake_ms = 12

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def get_record_status(self):
        return {"outputActive": self.recording, "outputPaused": self.paused,
                "outputDuration": 5000, "outputBytes": 1024}


class FakeMonitor:
    def __init__(self):
        self._running = True
        self._recording_target = None

    def start(self):
        self._running = True

    def stop(self):
        self._running = False


def make_host():
    host = NebulaHost(dict(CFG))
    host.obs = FakeOBS()
    host.monitor = FakeMonitor()
    host._obs_connected = True
    return host


def stub_api(host):
    api = Api.__new__(Api)
    api.cfg = dict(CFG)
    api._host = host
    return api


# --- 1. pausing the watcher is not a disconnection --------------------------

def test_pause_monitoring_keeps_obs():
    host = make_host()
    host.pause_monitoring()
    check("the websocket is still up", host.obs.connected is True)
    check("the watcher is stopped", host.monitor._running is False)
    check("state says so", host.hero_state() == "monitoring_paused",
          host.hero_state())
    status = host.tray_status()
    check("tray heading is not a fault", status["heading"] == "Monitoring paused",
          status["heading"])
    check("tray detail explains the consequence",
          status["detail"] == "Nothing will record until you resume",
          status["detail"])
    host.quit()


def test_resume_monitoring_needs_no_reconnect():
    host = make_host()
    host.pause_monitoring()
    host.obs.connect = lambda: check("resume did not reconnect", False,
                                     "OBS was never disconnected")
    host.resume_monitoring()
    check("the watcher is back", host.monitor._running is True)
    check("state is idle again", host.hero_state() == "idle", host.hero_state())
    host.quit()


def test_a_live_recording_still_wins():
    host = make_host()
    host.obs.recording = True   # the poll inside pause_monitoring re-reads OBS
    host.pause_monitoring()
    check("recording is reported over the pause",
          host.hero_state() == "recording", host.hero_state())
    host.quit()


def test_hero_card_offers_a_way_back():
    host = make_host()
    host.pause_monitoring()
    hero = stub_api(host)._hero()
    check("no ember tint", not hero["tint"], hero["tint"])
    check("eyebrow names the pause", hero["eyebrow"] == "Monitoring paused",
          hero["eyebrow"])
    check("title is not the disconnect copy",
          hero["title"] == "Monitoring paused", hero["title"])
    check("hint says OBS is still connected",
          "still connected" in hero["hint"], hero["hint"])
    check("resume is offered", "Resume monitoring" in hero["actions"],
          str(hero["actions"]))
    check("resume is clickable", "Resume monitoring" in hero["actions_enabled"])
    check("no frozen readouts", hero["show_readouts"] is False)
    host.quit()


def test_hero_action_routes_resume():
    host = make_host()
    host.pause_monitoring()
    api = stub_api(host)
    check("the button is a known action",
          api.hero_action("Resume monitoring")["ok"] is True)
    check("and pause is too", api.hero_action("Pause monitoring")["ok"] is True)
    host.quit()


# --- 2. an idle pause waits for the game ------------------------------------

class FakeClassifier:
    """Cache-only classify, the way the loop's gate is allowed to ask."""

    GAMES = {"game.exe": "Some Game", "other.exe": "Another Game"}

    def peek(self, exe_path, proc_name):
        name = self.GAMES.get(os.path.basename(exe_path or "").lower())
        return ("game", name) if name else ("non_game", None)


class GateMonitor(mon.Monitor):
    """Just the pause bookkeeping - no OBS, no loop."""

    def __init__(self):
        self.classifier = FakeClassifier()
        self._recording_target = (4242, "game.exe", "Some Game", "D:/x")
        self._auto_paused = True
        self._auto_pause_reason = "idle"
        self._last_focus_hold_log = 0.0
        self.logged = []

    def log(self, msg):
        self.logged.append(msg)


GAME_FG = (4242, r"C:\games\game.exe", "game.exe", "Some Game", "UnityWndClass")
BROWSER_FG = (99, r"C:\b\chrome.exe", "chrome.exe", "Docs", "Chrome_WidgetWin_1")
SAME_EXE_NEW_PID = (7, r"C:\games\GAME.EXE", "game.exe", "Some Game", "W")
OTHER_GAME_FG = (55, r"C:\games\other.exe", "other.exe", "Another Game", "W")


def test_foreground_gate():
    original = mon.get_foreground_window_info
    try:
        cases = [
            ("the recorded game in front resumes", GAME_FG, True),
            ("a browser in front holds the pause", BROWSER_FG, False),
            ("same exe under a new pid still counts", SAME_EXE_NEW_PID, True),
            ("an unreadable foreground fails open", None, True),
            ("another game in front also releases it", OTHER_GAME_FG, True),
        ]
        for name, info, expected in cases:
            mon.get_foreground_window_info = lambda i=info: i
            check(name, GateMonitor()._recorded_game_foreground() is expected)

        mon.get_foreground_window_info = lambda: BROWSER_FG
        m = GateMonitor()
        m._recording_target = None
        check("no target means nothing to wait for",
              m._recorded_game_foreground() is True)
    finally:
        mon.get_foreground_window_info = original


def test_focus_hold_log_is_rate_limited():
    m = GateMonitor()
    for _ in range(50):
        m._log_focus_hold()
    check("the hold says why, once", len(m.logged) == 1, str(m.logged))
    check("and names the game", "Some Game" in m.logged[0], m.logged[0])


def test_session_pauses_are_untouched():
    original = mon.get_foreground_window_info
    try:
        mon.get_foreground_window_info = lambda: BROWSER_FG
        m = GateMonitor()
        m._auto_pause_reason = "session"
        # The loop's gate reads the reason: a Moonlight pause is owned by the
        # stream gate, not by what happens to be in front locally.
        held = (m._auto_paused and m._auto_pause_reason == "idle"
                and not m._recorded_game_foreground())
        check("a stream-ended pause is not focus-gated", held is False)
    finally:
        mon.get_foreground_window_info = original


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
