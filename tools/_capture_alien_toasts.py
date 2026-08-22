"""Capture spike (v4) toast states on Alien-PC into PNGs.

Run on Alien from the source checkout:

    python tools/_capture_alien_toasts.py

Writes under tools/_toast_demo_alien/ and exits.
"""
from __future__ import annotations

import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# When copied into tools/, ROOT is the checkout.
if os.path.basename(ROOT) == "_alien_toast_scan":
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "tools", "_toast_demo_alien")
os.makedirs(OUT, exist_ok=True)

import webview
from tools.shoot import grab, grab_screen, looks_blank, set_dpi_aware, windows as list_windows
from spike.windows import NebulaWindows, _DemoHost

SEQUENCE = [
    ("01_start", "start", "Helldivers 2", None),
    ("02_pause", "pause", "Helldivers 2", None),
    ("03_resume", "resume", "Helldivers 2", None),
    ("04_stop", "stop", "Helldivers 2",
     {"duration": 761, "size": 1_240_000_000}),
    ("05_error", "error", "OBS disconnected", None),
    ("06_session_pause", "pause", "Alien-Pc",
     {"reason": "session"}),
    ("07_prompt", "prompt", "starrail.exe",
     {"title": "Record this game?"}),
]

HOLD_S = 2.2


def _find_toast_hwnd():
    for hwnd, title in list_windows("Nebula Toast"):
        return hwnd
    return None


def _shoot(name: str) -> str:
    path = os.path.join(OUT, f"{name}.png")
    hwnd = _find_toast_hwnd()
    if hwnd is None:
        raise RuntimeError("no Nebula Toast HWND visible for %s" % name)
    img = grab(hwnd)
    if img is None or looks_blank(img):
        img = grab_screen(hwnd)
    img.save(path)
    return path


def main() -> int:
    set_dpi_aware()
    from obsauto.config import load_config

    host = _DemoHost()
    cfg = load_config()
    windows = NebulaWindows(host, cfg)

    master = webview.create_window(
        "Nebula Toast Capture",
        html="<html><body style='margin:0;background:#0A0812'></body></html>",
        width=320,
        height=200,
        hidden=True,
        frameless=True,
    )
    host.window = master

    done = threading.Event()
    results = []

    def sequence():
        try:
            time.sleep(1.4)
            for name, event, game, details in SEQUENCE:
                windows.toast_replace(event, game, details)
                time.sleep(HOLD_S)
                path = _shoot(name)
                results.append(path)
                print("SHOT", path, flush=True)
            time.sleep(0.4)
        finally:
            done.set()
            try:
                master.destroy()
            except Exception:
                pass

    def boot():
        threading.Thread(target=sequence, daemon=True).start()

    # Identity stamp for the folder.
    try:
        stamp = (
            f"host={os.environ.get('COMPUTERNAME', '?')}\n"
            f"cwd={ROOT}\n"
            f"argv={' '.join(sys.argv)}\n"
        )
        # Best-effort git head.
        import subprocess
        head = subprocess.check_output(
            ["git", "-C", ROOT, "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        stamp += f"git_head={head}\n"
    except Exception as exc:
        stamp = f"stamp_failed={exc}\n"
    with open(os.path.join(OUT, "IDENTITY.txt"), "w", encoding="utf-8") as f:
        f.write(stamp)

    webview.start(boot, debug=False)
    windows.destroy()
    print("DONE", len(results), "shots ->", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
