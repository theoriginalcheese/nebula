"""REDUNDANT. Do not use this as the toast.

Play the opacity-only twinkle (commit e6016ea). Anthony watched it on
2026-10-01 and said it is not the toast. The confirmed one is commit
a1ebd65, backed up in design/toast-canonical/. This file stays so the
wrong motion is not rebuilt by mistake.

The specks are drawn once around the chip and only their opacity changes.
Does not launch Nebula.
"""
import math
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import design_v3 as dv

# e6016ea obsauto/design_v3.py TOAST_DUST — offsets from the chip centre.
DUST = (
    (20, -12, 2.2, 0.78),
    (30, -5, 1.5, 0.48),
    (17, 15, 1.8, 0.58),
    (-11, -17, 1.4, 0.42),
    (38, 11, 1.2, 0.36),
    (7, -19, 1.1, 0.32),
    (26, 16, 1.0, 0.28),
)

W, H = 384, 60
KEY = "#00FF01"
CASES = (
    ("Recording started", dv.EMBER),
    ("Recording paused", dv.ACCENT),
    ("Recording resumed", dv.ACCENT),
    ("Recording stopped", dv.EMBER),
    ("Something went wrong", dv.EMBER),
    ("Record again?", dv.ACCENT),
)
HOLD_MS = 4000


def main():
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=KEY)
    try:
        root.attributes("-transparentcolor", KEY)
    except tk.TclError:
        pass
    x = root.winfo_screenwidth() - W - 24
    y = root.winfo_screenheight() - H - 64
    root.geometry(f"{W}x{H}+{x}+{y}")

    canvas = tk.Canvas(root, width=W, height=H, bg=KEY, highlightthickness=0)
    canvas.pack()
    r = H / 2
    for item in (
        canvas.create_oval(0, 0, H, H, fill=dv.CARD_CORE, outline=""),
        canvas.create_oval(W - H, 0, W, H, fill=dv.CARD_CORE, outline=""),
        canvas.create_rectangle(r, 0, W - r, H, fill=dv.CARD_CORE, outline=""),
    ):
        pass

    cy = H / 2
    chip_cx, chip_cy = 22, cy
    chip = canvas.create_oval(
        chip_cx - 13, chip_cy - 13, chip_cx + 13, chip_cy + 13,
        fill=dv.over(dv.ACCENT, 0.16, dv.GROUND), outline="")
    title = canvas.create_text(
        44, cy, anchor="w", text="", fill=dv.TEXT,
        font=("Segoe UI", 10))

    items, bases = [], []
    for dx, dy, radius, alpha in DUST:
        dot = canvas.create_oval(
            chip_cx + dx - radius, chip_cy + dy - radius,
            chip_cx + dx + radius, chip_cy + dy + radius,
            fill=dv.over(dv.ACCENT, alpha, dv.CARD_CORE), outline="")
        items.append(dot)
        bases.append(alpha)

    state = {"i": 0, "tint": dv.EMBER, "born": time.time()}

    def apply(i):
        text, tint = CASES[i % len(CASES)]
        state["i"] = i
        state["tint"] = tint
        state["born"] = time.time()
        canvas.itemconfigure(title, text=text)
        canvas.itemconfigure(chip, fill=dv.over(tint, 0.16, dv.GROUND))
        print("showing %s" % text, flush=True)

    def tick():
        if not canvas.winfo_exists():
            return
        # e6016ea _toast_twinkle, unchanged.
        phase = time.time() * 2.4
        tint = state["tint"]
        for i, item in enumerate(items):
            wave = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(phase + i * 1.7))
            alpha = bases[i] * wave
            canvas.itemconfigure(item, fill=dv.over(tint, alpha, dv.CARD_CORE))
        if (time.time() - state["born"]) * 1000 >= HOLD_MS:
            nxt = state["i"] + 1
            if nxt >= len(CASES) * 2:
                root.destroy()
                return
            apply(nxt)
        root.after(50, tick)

    apply(0)
    root.after(50, tick)
    root.mainloop()


if __name__ == "__main__":
    main()
