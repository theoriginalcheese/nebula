"""Aurora UI mockup parity — the strings and chrome docs/dashboard*.png encode.

These are the non-negotiable labels from the Nebula UI Mockups design (frame 1b
and the recording/paused hero states). If a redesign changes them on purpose,
update the mockup screenshots and this file together.

    python tests/test_mockup_parity.py
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import config as config_module, gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None
config_module.save_config = lambda *a, **k: None

from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import (
    AppWindow, WIDTH, HEIGHT, SIDEBAR_W, VIEW_TITLES,
)

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


cfg = load_config()
# Exercise the mockup's OneDrive Sync-tile happy path (legacy sync_folder).
cfg["sync_folder"] = "OneDrive/ObsAutoFolder"
cfg["github_gamedata_repo"] = ""
cfg["github_token"] = ""

app = AppWindow(cfg, Classifier(), on_close_to_tray=lambda: None)
app.root.withdraw()

callback_errors = []
app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
    "".join(traceback.format_exception(t, v, tb))
)

# ---- shell geometry (frame 1b) ------------------------------------------
check("shell width is 1180 design units", WIDTH == 1180, WIDTH)
check("shell height is 760 design units", HEIGHT == 760, HEIGHT)
check("sidebar is 236 design units", SIDEBAR_W == 236, SIDEBAR_W)

# ---- workspace nav ------------------------------------------------------
expected_views = ("dashboard", "recordings", "games", "activity", "macropad", "settings")
check("all six workspace destinations exist",
      tuple(VIEW_TITLES) == expected_views, list(VIEW_TITLES))
for name in expected_views:
    app._show_view(name)
    check(f"nav opens {name}", app._current_view == name, app._current_view)

# ---- hero copy from the recording / paused mockups ----------------------
hero_copy = {
    "recording": ("REC", "Now recording · auto-detected"),
    "paused": ("PAUSED", "Idle — auto-paused, resumes on input"),
    "watching": ("WATCHING", "Monitoring · auto-records on launch"),
    "offline": ("OFFLINE", "OBS not connected"),
}
for state, (badge, sub) in hero_copy.items():
    app._show_view("dashboard")
    app._set_hero_state(state)
    got_badge = app.bg.itemcget(app._hero_badge_text, "text")
    got_sub = app.bg.itemcget(app._hero_sub_id, "text")
    check(f"hero {state} badge", got_badge == badge, got_badge)
    check(f"hero {state} subtitle", got_sub == sub, got_sub)

app._set_hero_state("recording")
app._current_game = "Zenless Zone Zero"
app._set_hero_state("recording")
check("recording preview caption",
      app.bg.itemcget(app._preview_info_id, "text") == "Game Capture → Zenless Zone Zero",
      app.bg.itemcget(app._preview_info_id, "text"))
app._set_hero_state("paused")
check("paused preview caption",
      app.bg.itemcget(app._preview_info_id, "text") == "Capture held — paused",
      app.bg.itemcget(app._preview_info_id, "text"))
check("paused transport says Resume",
      "Resume" in app.pause_btn.cget("text"), app.pause_btn.cget("text"))
app._set_hero_state("recording")
check("recording transport says Pause",
      "Pause" in app.pause_btn.cget("text"), app.pause_btn.cget("text"))
check("stop/record button present",
      "Stop" in app.record_toggle_btn.cget("text")
      or "Record" in app.record_toggle_btn.cget("text"),
      app.record_toggle_btn.cget("text"))

# ---- sidebar monitoring switch (mockup pill toggle) ---------------------
check("monitoring switch track exists", hasattr(app, "_mon_switch_track"))
check("monitoring switch knob exists", hasattr(app, "_mon_switch_knob"))
app._set_monitoring(True)
check("monitoring on label",
      app.bg.itemcget(app._mon_label, "text") == "Monitoring on",
      app.bg.itemcget(app._mon_label, "text"))
app._set_monitoring(False)
check("monitoring off label",
      app.bg.itemcget(app._mon_label, "text") == "Monitoring off",
      app.bg.itemcget(app._mon_label, "text"))

# ---- Sync tile mockup happy path ----------------------------------------
app._show_view("dashboard")
app._refresh_sync_tile()
check("OneDrive sync_folder paints OneDrive",
      app.bg.itemcget(app._stat_sync_val, "text") == "OneDrive",
      app.bg.itemcget(app._stat_sync_val, "text"))
check("sync sub says synced when configured",
      app.bg.itemcget(app._stat_sync_sub, "text") == "synced",
      app.bg.itemcget(app._stat_sync_sub, "text"))

# ---- Settings is a real editor (not the old read-only stub) -------------
app._show_view("settings")
check("settings form has widgets",
      hasattr(app, "_settings_widgets") and bool(app._settings_widgets),
      len(getattr(app, "_settings_widgets", {})))
check("settings form covers every editable field",
      set(app._settings_widgets) == {f.key for f in __import__(
          "obsauto.settings_spec", fromlist=["FIELDS"]).FIELDS},
      sorted(set(app._settings_widgets) ^ {f.key for f in __import__(
          "obsauto.settings_spec", fromlist=["FIELDS"]).FIELDS}))
stub = "Editing these in the app isn't implemented yet"
# Save/Revert are CTkButtons (window items), not canvas text — hunt widgets.
button_labels = []
for child in app.root.winfo_children():
    try:
        button_labels.append(child.cget("text"))
    except Exception:
        pass
check("settings has Save changes action",
      "Save changes" in button_labels and "Revert" in button_labels,
      [t for t in button_labels if t])
settings_texts = []
for item in app.bg.find_withtag("view_settings"):
    try:
        settings_texts.append(app.bg.itemcget(item, "text"))
    except Exception:
        pass
check("settings no longer shows the read-only stub",
      not any(stub in (t or "") for t in settings_texts),
      next((t for t in settings_texts if stub in (t or "")), "clean"))

# ---- Macropad stays deliberately empty ----------------------------------
app._show_view("macropad")
mac_texts = []
for item in app.bg.find_withtag("view_macropad"):
    try:
        mac_texts.append(app.bg.itemcget(item, "text"))
    except Exception:
        pass
check("macropad stays empty on purpose",
      any("deliberately empty" in (t or "").lower() or "not wired" in (t or "").lower()
          for t in mac_texts),
      mac_texts[:3])

check("no callback exceptions", not callback_errors,
      callback_errors[0].strip().splitlines()[-1] if callback_errors else "clean")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<52} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")

app.root.destroy()
sys.exit(0 if passed_all else 1)
