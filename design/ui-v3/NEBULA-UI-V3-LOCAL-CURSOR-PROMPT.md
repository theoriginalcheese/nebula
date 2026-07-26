# Paste into **Local Cursor** (Desktop Agent) — Nebula UI v3 build pass

**Not for Claude Code.** This is the structural build pass on your Windows laptop.
When this pass is done, hand off to Claude Code with  
`design/ui-v3/NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md` for final live polish.

---

## Setup (do this first)

1. Cursor Desktop → **File → Open Folder** → `C:\Users\antho\nebula`
2. Agent panel → mode **Local** (not Cloud)
3. Pull the work branch:

```bat
cd /d C:\Users\antho\nebula
git fetch origin
git checkout cursor/implement-mockup-v3-2b0d
git pull origin cursor/implement-mockup-v3-2b0d
```

4. Open the mockup beside the app (needs network for Geist/Phosphor CDNs):

```bat
start "" "C:\Users\antho\nebula\design\ui-v3\Nebula UI Mockups v3.dc.html"
```

5. Run the app when you need to verify:

```bat
pip install -r requirements.txt
python main.py
```

---

## Your job

Continue implementing **Nebula UI Mockups v3** into the real CustomTkinter app until the
structure and behaviours match the mockup. You are the builder. Claude Code will do the
final pixel / live-OBS refinement after you.

### Authority (in order)

1. `design/ui-v3/BUILD-SPEC.md` — wins on conflict  
2. `design/ui-v3/Nebula UI Mockups v3.dc.html` + `FRAMES.md`  
3. `CURSOR-HANDOFF.md` §2 — hard collisions with this repo  
4. `obsauto/design_v3.py` — tokens / geometry / hero enum (import these; don’t invent hex)  
5. Do **not** link Nocturne `_ds/.../styles.css` into the app  

### Already shipped on this branch (don’t rebuild from scratch)

Build order **1–7** plus a fidelity pass:

- Aurora → v3 chassis (1280×808, rail 232, hero enum, stats, activity)
- Toast (replace-in-place, dismiss X), tray, mini overlay
- Clips rows (Play / Reveal / Delete) — Length/thumbs still omitted
- Settings (mono keys, blur-write, Reveal, Test again, Browse, password eye, Launch OBS /
  Start minimised toggles)
- Games decide card, AppIDs, seen N×
- Hero: watching foreground line, disconnected countdown, Mark clip → `CreateRecordChapter`
- Macropad: **honest empty** (no fake HID)

Read `obsauto/gui.py`, `obsauto/design_v3.py`, and the mockup before editing.

---

## Build this pass (Local Cursor scope)

Work top-down against the open mockup. Prefer real data or an honest empty — never filler.

### A. Side-by-side chassis & dashboard (2a / 2f–2h)

- Diff live UI vs mockup for spacing, type sizes, rail storage card, pane header, hero
  layout (preview column width `PREVIEW_W`, button row, readouts).
- Hero states must stay one enum (`_set_hero_state`) — only eyebrow / tint / actions /
  preview visibility swap; nothing else on the dashboard jumps.
- Bitrate: keep Δbytes/Δt or blank — never invent `14.2 Mb/s`.
- Scene preview: static placeholder is fine; **do not** poll `GetSourceScreenshot` on a
  timer (full-window composite cost — see handoff §2.1).
- Ember = live + errors only. No second accent hue. No emoji.

### B. Clips (2b) — structure only

- Search / sort / By-game / row actions already started — finish any missing chrome.
- **Length + thumbnails:** only if you add an **optional** ffmpeg/ffprobe soft-dep that
  fails soft when missing. Otherwise leave omitted and document why.
- Empty state = the `min_clip_seconds` note only (no fake rows).

### C. Settings / Games polish (2c / 2d)

- Match section copy, field order, footer connection card, Games list density to the frame.
- Keep write-on-blur. Keep AppID / seen-count real (Classifier + steam index).

### D. Macropad (2e) — leave empty unless you build the real layer

Do **not** draw a connected pad with a fake HID id.  
If you start Macropad for real, do it in order: (1) HID input, (2) scan-code bindings in
`config.json`, (3) the pane. Bindings by **scan code**, not character.

### E. Tests before you stop

```bat
python tests/test_design_v3.py
python tests/test_classifier_appid.py
python tests/test_settings_bool.py
python tests/test_monitor_stats.py
python tests/test_views.py
python tests/test_frame_pacing.py
python tests/test_fidelity.py
python main.py
```

`test_frame_pacing.py` must keep passing — no per-frame canvas animation timers.

Commit on `cursor/implement-mockup-v3-2b0d` (or a `cursor/...-2b0d` branch off it). Push.

---

## Hard rules (do not reverse)

1. **Never animate the main `tk.Canvas` per-frame** — any canvas mutate ≈ full window composite  
2. **No fabricated numbers** — build a source or omit the element  
3. Tokens from `obsauto/design_v3.py` only  
4. Never `obs.connect()` on the Tk thread — worker + `_ui()` / `root.after`  
5. `except X as e:` unbinds `e` — bind `error = exc` before any deferred closure  
6. Logging coalesced — don’t write the textbox from `_log` directly  
7. User data via `APP_DIR` (`obsauto/paths.py`), never `os.path.dirname(__file__)`  
8. Offloader / GameSync invariants stay sacred (see `CLAUDE.md`)  

---

## Stop here — then hand to Claude Code

When the structure matches the mockup and tests pass, **stop**. Do not chase final pixel
nits or live-OBS edge polish.

Hand off:

1. Update `design/ui-v3/NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md` with what you shipped / what’s left  
2. Copy it to Downloads:

```bat
copy "C:\Users\antho\nebula\design\ui-v3\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md" "C:\Users\antho\Downloads\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md"
```

3. Tell Anthony: open that file in **Claude Code**, mockup + live Nebula side by side, for
   final detail refinement (spacing, live OBS, remaining soft-deps).

### Explicitly for Claude Code later (not you, unless asked)

- Pixel-perfect spacing / type against the open `.dc.html`
- Live OBS soak (connect, record, pause, mark chapter, disconnect countdown)
- ffmpeg Length/thumbs decision + implementation
- HID macropad subsystem
- `pyinstaller nebula.spec`
