import ctypes
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(__file__))

try:
    # Without this, Windows treats the taskbar/Alt-Tab icon as belonging to
    # pythonw.exe itself (the generic Python icon) rather than this specific
    # window - this has to run before any window is created. iconbitmap()
    # alone (already set on the window) isn't enough on its own.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Nebula.App")
except Exception:
    pass

try:
    # Make the process per-monitor DPI-aware so Windows renders our window at
    # true device pixels instead of bitmap-stretching it (which looks blurry
    # on a scaled display). This MUST run before any Tk window is created.
    # gui.py pairs this with ctk.deactivate_automatic_dpi_awareness() and one
    # uniform scale factor. (2 = PROCESS_PER_MONITOR_DPI_AWARE.)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

from obsauto.config import load_config
from obsauto import classifier as classifier_module
from obsauto import steam_scanner
from obsauto.classifier import Classifier
from obsauto.gamesync import GameSync
from obsauto.offload import Offloader
from obsauto.gui import AppWindow
from obsauto.tray_app import build_tray_icon
from obsauto.app_log import setup_logging, log_to_file
from obsauto.paths import RESOURCE_DIR

ICON_PATH = os.path.join(RESOURCE_DIR, "nebula_icon.ico")


def _apply_sync_folder(config):
    """Legacy folder-based sync (was OneDrive). Superseded by the GitHub sync,
    but still honoured if someone has sync_folder set - repoints games.json /
    steam cache into it. Must run before Classifier() reads those paths."""
    sync_folder = config.get("sync_folder")
    if not sync_folder:
        return
    if not os.path.isabs(sync_folder):
        sync_folder = os.path.join(os.path.expanduser("~"), sync_folder)
    os.makedirs(sync_folder, exist_ok=True)
    classifier_module.DATA_FILE = os.path.join(sync_folder, "games.json")
    steam_scanner.CACHE_FILE = os.path.join(sync_folder, "steam_appid_cache.json")


class _GameListSync:
    """Glues the classifier to GitHub: pulls the remote list into the local one
    at startup, and pushes local changes back - debounced, so a Steam rescan
    that registers dozens of games results in one push, not dozens."""

    def __init__(self, gamesync, classifier, log):
        self._sync = gamesync
        self._classifier = classifier
        self._log = log
        self._timer = None
        self._lock = threading.Lock()

    def pull_at_startup(self):
        if not self._sync.enabled:
            return
        def worker():
            remote = self._sync.fetch()
            if remote:
                added = self._classifier.absorb(remote)
                if added:
                    self._log(f"[Sync] Pulled {added} classification(s) from GitHub.")
            # Push our (possibly newer) local state back so both ends converge.
            self._sync.push(self._classifier.snapshot())
            self._log("[Sync] Game list synced with GitHub.")
        threading.Thread(target=worker, daemon=True).start()

    def on_saved(self, _data):
        # Debounce: coalesce a burst of _save() calls into one push 3s later.
        if not self._sync.enabled:
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(3.0, self._push_now)
            self._timer.daemon = True
            self._timer.start()

    def _push_now(self):
        try:
            self._sync.push(self._classifier.snapshot())
        except Exception as exc:
            self._log(f"[Sync] push failed: {exc}")


def main():
    setup_logging()
    config = load_config()
    _apply_sync_folder(config)

    # Logs from the sync/offload layers route to a holder that upgrades from the
    # log file to the GUI's activity feed once the window exists.
    log_target = {"fn": log_to_file}

    def route(msg):
        try:
            log_target["fn"](msg)
        except Exception:
            pass

    gamesync = GameSync(config, on_log=route)
    offloader = Offloader(config, on_log=route)
    classifier = Classifier(on_log=route)

    coordinator = _GameListSync(gamesync, classifier, route)
    classifier.on_saved = coordinator.on_saved

    app = AppWindow(config, classifier, on_close_to_tray=lambda: None,
                    offloader=offloader, gamesync=gamesync)
    # From here on, sync/offload chatter shows up in the activity log too.
    log_target["fn"] = app._log

    app.tray_icon = build_tray_icon(app, ICON_PATH)

    offloader.start(on_state=app.on_offload_state)
    coordinator.pull_at_startup()

    app.root.after(200, app.root.withdraw)  # start minimized to tray
    app.root.after(500, app.autostart)  # connect + start monitoring on its own
    app.run()


if __name__ == "__main__":
    main()
