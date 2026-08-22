"""Real-content + multi-DPI toast formatting audit.

    python tools/audit_toasts.py

Forces UI scales 1.0 / 1.25 / 1.5 / 2.0 (100%–200% monitors), fires realistic
event copy (long game names, stop meta, session pause, prompts), and checks:

- every text item stays inside the capsule (≤ W − TOAST_TEXT_INSET)
- toast HWND sits wholly inside the (mocked) primary work area with 24px margins
- pixel size ≈ design size × scale

Writes PNGs under tools/_toast_demo/audit/<scale>/ and a summary JSON.
Prints nebula_identity first so the report cannot be mistaken for the frozen exe.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.nebula_identity import banner, identity
from tools.shoot import grab, grab_screen, looks_blank, set_dpi_aware

print(banner())
print()

from obsauto import gui, hotkey

hotkey.register = lambda *a, **k: None
gui.ensure_obs_running = lambda *a, **k: None

from obsauto import config as config_module
from obsauto import design_v3 as dv
from obsauto.classifier import Classifier
from obsauto.config import load_config
from obsauto.gui import AppWindow

config_module.save_config = lambda *a, **k: None

OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_toast_demo", "audit")
SCALES = (1.0, 1.25, 1.5, 2.0)
# Typical primary work areas (left, top, right, bottom) — taskbar already subtracted.
WORK_AREAS = {
    "1080p": (0, 0, 1920, 1040),
    "1440p": (0, 0, 2560, 1400),
    "4k": (0, 0, 3840, 2100),
    "ultrawide": (0, 0, 3440, 1400),
}

# Real-ish copy — long titles stress ellipsis + middot packing.
CASES = [
    ("start_short", "start", "Helldivers 2", None),
    ("start_long", "start", "The Elder Scrolls IV: Oblivion Remastered", None),
    ("pause", "pause", "Counter-Strike 2", None),
    ("pause_session", "pause", "Clair Obscur: Expedition 33",
     {"reason": "session"}),
    ("resume", "resume", "Baldur's Gate 3", None),
    ("stop_meta", "stop", "Helldivers 2",
     {"duration": 6472, "size": 18_450_000_000}),
    ("stop_long_name", "stop", "Call of Duty: Black Ops 6",
     {"duration": 95, "size": 420_000_000}),
    ("error", "error", "OBS disconnected", None),
    ("error_long", "error", "SetRecordDirectory failed — path not writable", None),
    ("prompt_again", "prompt", "Helldivers 2",
     {"title": "Record again?"}, True),
    ("prompt_new", "prompt", "Record Clair Obscur: Expedition 33?",
     {"title": "Record this game?"}, True),
    ("prompt_long", "prompt",
     "Record The Elder Scrolls IV: Oblivion Remastered?",
     {"title": "Record this game?"}, True),
]


def settle(app, ms=400):
    end = time.perf_counter() + ms / 1000
    while time.perf_counter() < end:
        app.root.update()
        time.sleep(0.004)


def item_right_base(toast, key, scale):
    item = toast.get(key)
    if not item:
        return None
    try:
        if toast["canvas"].itemcget(item, "state") == "hidden":
            return None
        bbox = toast["canvas"].bbox(item)
    except Exception:
        return None
    if not bbox:
        return None
    return bbox[2] / scale


def check_layout(app, toast, label):
    """Return list of failure strings."""
    fails = []
    scale = app.scale
    prompt = bool(toast.get("prompt") or toast.get("actions"))
    w = dv.TOAST_PROMPT_W if prompt else dv.TOAST_W
    h = dv.TOAST_PROMPT_H if prompt else dv.TOAST_H
    max_x = w - dv.TOAST_TEXT_INSET

    sw = toast["popup"].winfo_width()
    sh = toast["popup"].winfo_height()
    expect_w = int(round(w * scale))
    expect_h = int(round(h * scale))
    # Allow 2px rounding slack.
    if abs(sw - expect_w) > 2 or abs(sh - expect_h) > 2:
        fails.append(
            f"{label}: hwnd {sw}x{sh} != design {w}x{h}×{scale} "
            f"(expected ~{expect_w}x{expect_h})"
        )

    for key in ("title", "sep", "sub", "detail"):
        right = item_right_base(toast, key, scale)
        if right is not None and right > max_x + 0.6:
            text = ""
            try:
                text = toast["canvas"].itemcget(toast[key], "text")
            except Exception:
                pass
            fails.append(
                f"{label}: {key} overflows capsule "
                f"(right={right:.1f} > max_x={max_x}, text={text!r})"
            )
    return fails


def check_placement(app, toast, work, label):
    fails = []
    left, top, right, bottom = work
    margin = int(round(dv.TOAST_MARGIN * app.scale))
    popup = toast["popup"]
    x = int(popup.winfo_x())
    y = int(popup.winfo_y())
    sw = int(popup.winfo_width())
    sh = int(popup.winfo_height())
    # After rise-in the toast should sit at the resting corner. Force alpha and
    # snap geometry to the end pose if still animating.
    try:
        popup.geometry(f"{sw}x{sh}+{right - sw - margin}+{bottom - sh - margin}")
        app.root.update()
        x = int(popup.winfo_x())
        y = int(popup.winfo_y())
    except Exception:
        pass

    if x < left or y < top or x + sw > right or y + sh > bottom:
        fails.append(
            f"{label}: toast ({x},{y},{sw},{sh}) outside work {work}"
        )
    # Right / bottom margins (±3px for DPI rounding)
    if abs((right - (x + sw)) - margin) > 3:
        fails.append(
            f"{label}: right margin {(right - (x + sw))} != {margin}"
        )
    if abs((bottom - (y + sh)) - margin) > 3:
        fails.append(
            f"{label}: bottom margin {(bottom - (y + sh))} != {margin}"
        )
    return fails


def capture(app, out_dir, name):
    toast = app._toast
    toast["hovering"] = True
    toast["remaining"] = toast["life"]
    try:
        toast["popup"].attributes("-alpha", 1.0)
    except Exception:
        pass
    settle(app, 220)
    hwnd = int(toast["popup"].winfo_id())
    img = grab(hwnd)
    if looks_blank(img):
        img = grab_screen(hwnd)
    path = os.path.join(out_dir, f"{name}.png")
    img.save(path)
    return path, img.size


def run_scale(scale: float) -> dict:
    gui._compute_ui_scale = lambda _window: scale
    app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
    app.root.withdraw()
    # Park off-screen-ish; toast is its own toplevel.
    try:
        app.root.geometry("+0+0")
    except Exception:
        pass
    settle(app, 200)

    if abs(app.scale - scale) > 0.01:
        app.root.destroy()
        return {"scale": scale, "ok": False, "errors": [f"app.scale={app.scale} wanted {scale}"]}

    out_dir = os.path.join(OUT_ROOT, f"scale_{scale:g}".replace(".", "_"))
    os.makedirs(out_dir, exist_ok=True)

    errors = []
    shots = []
    callback_errors = []
    app.root.report_callback_exception = (
        lambda t, v, tb: callback_errors.append(
            "".join(traceback.format_exception(t, v, tb))))

    # Cycle work areas on a representative subset so every resolution is hit.
    work_names = list(WORK_AREAS.keys())

    for i, case in enumerate(CASES):
        name, event, sub, details = case[0], case[1], case[2], case[3]
        as_prompt = len(case) > 4 and case[4]
        work_name = work_names[i % len(work_names)]
        work = WORK_AREAS[work_name]
        app._toast_workarea = lambda w=work: w

        if as_prompt:
            app._toast_replace(
                event, sub, details,
                actions=[("Record", lambda: None), ("Not now", lambda: None)],
            )
        else:
            app._toast_replace(event, sub, details)

        settle(app, 450)
        toast = app._toast
        label = f"scale={scale:g}/{work_name}/{name}"
        errors.extend(check_layout(app, toast, label))
        errors.extend(check_placement(app, toast, work, label))
        # Stop/meta must keep duration/size visible — not just the game name.
        if details and (details.get("duration") is not None or details.get("size") is not None):
            try:
                detail_shown = toast["canvas"].itemcget(toast["detail"], "text") or ""
                detail_state = toast["canvas"].itemcget(toast["detail"], "state")
            except Exception:
                detail_shown, detail_state = "", "hidden"
            if detail_state == "hidden" or not any(ch.isdigit() for ch in detail_shown):
                errors.append(
                    f"{label}: detail meta missing after layout "
                    f"(shown={detail_shown!r})"
                )
            elif details.get("size") is not None and not any(
                    u in detail_shown for u in ("B", "KB", "MB", "GB", "TB")):
                errors.append(
                    f"{label}: size missing from detail (shown={detail_shown!r})"
                )
            elif "…" in detail_shown or "..." in detail_shown:
                errors.append(
                    f"{label}: detail was ellipsized (shown={detail_shown!r})"
                )
        path, size = capture(app, out_dir, f"{i:02d}_{name}_{work_name}")
        shots.append({"name": name, "work": work_name, "path": path, "px": size})
        print(f"  {label:48s}  {size[0]}x{size[1]}  -> {os.path.basename(path)}")

    if callback_errors:
        errors.extend(callback_errors)

    # Tear down cleanly — pending after() polls otherwise spam bgerror once
    # the root is gone (harmless, but noisy in audit logs).
    try:
        if app._toast and app._toast.get("popup"):
            app._toast["popup"].destroy()
        app._toast = None
    except Exception:
        pass
    try:
        app.root.quit()
    except Exception:
        pass
    try:
        app.root.destroy()
    except Exception:
        pass
    return {
        "scale": scale,
        "ok": not errors,
        "errors": errors,
        "shots": shots,
        "out_dir": out_dir,
    }


def main():
    set_dpi_aware()
    os.makedirs(OUT_ROOT, exist_ok=True)
    results = []
    print(f"Auditing scales {SCALES} with real copy…\n")
    for scale in SCALES:
        print(f"=== scale {scale:g} ===")
        results.append(run_scale(scale))
        print()

    summary = {
        "identity": identity(),
        "scales": results,
        "ok": all(r["ok"] for r in results),
    }
    summary_path = os.path.join(OUT_ROOT, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    failed = [e for r in results for e in r["errors"]]
    if failed:
        print("FAILURES:")
        for e in failed:
            print(f"  - {e}")
        print(f"\nWrote {summary_path}")
        return 1

    print(f"ALL PASS ({sum(len(r['shots']) for r in results)} shots across "
          f"{len(SCALES)} scales × {len(WORK_AREAS)} work-area shapes)")
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
