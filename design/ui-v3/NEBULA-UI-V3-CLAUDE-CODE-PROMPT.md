# Paste into Claude Code — Nebula UI v3 (post-fidelity pass)

**Copy to** `C:\Users\antho\Downloads\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md`  
**Work in** your Nebula clone — pull `cursor/implement-mockup-v3-2b0d` (or `main` after merge).

---

Hi — continue **Nebula UI v3 refinement**. The mockup at
`design/ui-v3/Nebula UI Mockups v3.dc.html` has been implemented against the
local tree (not a fresh greenfield). Chassis was already on `main`; Cursor just
landed the fidelity pass in PR #4.

## What was just implemented

- **Hero 2a/2f–2h:** ember for live recording; controller chip; exe source line;
  folder chip gone; 404px preview with Live + res/fps; preview **hidden** while
  watching/disconnected
- **Stats 2a:** Clips today · Recorded · Auto-culled · Idle pauses — backed by
  disk scan + `Monitor` counters (`auto_culled`, `idle_pauses`,
  `recorded_seconds_today`)
- **Activity:** Copy log + All-tags filter; standalone Activity view removed
- **OBS:** `GetVersion`, `GetVideoSettings`, `GetCurrentProgramScene`; titlebar
  one-liner (version only when real)
- **Clips:** Play (`os.startfile`) + `Game — YYYY-MM-DD HH:MM` titles
- **Mini 2k:** pause + stop + collapse
- **Rail:** Clips total badge; Games = **pending** count
- **Customise** chrome hidden (double-click pane title to rearrange)

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

## Refine next

1. Pixel-check 2a–2k against a live `python main.py` window
2. Toast dismiss **X** (2i); Settings Connection footer + Test again (2c)
3. Classifier AppID / seen-count if you want Games 2d exact
4. ffmpeg Length/thumbs only if you accept the dependency
5. Macropad subsystem (HID → config map → pane)
6. `pyinstaller nebula.spec` when happy

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
