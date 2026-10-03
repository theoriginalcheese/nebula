"""Capture the shipping WebView toast without launching Nebula.

Writes shots/toast-capsule/*.png. Does not touch tools/_toast_demo/.
"""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import webview

from obsauto import design_v3 as dv
from spike.windows import (
    TOAST_H,
    TOAST_HTML,
    TOAST_PROMPT_H,
    TOAST_PROMPT_W,
    TOAST_W,
    _clip_capsule,
    _make_transparent,
    _toast_content,
)
from tools.shoot import grab, grab_screen, looks_blank, set_dpi_aware, windows

OUT = os.path.join(ROOT, os.environ.get("TOAST_SMOKE_DIR", os.path.join("shots", "toast-capsule")))
TITLE = "Nebula Toast Smoke"


class Api:
    """Bridge only. The window stays off this object — pywebview walks public
    attributes, and a Window there recurses until the process hangs."""

    def __init__(self, window_box):
        self._box = window_box
        self.pending = _toast_content("start", "Helldivers 2", None)

    def config(self):
        return {
            "w": TOAST_W,
            "h": TOAST_H,
            "prompt_w": TOAST_PROMPT_W,
            "prompt_h": TOAST_PROMPT_H,
            "life_ms": dv.TOAST_LIFE_MS,
            "prompt_life_ms": dv.TOAST_PROMPT_LIFE_MS,
            "drain_h": dv.TOAST_DRAIN_H,
            "margin": dv.TOAST_MARGIN,
            "in_ms": dv.TOAST_IN_MS,
            "in_rise": dv.TOAST_IN_RISE,
            "out_ms": dv.TOAST_OUT_MS,
            "dust": [list(spec) for spec in dv.TOAST_DUST],
        }

    def consume_pending(self):
        pending = self.pending
        self.pending = None
        return pending

    def ready(self):
        win = self._box.get("win")
        if win is None:
            return
        _make_transparent(win, None)
        _clip_capsule(win, None)

    def focus_main(self):
        return None

    def on_expired(self):
        return None

    def action(self, index):
        return None


def _hwnd():
    found = windows(TITLE)
    if not found:
        return None
    return next((h for h, t in found if t == TITLE), found[0][0])


def _save(name):
    hwnd = _hwnd()
    if not hwnd:
        raise RuntimeError("toast window not found for %s" % name)
    img = grab(hwnd)
    how = "PrintWindow"
    if looks_blank(img):
        img = grab_screen(hwnd)
        how = "screen"
    path = os.path.join(OUT, name + ".png")
    img.save(path)
    print("%s  %sx%s  via %s  -> %s" % (name, img.width, img.height, how, path))
    return path


def _shoot(api):
    win = api._box["win"]
    try:
        os.makedirs(OUT, exist_ok=True)
        for _ in range(40):
            if _hwnd():
                break
            time.sleep(0.1)
        time.sleep(1.2)
        _clip_capsule(win, None)
        win.evaluate_js(
            "document.getElementById('toast').classList.add('is-visible');"
            "document.getElementById('toast').style.opacity='1';"
            "document.getElementById('toast').style.transform='none';"
        )
        time.sleep(0.6)
        import json
        start = _toast_content("start", "Helldivers 2", None)
        win.evaluate_js("window.toastReplace(%s)" % json.dumps(start))
        time.sleep(0.5)
        _save("01_start")

        for name, event, game, details in (
            ("02_pause", "pause", "Helldivers 2", None),
            ("03_resume", "resume", "Helldivers 2", None),
            ("04_stop", "stop", "Helldivers 2",
             {"duration": 647, "size": int(1.7 * 1024 ** 3)}),
            ("05_error", "error", "", None),
        ):
            payload = _toast_content(event, game, details)
            win.evaluate_js("window.toastReplace(%s)" % json.dumps(payload))
            time.sleep(0.35)
            _save(name)

        prompt = _toast_content("prompt", "Helldivers 2", None)
        prompt["prompt"] = True
        prompt["actions"] = ["Record", "Not now"]
        win.resize(TOAST_PROMPT_W, TOAST_PROMPT_H)
        time.sleep(0.4)
        _clip_capsule(win, None)
        import json
        win.evaluate_js("window.toastReplace(%s)" % json.dumps(prompt))
        time.sleep(0.8)
        win.evaluate_js(
            "document.getElementById('toast').classList.add('is-visible');"
            "document.getElementById('toast').style.opacity='1';"
            "document.getElementById('toast').style.transform='none';"
        )
        time.sleep(0.4)
        _clip_capsule(win, None)
        _save("08_prompt")

        new_game = _toast_content(
            "prompt", "Clair Obscur", {"title": "New game detected"})
        new_game["prompt"] = True
        new_game["actions"] = ["Record", "Not now"]
        win.evaluate_js("window.toastReplace(%s)" % json.dumps(new_game))
        time.sleep(0.45)
        _clip_capsule(win, None)
        _save("09_prompt_new_game")
    except Exception as exc:
        print("SMOKE FAILED: %s" % exc)
    finally:
        try:
            win.destroy()
        except Exception:
            pass


def main():
    set_dpi_aware()
    box = {}
    api = Api(box)
    win = webview.create_window(
        TITLE,
        TOAST_HTML,
        js_api=api,
        width=TOAST_W,
        height=TOAST_H,
        min_size=(TOAST_W, TOAST_H),
        x=160,
        y=160,
        frameless=True,
        easy_drag=False,
        on_top=True,
        shadow=True,
        focus=False,
        background_color=dv.GROUND_DEEP,
    )
    box["win"] = win
    threading.Thread(target=_shoot, args=(api,), daemon=True).start()
    webview.start()


if __name__ == "__main__":
    main()
