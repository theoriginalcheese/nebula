"""Nebula entry point.

The shipping UI is **v4 WebView** (``spike/app.py``). The Tk shell in
``obsauto/gui.py`` is obsolete — kept in-tree so older GUI tests can still
import it, but ``python main.py`` no longer opens it.

    python main.py                 # same as: python spike/app.py
    python spike/app.py --show     # visible window (dev)
    pyinstaller nebula-v4.spec     # -> dist/Nebula-v4.exe

``nebula.spec`` (Tk onefile) is retired; use ``nebula-v4.spec``.
"""
from __future__ import annotations

import sys


def main(argv=None):
    # Preserve argv for spike flags (--show, --dev, --toast-demo, --url=…).
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    from spike.app import main as spike_main
    return spike_main() or 0


if __name__ == "__main__":
    raise SystemExit(main())
