"""The Settings view has to actually change the running app.

A settings page that only writes a file is a lie: the whole point of editing in
the app rather than in config.json is not restarting. So this checks both ends -
that the form round-trips every value faithfully, and that saving reaches the
live objects that snapshot their configuration (the OBS client, the audio
keep-alive, the game-list sync, the offloader, the global hotkey).

Runs under a real `mainloop()` on purpose. Saving OBS connection settings
reconnects, and that has to happen on a worker with the result marshalled back
through `_ui()` -> `root.after` - which Tk refuses when it's being driven by
`update()` instead. An update()-pumped test would quietly pass a version that
blocks the UI for the full socket timeout.

    python tests/test_settings.py

Needs a desktop session (it creates a hidden Tk window). No OBS required.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import config as config_module, gui, hotkey, settings_spec

# Never write the real config.json sitting next to the app, and never grab a
# global hotkey or launch OBS from a test.
saved_configs = []
config_module.save_config = lambda cfg: saved_configs.append(dict(cfg))
gui.ensure_obs_running = lambda *a, **k: None

hotkey_calls = {"registered": [], "unregistered": []}


def fake_register(binding, callback, suppress=True, on_log=None, scancode=None):
    handle = f"hook:{scancode if scancode is not None else binding}"
    hotkey_calls["registered"].append(handle)
    return handle


def fake_unregister(handle, on_log=None):
    hotkey_calls["unregistered"].append(handle)
    return True


hotkey.register = fake_register
hotkey.unregister = fake_unregister

from obsauto.classifier import Classifier
from obsauto.config import DEFAULTS, load_config
from obsauto.gamesync import GameSync
from obsauto.gui import AppWindow
from obsauto.offload import Offloader

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


# ---------------------------------------------------------------- pure spec
# These need no window, so they run first and fail fast.

for field in settings_spec.FIELDS:
    check(f"spec: {field.key} is a real config key", field.key in DEFAULTS)

# ...and the other direction, so adding a key to DEFAULTS without deciding
# whether it belongs in the UI fails here instead of quietly being uneditable.
unexposed = sorted(set(DEFAULTS) - {f.key for f in settings_spec.FIELDS})
check("spec: every config default is editable", not unexposed, unexposed)

# The strongest guarantee the form can offer: opening the page and pressing Save
# without touching anything must be a no-op. That holds only if render() and
# parse() are exact inverses for every default.
round_trip_bad = []
for field in settings_spec.FIELDS:
    original = DEFAULTS[field.key]
    value, error = settings_spec.parse(field, settings_spec.render(field, original))
    if error or value != original:
        round_trip_bad.append((field.key, original, value, error))
check("spec: every default round-trips through the form", not round_trip_bad,
      round_trip_bad[:2])

port = settings_spec.BY_KEY["obs_port"]
check("spec: non-numeric port rejected", settings_spec.parse(port, "abc")[1])
check("spec: port 0 rejected (below minimum)", settings_spec.parse(port, "0")[1])
check("spec: port 70000 rejected (above maximum)", settings_spec.parse(port, "70000")[1])
check("spec: port 4455 accepted", settings_spec.parse(port, " 4455 ") == (4455, None))

scancode = settings_spec.BY_KEY["toggle_hotkey_scancode"]
check("spec: blank scan code means unset", settings_spec.parse(scancode, "  ") == (None, None))

keep_alive = settings_spec.BY_KEY["keep_alive_audio_processes"]
check("spec: list splits and trims",
      settings_spec.parse(keep_alive, " discord.exe , vesktop.exe ,, ")[0]
      == ["discord.exe", "vesktop.exe"])
check("spec: empty list allowed", settings_spec.parse(keep_alive, "")[0] == [])

mode = settings_spec.BY_KEY["nas_offload_mode"]
check("spec: mode is case-insensitive", settings_spec.parse(mode, "MOVE") == ("move", None))
check("spec: nonsense mode rejected", settings_spec.parse(mode, "delete")[1])

root_field = settings_spec.BY_KEY["recording_root"]
check("spec: a pasted quoted path is unquoted",
      settings_spec.parse(root_field, '"D:/OBS Recordings"') == ("D:/OBS Recordings", None))

# A missing path is advisory, never fatal - a NAS or removable drive is allowed
# to show up after it's configured.
values, errors = settings_spec.parse_all({"nas_offload_root": "Z:/definitely/not/here"})
check("spec: absent path still parses", not errors and values["nas_offload_root"])
check("spec: absent path is reported as a warning",
      [f.key for f in settings_spec.missing_paths(values)] == ["nas_offload_root"])
check("spec: only sync_folder needs a restart",
      [f.key for f in settings_spec.restart_required(set(DEFAULTS))] == ["sync_folder"])


# ------------------------------------------------------------------- the app
class FakeOBS:
    """Stands in for OBSClient: never connected, so nothing here talks to a
    real OBS, but it still carries the host/port/password the settings write."""
    connected = False

    def __init__(self):
        self.host, self.port, self.password = "localhost", 4455, ""
        self.connect_calls = 0

    def connect(self):
        self.connect_calls += 1
        time.sleep(1.0)  # a real connect blocks for up to its socket timeout
        raise OSError("simulated: nothing listening")

    def disconnect(self):
        pass

    def get_record_status(self):
        return {"outputActive": False, "outputPaused": False}

    def is_recording(self):
        return False


config = load_config()
config.update({
    "obs_host": "localhost", "obs_port": 4455, "obs_password": "",
    "recording_root": "D:/OBS Recordings", "idle_timeout_seconds": 4,
    "min_clip_seconds": 10, "keep_alive_audio_processes": ["discord.exe"],
    "toggle_hotkey": "`", "toggle_hotkey_scancode": 41,
    "nas_offload_root": "", "nas_offload_mode": "copy",
    "github_gamedata_repo": "", "github_token": "", "sync_folder": "",
})
offloader = Offloader(config)
gamesync = GameSync(config)
app = AppWindow(config, Classifier(), on_close_to_tray=lambda: None,
                offloader=offloader, gamesync=gamesync)
app.obs = FakeOBS()
app.root.withdraw()

callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb))
)


def field_text(key):
    return app._settings_widgets[key].get()


def set_field(key, text):
    widget = app._settings_widgets[key]
    if settings_spec.BY_KEY[key].kind == "choice":
        widget.set(text)
    else:
        widget.delete(0, "end")
        widget.insert(0, text)


def status():
    return app.bg.itemcget(app._settings_status_id, "text")


def keycap_label():
    labels = [app.bg.itemcget(i, "text") for i in app._keycap_items
              if app.bg.type(i) == "text"]
    return labels[0] if labels else None


# ---- the form reflects the config -------------------------------------
def case_form_reflects_config():
    app._show_view("settings")
    missing = [f.key for f in settings_spec.FIELDS
               if f.key not in app._settings_widgets]
    check("form has a widget for every field", not missing, missing)
    check("form shows the configured port", field_text("obs_port") == "4455",
          field_text("obs_port"))
    check("form shows the keep-alive list as text",
          field_text("keep_alive_audio_processes") == "discord.exe",
          field_text("keep_alive_audio_processes"))
    check("form shows an unset scan-code-less field as blank",
          field_text("sync_folder") == "", field_text("sync_folder"))

    secret = app._settings_widgets["github_token"]
    check("secrets masked by default", secret.cget("show") == "\u2022",
          secret.cget("show"))
    app._settings_show_secrets.select()
    app._apply_secret_masking()
    check("switch reveals secrets", secret.cget("show") == "",
          secret.cget("show"))
    app._settings_show_secrets.deselect()
    app._apply_secret_masking()

    # Pressing Save without editing anything must not write a file.
    saved_configs.clear()
    app._save_settings()
    check("untouched form saves nothing", not saved_configs, len(saved_configs))
    check("untouched form says so", "up to date" in status().lower(), status())


# ---- a bad value blocks the whole save -------------------------------
def case_validation():
    saved_configs.clear()
    set_field("obs_port", "not-a-port")
    set_field("min_clip_seconds", "42")   # a good change, alongside the bad one
    app._save_settings()
    check("invalid value saves nothing", not saved_configs, len(saved_configs))
    check("a good field isn't half-applied",
          app.config["min_clip_seconds"] == 10, app.config["min_clip_seconds"])
    check("the failing field is named", "Port" in status(), status())
    app._revert_settings()
    check("revert restores the saved value", field_text("obs_port") == "4455",
          field_text("obs_port"))
    check("revert says so", "revert" in status().lower(), status())


# ---- a good save reaches the live objects ----------------------------
def case_live_apply():
    saved_configs.clear()
    hotkey_calls["registered"].clear()
    hotkey_calls["unregistered"].clear()
    old_handle = app._hotkey_handle

    set_field("min_clip_seconds", "25")
    set_field("idle_timeout_seconds", "12")
    set_field("keep_alive_audio_processes", "discord.exe, vesktop.exe")
    set_field("toggle_hotkey", "f12")
    set_field("toggle_hotkey_scancode", "")
    set_field("nas_offload_root", os.path.join(os.path.expanduser("~"), "nas-test"))
    set_field("nas_offload_mode", "move")
    set_field("github_gamedata_repo", "someone/nebula-gamedata")
    set_field("github_token", "token-value-that-must-not-be-logged")
    app._log_lines.clear()
    app._save_settings()

    check("save wrote the config once", len(saved_configs) == 1, len(saved_configs))
    check("config picked up the new minimum clip",
          app.config["min_clip_seconds"] == 25, app.config["min_clip_seconds"])
    check("the monitor reads the new minimum clip live",
          app.monitor.config["min_clip_seconds"] == 25)
    check("keep-alive list parsed into the config",
          app.config["keep_alive_audio_processes"] == ["discord.exe", "vesktop.exe"],
          app.config["keep_alive_audio_processes"])
    check("the audio keep-alive was rebound live",
          app.monitor._audio_keep_alive.process_names == {"discord.exe", "vesktop.exe"},
          app.monitor._audio_keep_alive.process_names)
    check("the offloader picked up move mode", offloader.mode == "move", offloader.mode)
    check("the offloader is now enabled", offloader.enabled is True)
    check("game-list sync retargeted", gamesync.repo == "someone/nebula-gamedata",
          gamesync.repo)
    check("sync token applied", gamesync.token.startswith("token-value"))
    check("stale blob sha dropped with the retarget", gamesync._sha is None)
    check("the old hotkey hook was removed",
          hotkey_calls["unregistered"] == [old_handle], hotkey_calls["unregistered"])
    check("the new hotkey was bound by name",
          hotkey_calls["registered"] == ["hook:f12"], hotkey_calls["registered"])
    check("the nav rail keycap follows the binding", keycap_label() == "F12",
          keycap_label())
    check("the dashboard slider follows the idle timeout",
          int(app._timeout_slider.get()) == 12, app._timeout_slider.get())
    check("the idle-timeout tile follows too",
          app.bg.itemcget(app.timeout_value_id, "text") == "12s",
          app.bg.itemcget(app.timeout_value_id, "text"))
    check("save reported how many changed", "Saved" in status(), status())

    logged = "\n".join(app._log_lines)
    check("the log names the changed keys", "min_clip_seconds" in logged, logged[:80])
    check("the log never carries a secret's value",
          "token-value-that-must-not-be-logged" not in logged)


# ---- restart-only settings say so ------------------------------------
def case_restart_notice():
    set_field("sync_folder", "OneDrive/ObsAutoFolder")
    app._save_settings()
    check("a restart-only change is flagged", "estart" in status(), status())
    check("...but is still saved", app.config["sync_folder"] == "OneDrive/ObsAutoFolder",
          app.config["sync_folder"])
    set_field("sync_folder", "")
    app._save_settings()


# ---- the form re-reads on every visit --------------------------------
def case_reload_on_visit():
    # The dashboard slider writes idle_timeout_seconds straight to the config;
    # the page must not keep showing the stale number afterwards.
    app._show_view("dashboard")
    app._on_timeout_change(31)
    app._show_view("settings")
    check("revisiting the page re-reads the config",
          field_text("idle_timeout_seconds") == "31", field_text("idle_timeout_seconds"))
    # Unsaved typing is dropped on leaving, rather than shown as though it applied.
    set_field("recording_root", "E:/typed but never saved")
    app._show_view("games")
    app._show_view("settings")
    check("unsaved edits don't survive leaving the page",
          field_text("recording_root") == app.config["recording_root"],
          field_text("recording_root"))


# ---- OBS settings reconnect, and never on the Tk thread --------------
beat = {"ticks": 0, "worst": 0.0, "last": 0.0}


def case_obs_reconnect():
    app.monitor._running = True   # pretend monitoring is live
    set_field("obs_host", "192.168.1.50")
    set_field("obs_port", "4456")

    beat["last"] = time.perf_counter()

    def tick():
        now = time.perf_counter()
        beat["worst"] = max(beat["worst"], now - beat["last"])
        beat["last"] = now
        beat["ticks"] += 1
        app.root.after(50, tick)

    tick()
    started = time.perf_counter()
    app._save_settings()
    elapsed = time.perf_counter() - started

    check("saving OBS settings returns immediately", elapsed < 0.4,
          f"{elapsed * 1000:.0f} ms")
    check("the OBS client was repointed",
          (app.obs.host, app.obs.port) == ("192.168.1.50", 4456),
          (app.obs.host, app.obs.port))
    check("the sidebar shows the new endpoint",
          app.bg.itemcget(app._obs_card_sub, "text") == "192.168.1.50:4456",
          app.bg.itemcget(app._obs_card_sub, "text"))

    def assert_after_connect():
        check("the reconnect actually ran", app.obs.connect_calls >= 1,
              app.obs.connect_calls)
        check("the UI stayed live through the blocking connect",
              beat["ticks"] > 15 and beat["worst"] < 0.5,
              f"{beat['ticks']} beats, worst gap {beat['worst'] * 1000:.0f} ms")
        case_reconnect_mid_connect()

    app.root.after(1600, assert_after_connect)


# ---- repointing OBS mid-connect must still come back up --------------
def case_reconnect_mid_connect():
    """autostart() is a no-op while a connect attempt is in flight, and that
    attempt resolves against the _abort_connect that _stop() sets - so a naive
    stop-then-start here would leave monitoring off permanently."""
    app.monitor._running = True
    app._connecting = True          # pretend an attempt is mid-flight
    before = app.obs.connect_calls
    set_field("obs_host", "10.0.0.9")
    app._save_settings()
    check("no connect while one is still in flight",
          app.obs.connect_calls == before, app.obs.connect_calls)

    def release():
        app._connecting = False     # the in-flight attempt finishes

    def assert_recovered():
        check("monitoring is restarted once the flight lands",
              app.obs.connect_calls > before, app.obs.connect_calls)
        check("nothing escaped into a Tk callback", not callback_errors,
              callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")
        app.root.quit()

    app.root.after(200, release)
    app.root.after(900, assert_recovered)


def run():
    case_form_reflects_config()
    case_validation()
    case_live_apply()
    case_restart_notice()
    case_reload_on_visit()
    case_obs_reconnect()


app.root.after(50, run)
app.root.after(20000, app.root.quit)  # safety net so a hang can't block forever
app.root.mainloop()

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<52} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
