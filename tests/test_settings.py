"""Settings pane - frame 2c and the config-map rules.

    "Writes config.json on blur"      - not per keystroke
    "Show the saved timestamp in the pane header"
    every *_seconds key renders its unit suffix
    "Never silently drop an unknown key - merge over DEFAULTS and keep the rest"

Saves are intercepted, so this never touches the real config.json.

    python tests/test_settings.py
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto import design_v3 as dv
from obsauto.classifier import Classifier
from obsauto.config import DEFAULTS, load_config
from obsauto.gui import AppWindow

saved = []
config_module.save_config = lambda cfg, *a, **k: saved.append(dict(cfg))

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


config = load_config()
# A key this app has never heard of - it must survive every write.
config["some_future_key"] = "keep me"

app = AppWindow(config, Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()
callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb)))


def settle(ms=120):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.005)


app._show_view("settings")
settle(200)


def field_texts():
    out = []

    def walk(w):
        try:
            t = w.cget("text")
            if t:
                out.append(str(t))
        except Exception:
            pass
        for c in w.winfo_children():
            walk(c)

    for c in app._settings_host.winfo_children():
        walk(c)
    return out


# ---- sections ----
check("five sections", list(app._settings_nav) == dv.SETTINGS_SECTIONS,
      list(app._settings_nav))
check("opens on Connection", app._settings_section == "Connection",
      app._settings_section)

texts = field_texts()
check("field labels rendered", "Host" in texts, texts[:6])
# "the mono config-key labels under each field ... are part of the design"
check("config key shown under the label", "obs_host" in texts, texts[:8])
check("only this section's fields", "recording_root" not in texts, texts)

# ---- every *_seconds field carries its unit ----
app._show_settings_section("Idle & audio")
settle(120)
texts = field_texts()
check("idle timeout key shown", "idle_timeout_seconds" in texts, texts[:8])
check("seconds unit rendered", "seconds" in texts, texts[:12])
mapped = [k for _l, k, s, _u in dv.CONFIG_MAP if s == "Idle & audio"]
check("section shows all its mapped keys", all(k in texts for k in mapped), mapped)

# ---- write on blur, not per keystroke ----
app._show_settings_section("Storage")
settle(120)
widget, kind = app._settings_fields["recording_root"]
before = len(saved)
widget.delete(0, "end")
widget.insert(0, "E:/Clips")
settle(80)
check("typing alone does not save", len(saved) == before, len(saved) - before)
check("config untouched until blur", app.config["recording_root"] != "E:/Clips",
      app.config["recording_root"])

app._settings_commit("recording_root")     # what <FocusOut> binds to
settle(80)
check("blur writes the value", app.config["recording_root"] == "E:/Clips",
      app.config["recording_root"])
check("blur saved the file", len(saved) == before + 1, len(saved) - before)

# ---- saved timestamp in the header ----
sub = app.bg.itemcget(app._settings_sub, "text")
check("header shows the saved timestamp", "Saved" in sub, sub)
check("timestamp recorded", bool(app._settings_saved_at), app._settings_saved_at)

# ---- unchanged value writes nothing ----
before = len(saved)
app._settings_commit("recording_root")
check("re-commit of an unchanged value is a no-op", len(saved) == before,
      len(saved) - before)

# ---- ints stay ints; junk is rejected, not written ----
app._show_settings_section("Idle & audio")
settle(120)
widget, _ = app._settings_fields["idle_timeout_seconds"]
widget.delete(0, "end")
widget.insert(0, "9")
app._settings_commit("idle_timeout_seconds")
check("int field keeps its type", app.config["idle_timeout_seconds"] == 9,
      repr(app.config["idle_timeout_seconds"]))

before_val = app.config["idle_timeout_seconds"]
before = len(saved)
widget.delete(0, "end")
widget.insert(0, "not a number")
app._settings_commit("idle_timeout_seconds")
check("junk in an int field is refused", app.config["idle_timeout_seconds"] == before_val,
      repr(app.config["idle_timeout_seconds"]))
check("refused edit writes nothing", len(saved) == before, len(saved) - before)
check("refused edit restores the old text", widget.get() == str(before_val), widget.get())

# ---- list field round-trips ----
widget, kind = app._settings_fields["keep_alive_audio_processes"]
check("list field renders comma-separated", "," in widget.get() or widget.get(),
      widget.get())
widget.delete(0, "end")
widget.insert(0, "discord.exe, teamspeak.exe")
app._settings_commit("keep_alive_audio_processes")
check("list field parses back to a list",
      app.config["keep_alive_audio_processes"] == ["discord.exe", "teamspeak.exe"],
      app.config["keep_alive_audio_processes"])

# ---- password is masked ----
app._show_settings_section("Connection")
settle(120)
widget, _ = app._settings_fields["obs_password"]
check("password field is masked", widget.cget("show") == "*", widget.cget("show"))

# ---- never drop an unknown key ----
last = saved[-1]
check("unknown key survives the write", last.get("some_future_key") == "keep me",
      last.get("some_future_key"))
missing = [k for k in DEFAULTS if k not in last]
check("every DEFAULTS key survives the write", not missing, missing)

# ---- every mapped control exists somewhere ----
seen = set()
for section in dv.SETTINGS_SECTIONS:
    app._show_settings_section(section)
    settle(60)
    seen |= set(app._settings_fields)
mapped_all = {k for _l, k, _s, _u in dv.CONFIG_MAP}
check("every CONFIG_MAP key has a field", mapped_all <= seen,
      sorted(mapped_all - seen))

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<46} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
