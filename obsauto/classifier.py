"""Game vs. not-a-game classification.

Hybrid approach (per user's choice): Steam Store metadata is authoritative
and automatic for anything installed via Steam; anything else (Epic,
standalone .exe, emulators) falls back to a one-time manual prompt whose
answer is remembered forever. No local/paid AI involved.
"""

import json
import os
import re
import threading
import time

from . import steam_scanner
from .paths import APP_DIR

DATA_FILE = os.path.join(APP_DIR, "games.json")

# Common background/launcher/utility processes we never want to prompt about.
# Keeps the "ask me once" flow from firing on every browser tab or launcher.
DENYLIST = {
    "explorer.exe", "steam.exe", "steamwebhelper.exe", "steamservice.exe",
    "epicgameslauncher.exe", "epicwebhelper.exe", "eossoverlay.exe",
    "goggalaxy.exe", "goggalaxycommunication.exe",
    "battle.net.exe", "battlenethelper.exe",
    "discord.exe", "discordptb.exe", "discordcanary.exe",
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
    "obs64.exe", "obs32.exe", "obs-studio.exe",
    "code.exe", "cursor.exe", "windowsterminal.exe", "cmd.exe", "powershell.exe",
    "pwsh.exe", "taskmgr.exe", "searchhost.exe", "textinputhost.exe",
    "shellexperiencehost.exe", "applicationframehost.exe", "systemsettings.exe",
    "nvidia share.exe", "nvcontainer.exe", "rtss.exe", "msiafterburner.exe",
    "python.exe", "pythonw.exe",
    "unitycrashhandler64.exe", "unitycrashhandler32.exe", "createdump.exe",
    "vc_redist.x64.exe", "vc_redist.x86.exe",
    "wallpaper32.exe", "wallpaper64.exe", "installer.exe", "install.exe",
    "msedgewebview2.exe", "widgets.exe", "widgetservice.exe",
    "armourycrate.exe", "armourycrateservice.exe", "aurasyncutility.exe",
    "blender.exe",
    # Source engine SDK/map-compiler tools bundled with Source-engine games -
    # never the game itself.
    "vbsp.exe", "vrad.exe", "vvis.exe", "vconsole2.exe",
}

# Bundled installer/anticheat/crash-reporter helpers found *inside* legitimate
# game folders (e.g. Astroneer ships ue4prereqsetup_x64.exe, skate. ships
# EAAntiCheat.Installer.exe) - matched by substring rather than exact name
# since every publisher names these slightly differently. Without this,
# proactively registering "every .exe in a verified game's folder" wrongly
# tags these helpers as the game itself.
INSTALLER_HELPER_PATTERNS = (
    "redist", "prereq", "crashreport", "crashhandler", "crashpad", "anticheat",
    "dxsetup", "directx", "vcredist", "ndp4", "dotnetfx", "dotnet",
    "connectinstaller", "battleye", "easyanticheat", "_setup", "setup_",
    "uninst", "ggsetup", "gguninst",
)


def _looks_like_installer_helper(basename):
    b = basename.lower()
    return any(pattern in b for pattern in INSTALLER_HELPER_PATTERNS)


class Classifier:
    def __init__(self, on_log=None, on_saved=None):
        self.on_log = on_log or (lambda msg: None)
        # Fired (best-effort) right after the local games.json is written, so a
        # sync layer can push the change up to GitHub. Kept decoupled: the
        # classifier neither knows nor cares what's on the other end.
        self.on_saved = on_saved or (lambda data: None)
        self._lock = threading.Lock()
        self._data = self._load()
        self._steam_index = {}  # installdir_lower -> {"name", "appid"} (or legacy str)
        self._steam_index_loaded = False
        self._pending_manual = {}  # key -> (basenames, suggested_name) awaiting a GUI prompt
        self._in_review = set()  # keys currently being handled by the GUI
        # Frame 2d "seen 4×": distinct notice bursts, not poll ticks. Debounced
        # so a game left in the foreground doesn't inflate the counter every
        # second while the review card is sitting there.
        self._sightings = {}  # review key -> count
        self._sighting_at = {}  # review key -> last count bump (monotonic)
        self._sighting_gap = 120.0  # seconds between countable re-notices

    def log(self, msg):
        self.on_log(msg)

    # ---- persistence ----
    def _load(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data.setdefault("games", {})
                    data.setdefault("non_games", {})
                    return data
            except (OSError, json.JSONDecodeError):
                self.log(f"[Classifier] {DATA_FILE} was corrupt, starting fresh.")
        return {"games": {}, "non_games": {}}

    def _save(self):
        # Merge with what's currently on disk before writing, rather than
        # blindly overwriting - if this file lives in a synced folder
        # (OneDrive) shared with another machine, a plain overwrite would
        # silently discard whatever the other machine classified since this
        # process started.
        on_disk = {"games": {}, "non_games": {}}
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    on_disk = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        self._data = {
            "games": {**on_disk.get("games", {}), **self._data["games"]},
            "non_games": {**on_disk.get("non_games", {}), **self._data["non_games"]},
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)
        try:
            self.on_saved(self._data)
        except Exception as exc:
            self.log(f"[Sync] on_saved hook failed: {exc}")

    def snapshot(self):
        """A copy of the current classification data, safe to hand to the sync
        layer without it seeing mid-mutation state."""
        with self._lock:
            return {
                "games": dict(self._data.get("games", {})),
                "non_games": dict(self._data.get("non_games", {})),
            }

    def absorb(self, external):
        """Merge a classification set pulled from elsewhere (GitHub) into the
        local one. Local entries win on conflict - a decision made on this
        machine isn't second-guessed by the remote. Returns how many new
        entries were added, and persists if anything changed."""
        if not external:
            return 0
        with self._lock:
            before = len(self._data.get("games", {})) + len(self._data.get("non_games", {}))
            self._data = {
                "games": {**external.get("games", {}), **self._data.get("games", {})},
                "non_games": {**external.get("non_games", {}), **self._data.get("non_games", {})},
            }
            after = len(self._data["games"]) + len(self._data["non_games"])
        added = after - before
        if added:
            self._save()
        return added

    # ---- Steam index (lazy, refreshed on demand) ----
    def refresh_steam_index(self):
        self.log("[Steam] Scanning installed Steam games...")
        self._steam_index = steam_scanner.build_steam_game_index(log=self.log)
        self._steam_index_loaded = True
        self.log(f"[Steam] Found {len(self._steam_index)} Steam game(s).")

    def register_all_steam_games(self, on_progress=None):
        """Proactively walk every installed Steam app - not just ones
        you've already run - and register real games up front, so their
        folder/classification exists before you ever launch them. Games
        Steam itself confirms (type "game") register automatically; the
        rest get queued for you to confirm instead of being silently marked
        non-game, since Steam's own tagging isn't always right for
        borderline creative/utility software.
        """
        on_progress = on_progress or (lambda name: None)
        manifests = steam_scanner.scan_app_manifests()
        registered = []
        for info in manifests.values():
            on_progress(info["name"])
            install_path = info.get("path")
            if not install_path or not os.path.isdir(install_path):
                continue

            is_game, store_name = steam_scanner.classify_appid(info["appid"], log=self.log)
            display_name = store_name or info["name"]
            appid = info.get("appid")

            exe_basenames = set()
            for _root, _dirs, files in os.walk(install_path):
                for fname in files:
                    if fname.lower().endswith(".exe"):
                        exe_basenames.add(fname.lower())

            unresolved = []
            for basename in exe_basenames:
                with self._lock:
                    already_known = (
                        basename in self._data["games"] or basename in self._data["non_games"]
                    )
                if already_known or basename in DENYLIST:
                    continue
                if _looks_like_installer_helper(basename):
                    self.mark_non_game(basename)
                    continue
                if is_game:
                    self.mark_game(basename, display_name, source="steam", appid=appid)
                    registered.append(basename)
                else:
                    unresolved.append(basename)

            # One review prompt per *app*, not per bundled executable - some
            # apps Steam doesn't tag as "game" (e.g. Wallpaper Engine) ship
            # 20+ helper .exe's, and asking about each individually would be
            # a wall of near-identical popups for a single decision.
            if unresolved and self.queue_app_for_manual_review(display_name, unresolved):
                self.log(f"[Steam] Not sure about {display_name} ({len(unresolved)} exe(s)) - added to review queue.")

        self._steam_index_loaded = True
        return registered

    def _steam_installdir_for_path(self, exe_path):
        """If exe_path lives under .../steamapps/common/<installdir>/..., return installdir."""
        norm = exe_path.replace("\\", "/").lower()
        marker = "/steamapps/common/"
        idx = norm.find(marker)
        if idx == -1:
            return None
        rest = norm[idx + len(marker):]
        return rest.split("/", 1)[0] if rest else None

    # ---- classification ----
    def classify(self, exe_path, proc_name):
        """Return ("game", display_name) / ("non_game", None) / ("unknown", None)."""
        basename = os.path.basename(exe_path).lower() if exe_path else proc_name.lower()

        with self._lock:
            if basename in self._data["games"]:
                return "game", self._data["games"][basename]["display_name"]
            if basename in self._data["non_games"]:
                return "non_game", None

        if basename in DENYLIST or _looks_like_installer_helper(basename):
            self.mark_non_game(basename)
            return "non_game", None

        if exe_path:
            if not self._steam_index_loaded:
                self.refresh_steam_index()
            installdir = self._steam_installdir_for_path(exe_path)
            if installdir and installdir in self._steam_index:
                display_name, appid = self._steam_entry(installdir)
                self.mark_game(basename, display_name, source="steam", appid=appid)
                if appid:
                    self.log(f"[Steam] Matched {basename} -> {display_name} (AppID {appid})")
                return "game", display_name
            if installdir:
                # Installed via Steam but Steam says it's not a "game" (tool/dlc/server)
                self.mark_non_game(basename)
                return "non_game", None

        return "unknown", None

    def _steam_entry(self, installdir):
        """Normalise a steam-index value to (display_name, appid_or_None)."""
        entry = self._steam_index.get(installdir)
        if entry is None:
            return None, None
        if isinstance(entry, str):
            return entry, None
        return entry.get("name") or installdir, entry.get("appid")

    def peek_kind(self, basename):
        """Side-effect-free classification for the watching hero line.

        Returns ``"game"`` / ``"non_game"`` / ``"unknown"`` without queuing
        reviews or writing games.json — the monitor needs this every poll.
        """
        basename = (basename or "").lower()
        if not basename:
            return "unknown"
        with self._lock:
            if basename in self._data["games"]:
                return "game"
            if basename in self._data["non_games"]:
                return "non_game"
        if basename in DENYLIST or _looks_like_installer_helper(basename):
            return "non_game"
        return "unknown"

    def appid_for(self, basename):
        """Steam AppID stored on a game entry, or None."""
        basename = (basename or "").lower()
        with self._lock:
            entry = self._data["games"].get(basename)
        if isinstance(entry, dict):
            return entry.get("appid")
        return None

    def mark_game(self, basename, display_name, source="manual", appid=None):
        basename = basename.lower()
        with self._lock:
            entry = {"display_name": display_name, "source": source}
            if appid:
                entry["appid"] = str(appid)
            else:
                # Keep a previously-known AppID when re-marking the same exe
                # without one (e.g. promote from Not games).
                prev = self._data["games"].get(basename)
                if isinstance(prev, dict) and prev.get("appid"):
                    entry["appid"] = prev["appid"]
            self._data["games"][basename] = entry
            self._data["non_games"].pop(basename, None)
            self._save()
        suffix = f" AppID {appid}" if appid else ""
        self.log(f"[Classifier] {basename} -> game ({display_name}) [{source}]{suffix}")

    def mark_non_game(self, basename):
        basename = basename.lower()
        with self._lock:
            self._data["non_games"][basename] = True
            self._data["games"].pop(basename, None)
            self._save()

    # ---- manual-review queue, drained by the GUI/tray ----
    # Each pending item is keyed by either a single exe basename (the
    # reactive "unrecognized running app" case, where we don't have a real
    # name to suggest) or a Steam display name (the proactive rescan case,
    # where one app can bundle many .exe's - EAAntiCheat, Wallpaper Engine,
    # etc. - and should be asked about once, not once per bundled exe).
    def queue_for_manual_review(self, basename):
        return self._queue_review(basename, [basename], suggested_name=None)

    def queue_app_for_manual_review(self, display_name, basenames):
        return self._queue_review(display_name, basenames, suggested_name=display_name)

    def _queue_review(self, key, basenames, suggested_name):
        with self._lock:
            # Skip anything already queued *or* already being shown to the
            # user right now - otherwise the background monitor thread keeps
            # re-queuing the same app every poll tick for as long as the GUI
            # dialog(s) are open (e.g. while the user is typing a folder
            # name), since classify() still says "unknown" until the answer
            # is actually saved.
            if key in self._pending_manual or key in self._in_review:
                # Still a re-notice — bump the "seen N×" counter (debounced).
                self._bump_sighting_unlocked(key)
                return False
            self._pending_manual[key] = (list(basenames), suggested_name)
            self._bump_sighting_unlocked(key, force=True)
            return True

    def _bump_sighting_unlocked(self, key, force=False):
        now = time.monotonic()
        last = self._sighting_at.get(key, 0.0)
        if not force and (now - last) < self._sighting_gap:
            return
        self._sighting_at[key] = now
        self._sightings[key] = self._sightings.get(key, 0) + 1

    def sighting_count(self, key):
        with self._lock:
            return self._sightings.get(key, 0)

    def peek_pending_reviews(self):
        """Read the manual-review queue WITHOUT draining it.

        The Games pane shows what's awaiting a decision; the dialog flow in
        _poll_manual_review is what actually resolves it. Displaying must not
        pop, or the pane would silently swallow the prompt the user is waiting
        for. Includes items currently on screen (`_in_review`) so a queue of one
        doesn't read as empty while its dialog is open.
        """
        with self._lock:
            names = [name or key for key, (_basenames, name) in self._pending_manual.items()]
            return names + sorted(self._in_review - set(self._pending_manual))

    def peek_next_review(self):
        """Head of the pending queue as ``(key, basenames, suggested_name)``.

        Used by the Games unclassified card (frame 2d) so it can render It's a
        game / Not a game without draining. Returns None when empty. Does not
        surface items already held in ``_in_review`` (modal owns those).
        """
        with self._lock:
            if not self._pending_manual:
                return None
            key = next(iter(self._pending_manual))
            basenames, name = self._pending_manual[key]
            return key, list(basenames), name

    def take_pending_review(self, key=None):
        """Claim one pending review for the Games pane buttons.

        Moves the entry into ``_in_review`` (same as ``pop_pending_reviews``)
        so the modal poll cannot race it. Returns
        ``(key, basenames, suggested_name)`` or None.
        """
        with self._lock:
            if key is None:
                if not self._pending_manual:
                    return None
                key = next(iter(self._pending_manual))
            item = self._pending_manual.pop(key, None)
            if item is None:
                return None
            basenames, name = item
            self._in_review.add(key)
            return key, list(basenames), name

    def pop_pending_reviews(self):
        """Returns [(key, basenames, suggested_name), ...]."""
        with self._lock:
            pending = dict(self._pending_manual)
            self._pending_manual.clear()
            self._in_review.update(pending.keys())
            return [(key, basenames, name) for key, (basenames, name) in pending.items()]

    def finish_review(self, key):
        with self._lock:
            self._in_review.discard(key)
            self._sightings.pop(key, None)
            self._sighting_at.pop(key, None)

    def resolve_review(self, basenames, is_game, display_name=None):
        if is_game:
            for basename in basenames:
                self.mark_game(basename, display_name, source="manual")
        else:
            for basename in basenames:
                self.mark_non_game(basename)
