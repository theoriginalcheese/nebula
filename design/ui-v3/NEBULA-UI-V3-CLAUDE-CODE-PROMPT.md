# Paste into Claude Code — Nebula UI v3 (post-fidelity pass)

**Copy to** `C:\Users\antho\Downloads\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md`  
**Work in** your Nebula clone — pull `cursor/implement-mockup-v3-2b0d` (or `main` after merge).

---

Hi — continue **Nebula UI v3 refinement**. The mockup at
`design/ui-v3/Nebula UI Mockups v3.dc.html` has been implemented against the
local tree (not a fresh greenfield). Chassis was already on `main`; Cursor just
landed the fidelity pass in PR #4.

## Build order steps 1–7 are DONE on this branch

Stop at step 7. Do **not** start ffmpeg Length/thumbs, AppID storage, or a full
HID macropad subsystem unless Anthony asks — those are beyond the build order.

### Shipped through step 7
1. Chassis 2a  
2. Hero enum + stats + activity  
3. Tray + window chrome  
4. Single-slot toast (replace-in-place, 4s drain, hover freeze, **dismiss X**)  
5. Clips (Play / Reveal / Delete; Length/thumbs omitted — need ffmpeg)  
6. Settings (mono keys, blur-write, rail **Reveal**, Connection footer + **Test again** + handshake ms)  
7. Games unclassified **It's a game / Not a game** card; Macropad honestly empty; mini overlay with pause/stop/collapse  

## Hard rules (do not reverse)

1. Never animate the main `tk.Canvas` per-frame
2. No fabricated numbers — build a source or omit
3. Import tokens from `obsauto/design_v3.py` only
4. Macropad stays empty until HID + scan-code bindings exist
5. No Mark clip / ffmpeg Length-thumbs until those backends exist

## Read first

1. `design/ui-v3/Nebula UI Mockups v3.dc.html` (browser; needs CDN)
2. `design/ui-v3/BUILD-SPEC.md` (wins over frames)
3. `CURSOR-HANDOFF.md` §2
4. `obsauto/design_v3.py`

## Only if asked (beyond step 7)

1. Pixel-check polish against the open mockup  
2. Classifier AppID / seen-count  
3. ffmpeg Length/thumbs  
4. Macropad HID subsystem  
5. `pyinstaller nebula.spec`

## Verify

```bat
python tests/test_design_v3.py
python tests/test_monitor_stats.py
python tests/test_views.py
python tests/test_frame_pacing.py
python main.py
```

```bat
copy "C:\Users\antho\nebula\design\ui-v3\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md" "C:\Users\antho\Downloads\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md"
```
