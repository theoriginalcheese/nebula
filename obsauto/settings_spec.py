"""What the Settings view can edit, described once.

Kept out of gui.py deliberately. Two reasons:

- Parsing and validation are pure functions here, so they can be tested without
  a desktop session (gui.py needs a real Tk window for anything at all).
- Adding a setting should be one entry in FIELDS, not another hand-positioned
  row of canvas coordinates. The view walks this list and renders whatever it
  finds, so the two can't drift out of step.

This covers `config.DEFAULTS` exactly - every key there has a field, and every
field names a real key (a test asserts both). `dashboard_grid` is the one config
key not represented, and it isn't in DEFAULTS either: it's written by the
dashboard's own Customise mode, which owns it.
"""

import os

from . import design_v3

# ---- field kinds ----------------------------------------------------------
# text          free string
# path          free string that names a file/folder; a missing one is a
#               warning, never an error (a NAS or removable drive is allowed to
#               be absent right now and appear later)
# secret        free string, masked in the UI (tokens/passwords)
# int           whole number, optionally range-bounded
# optional_int  whole number or blank (blank means None, i.e. "unset")
# list          comma-separated strings -> list[str]
# choice        one of `choices`


class Field:
    __slots__ = ("key", "label", "kind", "group", "hint", "minimum", "maximum",
                 "choices", "restart")

    def __init__(self, key, label, kind="text", group="", hint="",
                 minimum=None, maximum=None, choices=(), restart=False):
        # `restart` is either False (applies live) or the reason it can't, so
        # the view can say *why* rather than just refusing to be helpful.
        self.key = key
        self.label = label
        self.kind = kind
        self.group = group
        self.hint = hint
        self.minimum = minimum
        self.maximum = maximum
        self.choices = tuple(choices)
        self.restart = restart

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<Field {self.key} ({self.kind})>"


# ---- groups, in the order the view stacks them ---------------------------
GROUPS = (
    ("obs", "OBS connection",
     "obs-websocket v5. The port and password come from OBS's own "
     "Tools \u2192 WebSocket Server Settings."),
    ("recording", "Recording",
     "Where clips land, and how eagerly Nebula starts and pauses them."),
    ("replay", "Instant replay",
     "OBS keeps the last few seconds in RAM. One key writes them to disk, with "
     "no session recording running. Replays never get auto-culled."),
    ("hotkey", "Hotkey",
     "One global key toggles monitoring from anywhere, even mid-game."),
    ("gamesync", "Game list sync",
     "Classifications live in a private GitHub repo so a game you sort on one "
     "machine is known on the others. Blank repo or token = local only."),
    ("offload", "NAS offload",
     "Finished clips are copied to the NAS and byte-verified before anything "
     "local is touched."),
    ("storage", "Storage",
     "How long the disk lasts at your current rate, and the two things that "
     "change it. Culling moves files to the Recycle Bin - never a hard delete."),
    ("appearance", "Appearance",
     "Six accents over one fixed ground, plus how tight, how round and how "
     "alive the shell is. Every one of these is an override of a token that "
     "already exists, so nothing here can invent a colour."),
    ("updates", "Updates",
     "Keep this install in sync with GitHub. Packaged builds check Releases; "
     "source checkouts use a one-line git pull script."),
    ("legacy", "Legacy",
     "Superseded, kept so an older config still resolves."),
)

FIELDS = (
    # ---- OBS ----
    Field("obs_host", "Host", "text", "obs",
          hint="Machine running obs-websocket. Normally localhost."),
    Field("obs_port", "Port", "int", "obs", minimum=1, maximum=65535,
          hint="OBS's WebSocket server port (4455 unless you changed it)."),
    Field("obs_password", "Password", "secret", "obs",
          hint="Blank unless you ticked authentication in OBS."),
    Field("obs_path", "OBS executable", "path", "obs",
          hint="Used to launch OBS when it isn't already running. Skipped "
               "silently if this path doesn't exist here."),
    Field("reconnect_interval_seconds", "Reconnect every", "int", "obs",
          minimum=1, maximum=3600,
          hint="Seconds between retries while OBS is unreachable."),

    # ---- Recording ----
    Field("recording_root", "Recording root", "path", "recording",
          hint="Per-game folders are created in here."),
    Field("idle_timeout_seconds", "Idle timeout", "int", "recording",
          minimum=1, maximum=3600,
          hint="Seconds of no input before recording auto-pauses. The "
               "dashboard's Idle timeout slider writes this same value."),
    Field("min_clip_seconds", "Minimum clip", "int", "recording",
          minimum=0, maximum=3600,
          hint="Clips shorter than this are deleted when they finish \u2014 "
               "catches a game window that only flickered. 0 keeps everything."),
    Field("poll_interval_seconds", "Poll interval", "int", "recording",
          minimum=1, maximum=60,
          hint="Seconds between foreground-window checks."),

    # ---- Instant replay (7a) ----
    Field("replay_enabled", "Instant replay", "bool", "replay",
          hint="Arm OBS's replay buffer so the last few seconds can be saved "
               "on a key press."),
    Field("replay_seconds", "Buffer length", "int", "replay",
          minimum=10, maximum=300,
          hint="Seconds held in RAM. Roughly (bitrate ÷ 8) × seconds "
               "× 1.1 megabytes — shown live on the dashboard module."),
    Field("replay_hotkey", "Save key", "text", "replay",
          hint="Pressed anywhere, including inside a game. Bound by scan code, "
               "so it works whatever the keyboard layout."),
    Field("replay_hotkey_scancode", "Save key scan code", "optional_int", "replay",
          minimum=0, maximum=65535,
          hint="Optional. Binds this exact physical key rather than resolving "
               "the name (67 is F9). Blank = bind by name."),
    Field("replay_subfolder", "Replay folder", "text", "replay",
          hint="Created inside each game's folder. Replays land here rather "
               "than beside full recordings."),
    Field("replay_arm_with_monitoring", "Arm with monitoring", "bool", "replay",
          hint="Arm the buffer whenever monitoring is on, rather than waiting "
               "for a game to be detected."),
    Field("replay_only_for_games", "Games only", "bool", "replay",
          hint="Keep the buffer disarmed while the foreground app isn't a "
               "game, so it isn't holding your desktop in RAM."),
    Field("keep_alive_audio_processes", "Audio keep-alive", "list", "recording",
          hint="Comma-separated executables. While one of them is producing "
               "sound (friends talking in Discord), recording won't auto-pause "
               "on idle. Empty disables the keep-alive."),

    # ---- Storage (7c) ----
    Field("cull_after_days", "Cull clips older than", "int", "storage",
          minimum=0, maximum=3650,
          hint="Days. Clips older than this can be culled to the Recycle Bin "
               "from the Storage card. 0 turns culling off entirely."),
    Field("cull_keep_marked", "Keep marked clips", "bool", "storage",
          hint="A marked clip is never culled. Replays are never culled "
               "either, whatever this says."),
    Field("cull_auto", "Cull without asking", "bool", "storage",
          hint="Off by default and worth leaving off — with it on, the cull "
               "runs on its own instead of showing you the count first."),
    Field("disk_warn_days", "Warn when days left below", "int", "storage",
          minimum=0, maximum=365,
          hint="One toast at this threshold, at most once a day. 0 = silent."),
    Field("disk_block_below_gb", "Refuse to record below", "int", "storage",
          minimum=0, maximum=10000,
          hint="Gigabytes free. Below this the hero card won't start a "
               "recording — better than one that dies mid-session."),

    # ---- Hotkey ----
    Field("toggle_hotkey", "Toggle key", "text", "hotkey",
          hint="A keyboard-package binding such as f12 or ctrl+alt+r. Also "
               "what's drawn on the keycap in the nav rail. Blank = no hotkey."),
    Field("palette_hotkey", "Command palette", "text", "hotkey",
          hint="Opens the palette from anywhere, including over a game. "
               "Blank = no global key."),
    Field("toggle_hotkey_scancode", "Scan code", "optional_int", "hotkey",
          minimum=0, maximum=65535,
          hint="Optional. Binds this exact physical key instead of resolving "
               "the name \u2014 needed when one character maps to several scan "
               "codes (41 is the backtick key). Blank = bind by name."),

    # ---- GitHub game-list sync ----
    Field("github_gamedata_repo", "Repo", "text", "gamesync",
          hint="owner/name of the private repo holding games.json."),
    Field("github_gamedata_path", "Path in repo", "text", "gamesync",
          hint="File path within that repo."),
    Field("github_token", "Token", "secret", "gamesync",
          hint="Needs repo scope. Stays in this machine's config.json \u2014 "
               "never committed, never carried in the synced games.json."),

    # ---- NAS offload ----
    Field("nas_offload_root", "NAS root", "path", "offload",
          hint="Destination for finished clips, e.g. Z:/OBS Recordings or a "
               "UNC path. Blank turns offload off. Safe to set before the NAS "
               "is reachable \u2014 clips queue and retry."),
    Field("nas_offload_mode", "Mode", "choice", "offload",
          choices=("copy", "move"),
          hint="copy keeps both copies. move frees local space, but only ever "
               "deletes the original after the NAS copy is SHA-256 verified."),

    # ---- Legacy ----
    # ---- Appearance ----
    # Choice, never text: the menu IS the constraint. A free hex field would
    # let the accent land somewhere it cannot be read against the ground, and
    # then the ground is a support question rather than a design decision.
    Field("appearance_accent", "Accent", "choice", "appearance",
          choices=tuple(design_v3.ACCENTS),
          hint="The one hue that leads. Ember still means a real "
               "disconnection, whichever you pick."),
    Field("appearance_density", "Density", "choice", "appearance",
          choices=tuple(design_v3.DENSITIES),
          hint="Padding and gaps only - the type scale does not move."),
    Field("appearance_radius", "Corners", "choice", "appearance",
          choices=tuple(design_v3.RADII),
          hint="Cards stay concentric at every setting: the core radius is "
               "derived from the shell, not scaled beside it."),
    Field("appearance_motion", "Background motion", "choice", "appearance",
          choices=tuple(design_v3.MOTION_MODES),
          hint="Off pauses the aurora drift, the star wind and the pointer "
               "spotlight. Worth having on a GPU that is also encoding."),

    Field("holdoff_same_game_seconds", "Re-record prompt delay", "int", "recording",
          minimum=0, maximum=3600,
          hint="After you hit Stop, wait this many seconds before asking to "
               "record the same game again. A different game asks as soon as "
               "it is detected. 0 = ask immediately for the same game too."),

    Field("sync_folder", "Sync folder", "path", "legacy",
          restart="the classifier resolves its data path at launch",
          hint="Old folder-based sync for games.json, superseded by the GitHub "
               "sync above \u2014 leave blank. A relative path resolves against "
               "your home folder."),
)

BY_KEY = {field.key: field for field in FIELDS}


def fields_in(group):
    return [field for field in FIELDS if field.group == group]


def _unquote(text):
    """Drop one matching pair of surrounding quotes.

    Windows Explorer's "Copy as path" yields `"D:\\OBS Recordings"`, and a
    pasted path keeping its quotes would break every os.path call downstream
    in a way that's hard to spot in a text field."""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1].strip()
    return text


def parse(field, raw):
    """Turn one widget's text into a config value.

    Returns (value, error). `error` is a lower-case fragment meant to be read
    after the field's label ("Port: needs a whole number"), or None on success.
    """
    text = _unquote((raw or "").strip())

    if field.kind in ("text", "path", "secret"):
        return text, None

    if field.kind == "list":
        return [part.strip() for part in text.split(",") if part.strip()], None

    if field.kind == "choice":
        for choice in field.choices:
            if choice.lower() == text.lower():
                return choice, None
        return None, "must be " + " or ".join(field.choices)

    if field.kind == "optional_int" and not text:
        return None, None

    try:
        value = int(text, 10)
    except ValueError:
        return None, "needs a whole number"
    if field.minimum is not None and value < field.minimum:
        return None, f"can't be below {field.minimum}"
    if field.maximum is not None and value > field.maximum:
        return None, f"can't be above {field.maximum}"
    return value, None


def render(field, value):
    """The text a widget should show for a stored config value."""
    if field.kind == "list":
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(v) for v in value)
        return "" if value is None else str(value)
    if value is None:
        return ""
    return str(value)


def parse_all(raw_values):
    """Parse a {key: text} mapping. Returns (values, errors), where `errors` is
    [(field, message)] and `values` holds only the keys that parsed cleanly, so
    a caller can report every problem at once instead of one per attempt."""
    values, errors = {}, []
    for field in FIELDS:
        if field.key not in raw_values:
            continue
        value, error = parse(field, raw_values[field.key])
        if error:
            errors.append((field, error))
        else:
            values[field.key] = value
    return values, errors


def missing_paths(values):
    """Path fields naming something that isn't there (yet).

    Advisory only, never an error: a NAS share, a mapped drive or an external
    recording disk is allowed to be absent at the moment you configure it, and
    refusing the setting would make Nebula impossible to set up ahead of
    mounting - which the offloader is explicitly built to tolerate."""
    missing = []
    for field in FIELDS:
        if field.kind != "path":
            continue
        value = values.get(field.key)
        if not value:
            continue
        path = value
        if not os.path.isabs(path):
            # A relative sync_folder resolves against the user's home dir, the
            # same way main.py._apply_sync_folder() resolves it.
            path = os.path.join(os.path.expanduser("~"), path)
        if not os.path.exists(path):
            missing.append(field)
    return missing


def restart_required(keys):
    """Which of `keys` only take effect after a restart."""
    return [BY_KEY[key] for key in keys if key in BY_KEY and BY_KEY[key].restart]


# Keys that live in config.json but are state rather than settings, so they
# deliberately have no field. Declared here (rather than just being absent) so
# the "every DEFAULTS key is editable" test still catches a setting that was
# added and then forgotten - the exemption has to be written down to apply.
INTERNAL_KEYS = frozenset({
    "ffmpeg_notice_dismissed",   # 7f: the one-time "install ffmpeg" row
    "dashboard_layout",          # 6.8: written by Customise, not by hand
    "dashboard_grid",            # the retired interim key
})
