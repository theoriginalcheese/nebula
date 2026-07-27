"""Instant replay - spec 7a.

    "A rolling buffer OBS already keeps in RAM. One key writes the last N
     seconds to disk with no session recording running. Nebula's job is to arm
     the buffer when a game is detected, name the saved file, and confirm it."

The parts worth pinning are the ones that are easy to get subtly wrong: the
save path arrives as an *event* rather than in the response, the file must be
moved rather than copied, and a replay must never be caught by the auto-cull.

    python tests/test_replay.py
"""
import os
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto import replay as replay_mod
from obsauto import session_log
from obsauto.classifier import Classifier
from obsauto.config import DEFAULTS, load_config
from obsauto.gui import AppWindow
from obsauto.obs_client import OBSError
from obsauto.replay import ReplayBuffer

config_module.save_config = lambda *a, **k: None

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class FakeOBS:
    def __init__(self):
        self.connected = True
        self.buffer_active = False
        self.calls = []
        self.params = {}
        self.fail = None
        self.on_event = None

    def _maybe_fail(self):
        if self.fail:
            message, self.fail = self.fail, None
            raise OBSError(message)

    def start_replay_buffer(self):
        self.calls.append("start")
        self._maybe_fail()
        self.buffer_active = True

    def stop_replay_buffer(self):
        self.calls.append("stop")
        self._maybe_fail()
        self.buffer_active = False

    def save_replay_buffer(self):
        self.calls.append("save")
        self._maybe_fail()

    def get_replay_buffer_status(self):
        return self.buffer_active

    def set_profile_parameter(self, category, name, value):
        self.params[(category, name)] = value


# ---------------------------------------------------------------------------
# The formula and its bounds
# ---------------------------------------------------------------------------
# "MB ≈ (bitrate_mbps / 8) × seconds × 1.1"
check("the RAM estimate is the spec's formula",
      abs(replay_mod.ram_estimate_mb(100, 30) - (100 / 8 * 30 * 1.1)) < 0.001,
      replay_mod.ram_estimate_mb(100, 30))
check("no bitrate means no estimate, not a guess",
      replay_mod.ram_estimate_mb(None, 30) is None)
check("the 2 GB warning threshold is the spec's",
      replay_mod.RAM_WARN_MB == 2048, replay_mod.RAM_WARN_MB)
check("buffer length is clamped to 10-300",
      (replay_mod.clamp_seconds(1), replay_mod.clamp_seconds(9999),
       replay_mod.clamp_seconds("x")) == (10, 300, 30),
      (replay_mod.clamp_seconds(1), replay_mod.clamp_seconds(9999)))

for key, want in replay_mod.DEFAULTS.items():
    check(f"config carries {key}", DEFAULTS.get(key) == want,
          f"{DEFAULTS.get(key)!r} != {want!r}")

# ---------------------------------------------------------------------------
# Arming
# ---------------------------------------------------------------------------
tmp = tempfile.mkdtemp(prefix="nebula-replay-")
session_log.log_path = lambda: os.path.join(tmp, "sessions.jsonl")

obs = FakeOBS()
cfg = dict(DEFAULTS)
cfg["recording_root"] = os.path.join(tmp, "recordings")
saved = []
states = []
rb = ReplayBuffer(obs, cfg, on_log=lambda m: None,
                  on_saved=lambda p, g: saved.append((p, g)),
                  on_state=states.append)

check("nothing is armed to begin with", rb.armed is False)
rb.arm("Helldivers 2")
check("arming starts the buffer", "start" in obs.calls, obs.calls)
check("it reports armed", rb.armed is True and states[-1] is True, states)
# "SetProfileParameter: SimpleOutput / RecRB, RecRBTime"
check("the buffer length is pushed to OBS",
      obs.params.get(("SimpleOutput", "RecRBTime")) == 30, obs.params)
check("the buffer is enabled in the profile",
      obs.params.get(("SimpleOutput", "RecRB")) == "true", obs.params)

obs.calls.clear()
rb.arm("Helldivers 2")
check("arming twice doesn't restart it", "start" not in obs.calls, obs.calls)

rb.disarm()
check("disarming stops the buffer", "stop" in obs.calls, obs.calls)
check("it reports disarmed", rb.armed is False and states[-1] is False)

# A refused arm must leave the state honest rather than claiming success.
obs.fail = "StartReplayBuffer failed"
rb.arm("Helldivers 2")
check("a refused arm doesn't claim to be armed", rb.armed is False)

# "GetReplayBufferStatus: poll on connect to set the badge."
obs.buffer_active = True
rb.refresh_from_obs()
check("connecting adopts OBS's real buffer state", rb.armed is True)

# ---------------------------------------------------------------------------
# Saving, and the event that carries the path
# ---------------------------------------------------------------------------
obs.calls.clear()
check("saving reaches OBS", rb.save() is True and obs.calls == ["save"], obs.calls)
check("the path is not in the save response - nothing filed yet", not saved)

source = os.path.join(tmp, "obs-output", "Replay 2026-07-27 03-00-00.mkv")
os.makedirs(os.path.dirname(source), exist_ok=True)
with open(source, "wb") as f:
    f.write(b"0" * 4096)

rb.handle_event("ReplayBufferSaved", {"savedReplayPath": source})
check("the event files the clip", len(saved) == 1, saved)
landed = saved[0][0] if saved else ""
check("it lands under the game's Replays folder",
      os.path.normpath(landed).startswith(
          os.path.normpath(os.path.join(cfg["recording_root"], "Helldivers 2", "Replays"))),
      landed)
check("the filename is the spec's timestamp form",
      os.path.basename(landed)[:4].isdigit() and os.path.basename(landed)[4] == "-",
      os.path.basename(landed))
# "Move, never copy - OBS writes to its own output dir first."
check("the source is moved, not copied", not os.path.exists(source), source)
check("and the destination exists", os.path.exists(landed), landed)
check("it's recorded as saved this session",
      len(rb.saved_this_session) == 1, rb.saved_this_session)

# "Replays bypass min_clip_seconds entirely; they are intentional by
# definition." So the session log must not mark one as culled - if it did, the
# Auto-culled tile would count deliberate saves as accidents.
rows = [r for r in session_log.read() if r.get("type") == "rec_stop"]
check("the replay is logged", rows, rows)
check("a replay is never marked culled",
      rows and not rows[-1].get("culled"), rows[-1] if rows else None)
check("it is flagged as a replay", rows and rows[-1].get("replay") is True,
      rows[-1] if rows else None)
check("a replay counts as a kept clip",
      session_log.today()["clips"] == 1 and session_log.today()["culled"] == 0,
      session_log.today())

# Saving with nothing armed must say so rather than pretending.
rb.armed = False
obs.calls.clear()
check("saving a disarmed buffer is refused", rb.save() is False)
check("and nothing was sent to OBS", obs.calls == [], obs.calls)

# A vanished file is reported, not crashed on.
rb.armed = True
rb._file(os.path.join(tmp, "does-not-exist.mkv"))
check("a missing source file fails soft", len(saved) == 1, saved)

# ---------------------------------------------------------------------------
# The dashboard module
# ---------------------------------------------------------------------------
app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=200):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


settle(350)

check("the replay module is on the dashboard by default",
      "replay" in {it["id"] for it in gui.DEFAULT_GRID},
      [it["id"] for it in gui.DEFAULT_GRID])
check("it is half width, as 7a draws it",
      next(it["span"] for it in gui.DEFAULT_GRID if it["id"] == "replay") == 6)
check("its height is the spec's 236", gui.BLOCK_HEIGHTS["replay"][6] == 236,
      gui.BLOCK_HEIGHTS["replay"])
check("it registers in the 6.8 catalogue", "replay" in gui.BLOCK_LABELS)
check("the module got built", getattr(app, "_replay_badge", None) is not None)

# No bitrate has been measured, so there must be no RAM figure at all.
check("no RAM estimate before a real bitrate exists",
      app.bg._c.itemcget(app._replay_ram_id, "text") == "",
      app.bg._c.itemcget(app._replay_ram_id, "text"))
app._last_bitrate_mbps = 40.0
app._refresh_replay_module()
settle(80)
check("a measured bitrate produces one",
      "RAM" in app.bg._c.itemcget(app._replay_ram_id, "text"),
      app.bg._c.itemcget(app._replay_ram_id, "text"))

def badge():
    # Eyebrow text is letter-spaced by _track(), so compare unspaced.
    return app.bg._c.itemcget(app._replay_badge_text, "text").replace(" ", "").upper()


app.replay.armed = False
app._refresh_replay_module()
settle(60)
check("the badge reads Disarmed when it is", badge() == "DISARMED", badge())
app.replay.armed = True
app._refresh_replay_module()
settle(60)
check("and Buffer armed when it is", badge() == "BUFFERARMED", badge())

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<52} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
