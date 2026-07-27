# Paste-into-Claude prompt — Nebula UI v3 final polish

**Purpose:** Cursor has finished the implementable v3 work on this machine
(Strix-laptop). Paste everything below the line into Claude Code for live-OBS
visual QA, packaging, and the few remaining product decisions that need a human.

**Do not re-implement the chassis / hero / tray / toast / panes.** Those are done
and tested. Your job is the last millimetre.

---

Hi — you're finishing **Nebula UI v3** after Cursor. Nebula is a Windows desktop
app (Python + CustomTkinter on a `tk.Canvas`) that watches for the active game,
drives OBS over obs-websocket v5, and sorts recordings into per-game folders.

## Read first (in this order)

1. `CURSOR-HANDOFF.md` — especially §2 (Tk collisions) and §4 (repo invariants).
2. `design/ui-v3/BUILD-SPEC.md` — authority. *"If a frame and this table disagree,
   this table wins."*
3. `design/ui-v3/FRAMES.md` — frames **2a–2k**; **2l is the build-spec sheet**,
   not a UI frame (already transcribed).
4. `CURSOR-PROMPT.md` (STATE block) + this file.
5. Vault notes: `nebula-ui-v3`, `nebula-aurora-ui`, `obs-footage-sacred`.

Open the mockup in a browser (needs network for Geist/Phosphor CDNs):
`design/ui-v3/Nebula UI Mockups v3.dc.html`.

There is **no Claude Design MCP required** — the project is already imported under
`design/ui-v3/`. Nocturne (`_ds/nocturne-*/`) is provenance only; **do not link it**.
Tokens live in `obsauto/design_v3.py`.

## What Cursor just closed (do not redo)

- All seven build-order steps (chassis → hero → tray → toast → clips → settings →
  games / honest macropad / mini overlay).
- Fine-detail fidelity (`tests/test_fidelity.py`).
- **Removed** the transitional standalone Activity view — log is dashboard-only.
- **Real OBS metadata** (fetched on a worker, never the Tk thread):
  - Titlebar: `OBS {major.minor} · host:port` via `GetVersion`
  - Hero chip: `WxH · N fps` via `GetVideoSettings` (`format_video_label`)
  - Scene caption/chip via `GetCurrentProgramScene`
  - Settings OBS footer: `Connected to OBS … — handshake N ms` + **Test again**
- Titlebar circle buttons are **30px** hit targets (was 26).
- Frame pacing still **p50 ~16ms**; no per-frame canvas animation.

## Your checklist — only these remain

### A. Live visual QA (with OBS running)

```
python main.py
```

Compare against frames 2a / 2f–2h / 2i–2k. Note mismatches in a short list — fix
only things that are *wrong against the contract*, not taste.

Especially verify:

- [ ] Titlebar shows real OBS version after connect (not "connected" forever).
- [ ] Hero res/fps chip fills after connect and clears on disconnect.
- [ ] Settings → OBS group footer handshake ms matches a fresh connect.
- [ ] Ember leads **only** on disconnected hero / error toast / live-error paths.
- [ ] `−` and `×` both hide; Quit only from tray.
- [ ] Mini overlay refuses while idle; closes when recording ends.
- [ ] Toast is single-slot; replace resets the 4s drain.

### B. Rebuild the frozen exe

Dev and frozen **do not share data** (`APP_DIR` next to the exe vs repo root).

```
pyinstaller nebula.spec
```

Then smoke `dist/Nebula.exe` once (single-instance mutex will fight a source run —
quit `python main.py` first). Read `dist/logs/obsauto.log` if anything looks off.

### C. Product decisions that still need a human (do not invent data)

| Gap | Why it's still open | Acceptable resolutions |
|---|---|---|
| Clip **Length** + **thumbnails** (2b) | Needs ffmpeg/ffprobe — not a dependency today | Add ffmpeg **or** keep omitted |
| **Auto-culled** / **Idle pauses** tiles (2a) | Nothing in `Monitor` counts them | Add counters **or** keep the current two-tile honesty |
| Live **scene preview** frames | `GetSourceScreenshot` = canvas composite every tick — fatal here | Keep stylised tile; never poll screenshots on a timer |
| **Mic** meter on hero | Needs OBS input volume polling | Wire `GetInputAudioBalance` / meters **or** omit |
| **Mark clip** button | No backend | Stay omitted until Replay Buffer / chapter API exists |
| **Macropad** (2e) | No HID layer in `obsauto/` | Stay honest-empty until: HID input → `config.json` bind map by **scan code** → pane |
| Phosphor Light vs Segoe Fluent Icons | Phosphor TTF not installed | Bundle a Phosphor TTF into `RESOURCE_DIR` **or** keep Fluent (`ICON_GLYPHS`) |
| Resizable window (1080×700) | Fixed-pixel `ScaledCanvas` | Keep fixed 1280×808 × `self.scale` unless you deliberately reflow |

### D. Docs / vault hygiene after you finish

- Keep `CURSOR-PROMPT.md` STATE block current if you land more commits.
- Durable conclusions → Obsidian vault only
  (`C:\Users\antho\Claude Memories\claude-memory`), mirror **both**
  `memory/index.md` and `memory/MEMORY.md`. Do not put durable notes in the repo.

## Hard rules (outrank the mockup)

1. **Never animate the main `tk.Canvas` per-frame.** `tests/test_frame_pacing.py`.
2. **No fabricated UI numbers.** Build the source or omit the element.
3. **Never `obs.connect()` on the Tk thread.**
4. **`except X as e` unbinds `e`** — bind to a local before any `after()` / `_ui()` closure.
5. Coalesced logging; cached `_regen_glass()`; offload copy-verify-then-delete;
   GameSync never PUTs against an unknown remote.

## Tests to re-run after any edit

```
python tests/test_design_v3.py
python tests/test_fidelity.py
python tests/test_obs_meta.py
python tests/test_views.py
python tests/test_tray.py
python tests/test_toast.py
python tests/test_clips.py
python tests/test_settings.py
python tests/test_step7.py
python tests/test_async_connect.py
python tests/test_frame_pacing.py
```

Anything async **must** use a real `mainloop()` — `update()`-pumping hides
cross-thread `after()` failures.

## Done when

1. Live QA checklist above is ticked (or mismatches fixed).
2. `dist/Nebula.exe` rebuilt and smoke-tested once.
3. Any decision from table C is either implemented *with a real source* or
   explicitly left omitted with a one-line note in the vault / `CURSOR-PROMPT`
   STATE — never a fake `0`.
