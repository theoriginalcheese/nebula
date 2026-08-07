# -*- mode: python ; coding: utf-8 -*-
# OBSOLETE — the Tk UI is retired. Use nebula-v4.spec:
#   pyinstaller nebula-v4.spec   -> dist/Nebula-v4.exe
#
# This file used to build the CustomTkinter shell via main.py. main.py now
# launches spike/app.py; rebuilding with this spec without the v4 web bundle
# would produce a broken exe. Kept only so old scripts that still name it
# fail loudly with a clear message rather than silently packaging Tk chrome.
raise SystemExit(
    "nebula.spec is obsolete (Tk UI retired). Use: pyinstaller nebula-v4.spec"
)
