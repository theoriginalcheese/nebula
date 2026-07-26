# Paste into Claude Code — Nebula UI v3 (mockup fidelity complete)

**Copy to** `C:\Users\antho\Downloads\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md`  
**Work in** your Nebula clone — pull `cursor/implement-mockup-v3-2b0d` (or `main` after merge).

---

Hi — **Nebula UI v3** is implemented against the local mockup at
`design/ui-v3/Nebula UI Mockups v3.dc.html` (Claude Design MCP is not available
in the Cursor cloud agent; the imported tree is the source of truth).

Authority: `BUILD-SPEC.md` > frames / `.dc.html` > Nocturne CSS (do **not** link
Nocturne into the app). Tokens: `obsauto/design_v3.py`.

## Shipped

### Build order 1–7
1. Chassis 2a  
2. Hero enum + stats + activity  
3. Tray + window chrome  
4. Single-slot toast (replace-in-place, 4s drain, hover freeze, dismiss X)  
5. Clips (Play / Reveal / Delete; Length/thumbs omitted — need ffmpeg)  
6. Settings (mono keys, blur-write, rail Reveal, Connection footer + Test again)  
7. Games unclassified decide card; Macropad honestly empty; mini overlay  

### Fidelity follow-up (mockup frames)
- Watching: `Foreground: chrome.exe — classified as not a game.`
- Disconnected: `next attempt in Ns` countdown + Launch OBS wording
- Hero: Mark clip → OBS `CreateRecordChapter` (soft-fail toast); secondary pill
  trailing-icon circle; scene blank until real name (no fake "Game Capture")
- Games: Steam AppID on rows; unclassified `seen N×` (debounced sightings)
- Settings: Browse on paths, password eye, `launch_obs_with_nebula` +
  `start_minimised_to_tray` toggles

## Hard rules (do not reverse)

1. Never animate the main `tk.Canvas` per-frame  
2. No fabricated numbers — build a source or omit  
3. Import tokens from `obsauto/design_v3.py` only  
4. Macropad stays empty until HID + scan-code bindings exist  
5. No ffmpeg Length/thumbs until that dependency is decided  

## Still out of scope unless Anthony asks

1. ffmpeg Length/thumbs  
2. Live `GetSourceScreenshot` preview (repaint cost)  
3. HID macropad subsystem  
4. `pyinstaller nebula.spec`  

## Verify

```bat
python tests/test_design_v3.py
python tests/test_classifier_appid.py
python tests/test_settings_bool.py
python tests/test_monitor_stats.py
python tests/test_views.py
python tests/test_frame_pacing.py
python main.py
```

```bat
copy "C:\Users\antho\nebula\design\ui-v3\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md" "C:\Users\antho\Downloads\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md"
```
