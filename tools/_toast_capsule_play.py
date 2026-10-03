"""Play every shipping toast on the desktop. Does not launch Nebula.

    python tools/_toast_capsule_play.py
"""
import json
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
    _toast_place,
    _toast_workarea,
)

TITLE = "Nebula Toast"
HOLD_S = 3.6

# Same set as the August gallery, in that order.
CASES = [
    ("start", "Helldivers 2", None, None),
    ("pause", "Helldivers 2", None, None),
    ("pause", "Helldivers 2", {"reason": "session"}, None),
    ("resume", "Helldivers 2", None, None),
    ("stop", "Helldivers 2", {"duration": 647, "size": 1_845_000_000}, None),
    ("error", "OBS disconnected", None, None),
    ("prompt", "Helldivers 2", {"title": "Record again?"}, ["Record", "Not now"]),
    ("prompt", "Record Clair Obscur: Expedition 33?",
     {"title": "Record this game?"}, ["Record", "Not now"]),
]


class Api:
    def __init__(self, window_box):
        self._box = window_box
        event, name, details, actions = CASES[0]
        self.pending = _payload(event, name, details, actions)

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


def _payload(event, name, details, actions):
    content = _toast_content(event, name, details)
    if actions:
        content["actions"] = list(actions)
        content["prompt"] = True
    return content


def _play(box):
    win = box["win"]
    # First state is already pending for boot. Give the rise a moment.
    time.sleep(HOLD_S)
    for event, name, details, actions in CASES[1:]:
        content = _payload(event, name, details, actions)
        prompt = bool(content.get("prompt"))
        w = TOAST_PROMPT_W if prompt else TOAST_W
        h = TOAST_PROMPT_H if prompt else TOAST_H
        try:
            win.resize(w, h)
        except Exception as exc:
            print("resize failed: %s" % exc)
        time.sleep(0.15)
        _clip_capsule(win, None)
        print("showing %s — %s" % (event, content.get("title")))
        win.evaluate_js("window.toastReplace(%s)" % json.dumps(content))
        time.sleep(4.8 if prompt else HOLD_S)
    print("done")
    try:
        win.destroy()
    except Exception:
        pass


def main():
    left, top, right, bottom, monitor = _toast_workarea()
    x, y = _toast_place(right, bottom, monitor, prompt=False)
    box = {}
    api = Api(box)
    win = webview.create_window(
        TITLE,
        TOAST_HTML,
        js_api=api,
        width=TOAST_W,
        height=TOAST_H,
        min_size=(TOAST_W, TOAST_H),
        x=int(x),
        y=int(y),
        frameless=True,
        easy_drag=False,
        on_top=True,
        shadow=True,
        focus=False,
        background_color=dv.GROUND_DEEP,
    )
    box["win"] = win
    print("showing start — Recording started")
    threading.Thread(target=_play, args=(box,), daemon=True).start()
    webview.start()


if __name__ == "__main__":
    main()
