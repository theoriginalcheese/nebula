"""Resolves the app's install directory for both dev runs (``python main.py``)
and a frozen PyInstaller onefile exe.

Modules used to derive this from their own ``__file__``, which works in dev
but breaks under onefile: frozen module ``__file__`` values resolve inside
PyInstaller's temporary extraction dir (``sys._MEIPASS``), which is deleted
when the exe exits - so config.json/games.json/logs would silently vanish
each run. Anchor on ``sys.executable`` instead when frozen.
"""

import os
import sys

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Bundled read-only assets (e.g. nebula_icon.ico) live in PyInstaller's
# extraction dir when frozen (sys._MEIPASS) - separate from APP_DIR, which is
# for user-writable data that must persist next to the exe, not be wiped on
# exit.
RESOURCE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
