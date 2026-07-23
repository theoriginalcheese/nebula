import ctypes
import os
import sys

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
    #
    # The GUI is a fixed-pixel canvas design (860x660 art + absolute
    # coordinates) authored at 1.0 scaling. CustomTkinter would otherwise
    # auto-multiply the window geometry and its widgets by the monitor's DPI
    # factor (e.g. 1.5x at 150% scaling) WITHOUT scaling the raw canvas art -
    # so everything misaligns and clips. gui.py pairs this with
    # ctk.deactivate_automatic_dpi_awareness() to keep the whole UI at 1.0,
    # while this call keeps it crisp. (2 = PROCESS_PER_MONITOR_DPI_AWARE.)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

from obsauto.config import load_config
from obsauto import classifier as classifier_module
from obsauto import steam_scanner
from obsauto.classifier import Classifier
from obsauto.gui import AppWindow
from obsauto.tray_app import build_tray_icon
from obsauto.app_log import setup_logging

ICON_PATH = os.path.join(os.path.dirname(__file__), "nebula_icon.ico")


def _apply_sync_folder(config):
    """Point games.json / steam_appid_cache.json at a synced folder (e.g.
    OneDrive) instead of this install's own directory, so classifications
    made on one machine (laptop/desktop) show up on the other. Must run
    before Classifier() is constructed, since it reads these paths at
    __init__ time.

    A relative path (e.g. "OneDrive/ObsAutoFolder") resolves against this
    machine's own home directory - so the same config.json value works on
    both the laptop and desktop even though the Windows username differs,
    as long as OneDrive syncs to its default "~/OneDrive" location on both.
    """
    sync_folder = config.get("sync_folder")
    if not sync_folder:
        return
    if not os.path.isabs(sync_folder):
        sync_folder = os.path.join(os.path.expanduser("~"), sync_folder)
    os.makedirs(sync_folder, exist_ok=True)
    classifier_module.DATA_FILE = os.path.join(sync_folder, "games.json")
    steam_scanner.CACHE_FILE = os.path.join(sync_folder, "steam_appid_cache.json")


def main():
    setup_logging()
    config = load_config()
    _apply_sync_folder(config)
    classifier = Classifier()

    app = AppWindow(config, classifier, on_close_to_tray=lambda: None)
    app.tray_icon = build_tray_icon(app, ICON_PATH)

    app.root.after(200, app.root.withdraw)  # start minimized to tray
    app.root.after(500, app.autostart)  # connect + start monitoring on its own
    app.run()


if __name__ == "__main__":
    main()
