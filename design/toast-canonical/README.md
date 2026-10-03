# Canonical capsule toast — do not overwrite

Anthony confirmed this live on 2026-10-01. It is the second recovery of the same toast. This folder is the backup. Do not regenerate it from a demo script, and do not replace these stills with a fresh capture.

## What it is

Commit `a1ebd65` (2026-08-08, "Bump version to 4.0.1"). Status pills are **384×60**. The prompt is **404×116**. Both are true pills (radius = height / 2).

The prompt keeps the copy on the upper row (chip centre at y=30) and puts **Record** and **Not now** underneath, at y = height − 40, x = 16 and x = 132, each 108×26. Dust moves. It does not only twinkle.

| Event | Motion | Where |
|---|---|---|
| start | burst | left, on the chip |
| stop | sink | left |
| pause | drift | right end |
| resume | rise | left |
| error | scatter | left |
| prompt | orbit | right end |

Ember for start, stop, and error. Violet for pause, resume, and prompt.

## Where the live code is

- `obsauto/design_v3.py` — `TOAST_*`
- `obsauto/gui.py` — Tk painter (the window that was confirmed)
- `spike/web/toast.css`, `spike/web/toast.html`, `spike/web/toast.js`, `spike/windows.py` — the toast `main.py` actually shows

`source/` in this folder is a frozen excerpt of the `a1ebd65` painter. Nothing imports it.

## Stills

`stills/` is a copy of the real gallery PNGs. The originals also live in `tools/_toast_demo/`. Several files in that gallery are empty (null bytes): `01_start.png`, `02_start_with_meta.png`, `04_pause_session.png`, `09_prompt_new_game.png`. They are not here.

## Do not use

- `tools/_toast_demo_alien/` — redundant recapture
- `design/claude-inspo/redundant/` — the opacity-only twinkle, which is an earlier smaller toast
- A 420×68 strip with the buttons on the right — that was a later mismatch
