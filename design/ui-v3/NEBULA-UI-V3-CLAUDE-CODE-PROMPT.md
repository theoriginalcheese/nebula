# Paste into Claude Code — Nebula UI v3 refine

**Copy this file to** `C:\Users\antho\Downloads\NEBULA-UI-V3-CLAUDE-CODE-PROMPT.md`
so Claude Code can open it from Downloads. Work in the local Nebula repo
(`C:\Users\antho\nebula` or wherever you clone `theoriginalcheese/nebula`).

**Updated:** 2026-07-26 — Cursor Cloud Agent. The **main framework is already built**
on `main`. This prompt is for **refinement**, not a greenfield rebuild.

---

Hi — pick up **Nebula UI v3 refinement**. Nebula is a Windows desktop app
(Python + CustomTkinter on a `tk.Canvas`) that watches the foreground game, drives
OBS over obs-websocket v5, and sorts recordings into per-game folders.

## What is already done (do not rebuild)

The Claude Design project
`https://claude.ai/design/p/19d87879-67c8-4a4e-8eb1-d4fbd327a23a?file=Nebula+UI+Mockups+v3.dc.html`
was imported locally. Spec + all seven build-order steps are on `main`.

| Area | Where |
|------|--------|
| Mockup + DS (local, no MCP needed) | `design/ui-v3/Nebula UI Mockups v3.dc.html`, `support.js`, `_ds/nocturne-…/` |
| Spec authority | `design/ui-v3/BUILD-SPEC.md` (wins over frames) |
| Frame notes 2a–2k | `design/ui-v3/FRAMES.md` |
| Contract as code | `obsauto/design_v3.py` — **import tokens from here; never re-declare literals** |
| Full UI | `obsauto/gui.py` — chassis, hero enum, clips, settings, games, toast, mini overlay |
| Static randomised backdrop | `theme_art.generate_backdrop_v3()` |
| Tray / icons | `tray_app.py`, `icon_art.py` |
| Cursor rules | `.cursor/rules/nebula-ui-v3.mdc` |
| Long brief | `CURSOR-HANDOFF.md`, living paste prompt `CURSOR-PROMPT.md` |

View the mockup: open `design/ui-v3/Nebula UI Mockups v3.dc.html` in a browser
(needs network for Geist + Phosphor CDNs).

**Do not** re-import via `claude_design` / DesignSync unless the remote mockup
changed — the local tree is the source of truth for this machine.

## Authority order

```
design/ui-v3/BUILD-SPEC.md
  > FRAMES.md / Nebula UI Mockups v3.dc.html
  > Nocturne styles.css (provenance only — do NOT link it)
```

Nocturne (`#161826`, Inter) is **not** the v3 look. v3 is **Nebula Deep**
(`#100D1C`, Geist → Segoe UI Variable / Cascadia Mono) via `design_v3.py`.

## Hard constraints (outrank the mockup)

1. **Never animate the main `tk.Canvas` per-frame.** Any change ≈100ms full-window
   composite. Aurora/star *motion* and pointer spotlight are intentionally **static /
   omitted**. Backdrop is seeded once at launch. `tests/test_frame_pacing.py` guards this.
2. **No fabricated UI numbers.** Build a real source or omit the element. Never ship a
   plausible `0` that means "not implemented".
3. Never `obs.connect()` on the Tk thread — worker + `_ui()`.
4. `except X as e` unbinds `e` at block exit — bind to a local before any `after()`/`_ui()` closure.
5. Logging coalesced (`_log` → buffer → `_flush_log`); `_regen_glass()` stays cached.
6. Offloader: copy → SHA-256 verify → only then delete local. Clips delete must respect that.
7. User data via `obsauto/paths.py` `APP_DIR` — never `os.path.dirname(__file__)` for writes.

## Decisions already made — do not reverse

- Background: **static**, randomised per launch (`BACKGROUND_MOTION_UNUSED` quarantined).
- Window: **fixed-pixel 1280×808** × `self.scale` (no live resize reflow yet).
- Macropad pane: **honest empty** until an HID + scan-code binding layer exists.
- Settings sections follow `settings_spec.GROUPS` (covers all `DEFAULTS`), not only frame 2c’s five names.

## Refine next (priority order)

Do these one at a time; keep tests green; do not invent data.

### 1. Fold the transitional Activity view
v3 has no standalone Activity page — the log is a dashboard block. `gui.RAIL_VIEWS`
already excludes it, but `_build_activity_view` still exists and `_log()` dual-writes.
Remove the dead view cleanly without breaking the dashboard console.

### 2. Wire real sources for remaining mockup gaps
| Gap | How |
|-----|-----|
| Scene `WxH · fps` | OBS `GetVideoSettings` — show only when connected |
| Bitrate | Already derived from status deltas — keep the “nothing until two samples” rule |
| `Auto-culled` / `Idle pauses` tiles | Add counters in `Monitor`, or keep tiles omitted |
| Clip **Length** + **thumbnails** | Needs ffprobe/ffmpeg — new dependency; decide before coding |
| Steam AppID / “seen N×” on Games | Classifier has no fields yet — extend storage or omit |

### 3. Macropad (only if you want the subsystem)
Order: (a) HID input layer, (b) persisted binding map in `config.json` by **scan code**
(`toggle_hotkey_scancode`; vault `asus-m4-fan-key`), (c) then the 2e pane. Until then leave empty.

### 4. Visual fidelity polish against the open mockup
Open the `.dc.html` beside a live `python main.py` window. Prefer
`tests/test_fidelity.py` for mechanical rules. Do not add canvas animation to “match” CSS.

### 5. Package
When happy: `pyinstaller nebula.spec` → `dist/Nebula.exe` (exe does not track source).

## Verify before claiming done

```bash
cd C:\Users\antho\nebula   # or your clone
pip install -r requirements.txt
python tests/test_design_v3.py
python tests/test_fidelity.py
python tests/test_views.py
python tests/test_clips.py
python tests/test_toast.py
python tests/test_tray.py
python tests/test_step7.py
python tests/test_frame_pacing.py   # needs a real desktop session; briefly shows the window
python main.py
```

⚠️ Async UI tests need a real `mainloop()` — `update()`-pumping hides worker results
(`_ui()` swallows cross-thread `after()` failures).

## Memory (Anthony’s vault — laptop only)

Durable notes → `C:\Users\antho\Claude Memories\claude-memory` only.
Read `memory/index.md` first. New notes: Claude frontmatter + `metadata.origin: cursor`
(or Claude Code’s equivalent), pointer lines in **both** `memory/index.md` and
`memory/MEMORY.md`. Related: `nebula-ui-v3`, `nebula-aurora-ui`, `nebula-dpi-scaling`.

## Start command for this session

1. `git pull origin main`
2. Open `design/ui-v3/Nebula UI Mockups v3.dc.html` in a browser
3. Read `CURSOR-HANDOFF.md` §2 + `design/ui-v3/BUILD-SPEC.md`
4. Pick **one** refine item above (start with #1 unless told otherwise)
5. Implement + run the relevant tests; update the `<!-- STATE:BEGIN -->` block in
   `CURSOR-PROMPT.md` when you land work
