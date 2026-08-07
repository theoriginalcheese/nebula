import json
import os

from . import design_v3
from .paths import APP_DIR

CONFIG_FILE = os.path.join(APP_DIR, "config.json")

DEFAULTS = {
    "obs_host": "localhost",
    "obs_port": 4455,
    "obs_password": "",
    "recording_root": "D:/OBS Recordings",
    "idle_timeout_seconds": 4,
    "poll_interval_seconds": 1,
    # Clips shorter than this get auto-deleted right after they finish -
    # catches junk from a game window that briefly flickered rather than an
    # actual play session.
    "min_clip_seconds": 10,
    # ---- instant replay (spec 7a) ----
    # OBS's own rolling RAM buffer. Nebula arms it, asks for the save, and
    # files the result into <recording_root>/<game>/<replay_subfolder>/.
    # Replays deliberately ignore min_clip_seconds - they're intentional.
    "replay_enabled": True,
    "replay_seconds": 30,               # 10-300
    "replay_hotkey": "f9",
    "replay_hotkey_scancode": 67,       # bound by scan code, like the toggle
    "replay_subfolder": "Replays",
    "replay_arm_with_monitoring": True,
    "replay_only_for_games": True,
    # 7f's one-time "ffmpeg isn't installed" row in Settings. Not a Field -
    # it's a dismissal record, not something to edit.
    "ffmpeg_notice_dismissed": False,
    # ---- storage forecast + cull (spec 7c) ----
    # The forecast states a date rather than a percentage. Culling moves files
    # to the Recycle Bin, never unlinks, always excludes replays and marked
    # clips, and never runs while recording.
    "cull_after_days": 30,            # 0 = off
    "cull_keep_marked": True,
    "cull_auto": False,               # ask first, always
    "disk_warn_days": 3,              # one toast at this threshold, once a day
    "disk_block_below_gb": 20,        # below this the hero refuses to start
    # ---- appearance (the other half of customise) ----
    # Customise mode makes the layout yours; these make the surface it sits on
    # yours. Each is a CSS-variable override on :root over tokens that already
    # exist - see design_v3.ACCENTS / DENSITIES / RADII / MOTION_MODES for the
    # menus and why they are menus rather than free fields. The ground colours
    # are deliberately not in here: six accents over one ground is a design
    # system, a colour picker is a support burden.
    "appearance_accent": design_v3.ACCENT_DEFAULT,
    "appearance_density": design_v3.DENSITY_DEFAULT,
    "appearance_radius": design_v3.RADIUS_DEFAULT,
    "appearance_motion": design_v3.MOTION_DEFAULT,
    # ---- command palette (spec 7e) ----
    "palette_hotkey": "ctrl+k",       # blank = no global palette key
    # Legacy folder-based sync for games.json / steam_appid_cache.json (was
    # OneDrive). Superseded by the GitHub sync below, which is instant and
    # reliable; leave blank. Kept so an old config still resolves.
    "sync_folder": "",
    # ---- game-list sync via GitHub (instant cross-device) ----
    # A private repo Nebula pulls on startup and pushes to after each
    # classification change. All three blank = feature off (local only).
    # github_token is kept in this local, gitignored config and never synced.
    "github_token": "",
    "github_gamedata_repo": "",   # "owner/name", e.g. "you/nebula-gamedata"
    "github_gamedata_path": "games.json",
    # ---- recording offload to the NAS ----
    # After a clip is finalized it's copied to nas_offload_root/<game>/ and
    # byte-verified (SHA-256) before, in "move" mode, the local original is
    # removed. Blank root = feature off. The NAS path must be reachable as a
    # normal filesystem path (a mapped drive like "Z:/OBS Recordings" or a UNC
    # path); set it per-machine. "copy" keeps both copies, "move" frees local.
    "nas_offload_root": "",
    "nas_offload_mode": "copy",
    # Hours between automatic backlog scans when the NAS path is reachable
    # (Tailscale online / mapped drive up). 0 = manual Sync now only; the
    # per-clip queue from finished recordings still drains either way.
    "nas_offload_interval_hours": 24,
    # ---- Moonlight remote play (client) ----
    # Nebula launches Moonlight's CLI; it does not embed the stream. Blank
    # host disables Connect. App is usually "Desktop" for a full session.
    "moonlight_path": "C:/Program Files/Moonlight Game Streaming/Moonlight.exe",
    "moonlight_host": "",
    "moonlight_app": "Desktop",
    "moonlight_display_mode": "borderless",
    # Used to auto-launch OBS if it isn't already running (at startup, and
    # again if it crashes/closes mid-session). Skipped silently if this path
    # doesn't exist on this machine - just set it per-machine if different.
    "obs_path": "C:/Program Files/obs-studio/bin/64bit/obs64.exe",
    # How often (seconds) to retry launching+connecting to OBS while
    # disconnected, either at startup or after an unexpected drop.
    "reconnect_interval_seconds": 10,
    # While any of these apps is producing audio (e.g. friends talking in a
    # Discord voice call), recording won't auto-pause even if you're locally
    # idle. Empty list disables the keep-alive.
    "keep_alive_audio_processes": ["discord.exe"],
    # Global hotkey that toggles monitoring on/off from anywhere (even mid-
    # game). A `keyboard`-package binding string, e.g. "f12" or "ctrl+alt+r".
    # This is also the label drawn on the keycap hint in the title bar.
    # Empty = no hotkey.
    "toggle_hotkey": "`",
    # Optional: bind this exact *physical* key (scan code) instead of resolving
    # `toggle_hotkey` as text. Needed when a character maps to more than one
    # scan code - "`" resolves to both 41 (the real backtick key) and 40, and 40
    # is also the apostrophe key, so binding by name would suppress apostrophes
    # system-wide. 41 = the backtick/grave key left of "1". None = bind by name.
    "toggle_hotkey_scancode": 41,
    # After a manual Stop, wait this many seconds before offering "Record
    # again?" for the same still-running game. A different game prompts as
    # soon as it is detected. 0 = prompt for the same game immediately too.
    "holdoff_same_game_seconds": 60,
}


def load_config():
    config = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except (OSError, json.JSONDecodeError):
            pass
    else:
        save_config(config)
    return config


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, sort_keys=True)
