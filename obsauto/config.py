import json
import os

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
