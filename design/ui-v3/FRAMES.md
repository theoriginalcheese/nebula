# Nebula UI v3 — Frames 2a–2k

Content extracted from `Nebula UI Mockups v3.dc.html`. The frames show *intent*; where a
frame and [BUILD-SPEC.md](BUILD-SPEC.md) disagree, **the spec wins** (the doc says so).

> ⚠️ Every number in these frames is **mockup filler**. See the "fabricated data" section of
> [`../../CURSOR-HANDOFF.md`](../../CURSOR-HANDOFF.md) — this repo has a standing rule that a
> value with no real source is omitted, not invented.

---

## 01 — The chassis (frame 2a)

> "1280×808 core in a 6px tray. Titlebar, 232px rail and content pane **never change between
> views** — build this once."

**Titlebar** (h 46) — `Nebula` · version badge (`0.9.2`) · `Monitoring` + hotkey keycap ·
right side: `OBS 30.2 · localhost:4455`, minimise, close.

**Rail** (w 232) — eyebrow `Session`, then:
`Dashboard` · `Clips` (count badge) · `Games` (count badge) · `Macropad` · `Settings`.
Foot of rail: storage card — `D:/OBS Recordings`, a % bar, `1.42 TB free of 3.63 TB`.

**Pane header** (h 62) — eyebrow `Live session`, title `Dashboard`, right-aligned ghost
actions `Open folder`, `Rescan Steam`.

**Hero card** — double bezel (`tray 5 · r22 / r17`), left column + right column:
- Left: eyebrow badge `Recording`, game title `Helldivers 2`, sub
  `helldivers2.exe · Steam 553850`, three readouts (`Elapsed`, `File size`, `Bitrate`),
  then the button row `Stop recording` / `Pause` / `Mark clip`.
- Right: 16/9 scene preview with `Live` chip, `2560×1440 · 60 fps`, caption
  `OBS scene preview`, below it `Scene — Game Capture` and a `Mic` meter.

**Stat tiles** (4 across) — `Clips today`, `Recorded`, `Auto-culled`, `Idle pauses`.

**Activity** — header `Activity` + `All tags` filter + `Copy log`; colour-tagged rows:
```
21:14:02  [OBS]      Recording started → Helldivers 2
21:13:58  [Monitor]  Foreground window changed — helldivers2.exe
21:13:58  [Steam]    Matched appid 553850 from library cache
20:58:41  [Audio]    discord.exe active — idle pause suppressed
20:22:17  [OBS]      Clip discarded — 6s under min_clip_seconds
```

Annotation pins on this frame: `h 46` (titlebar), `w 232` (rail), `pad 26`, `gap 16`.

---

## 02 — The panes

> "Same chassis, content pane swapped. Rail and titlebar are omitted here on purpose — render
> them exactly as 2a. Each pane is drawn at its true size: **1048×746**."

### 2b — Clips

Header: `418 clips · 1.9 TB` / title `Clips` / `Search clips` field / `Newest` sort.

Left column `By game` — per-game counts, then `Reveal recording root`.

Table columns: **Clip · Length · Size · Recorded · Actions**. Each row = thumbnail + title
(`Helldivers 2 — 2026-07-23 21:14`) + relative path
(`Helldivers 2/2026-07-23 21-14-02.mkv`), length, size, recency (`2 min ago`, `Today 18:02`,
`Yesterday`, `Tue`). Three row actions (spec § icons: `folder-open` reveal, `scissors` mark,
`trash` delete).

Footer note: *"Clips under `min_clip_seconds` (10s) are deleted automatically and never listed
here."* — and per the build order, this note **is** the entire empty state.

### 2c — Settings

Header eyebrow: `Writes config.json on blur` · title `Settings` · right: `Saved 21:12:04`.

Section nav: `Connection` · `Storage` · `Idle & audio` · `Hotkey` · `Sync`.
Meta row: `Config file  ../config.json  [Reveal]`.

*Connection* section as drawn — intro line "Nebula launches OBS if it isn't running, then
connects over WebSocket", then fields, **each with its config key in mono under the label**:

| Label | Key shown | Value in frame |
|---|---|---|
| Host | `obs_host` | localhost |
| Port | `obs_port` | 4455 |
| Password | `obs_password` | •••••••••• |
| Reconnect every | `reconnect_interval_seconds` | 10 s |
| OBS executable | `obs_path` | `C:/Program Files/obs-studio/bin/64bit/obs64.exe` + `Browse` |

Hint under `obs_path`: *"Missing path is skipped silently — per-machine setting."*
Toggles: `Launch OBS with Nebula` ("Also relaunches if OBS crashes mid-session"),
`Start minimised to tray` ("Window opens hidden; tray icon still shows state").
Footer: `Connected to OBS 30.2 — handshake 41 ms` + `Test again`.

### 2d — Games

Header: `3 awaiting your call` / `Games` / `Rescan library`.

**Unclassified** block — one candidate at a time:
`Vintage Story` · `vintagestory.exe · not in Steam library · seen 4×` ·
buttons `It's a game` / `Not a game`.

`Games 142` list with AppIDs (`Helldivers 2  553850`, …), footer
*"Stored in `games.json` · shared via sync folder"*.

`Not games 67` list (`Discord` tagged *keep-alive*, `Chrome`, `Explorer`, `Game Bar`,
`Steam`), footer *"Right-click a row to move it back to Games."*

### 2e — Macropad

Header: `3×3 pad · connected` / `Macropad` / `HID 0x1209:0xA1B2`.

`Key map` — 3×3 grid: `Start / stop`, `Pause`, `Mark clip`, `Mute mic`, `Scene 1`, `Scene 2`,
`Idle off`, `Open folder`, `Unassigned`.
Hint: *"Drag an action from the right onto a key. Long-press a key on the device to identify
it here."*

`Actions` list: `Toggle recording`, `Toggle monitoring`, `Mark clip`, `Switch scene…`,
`Mute source…`, `Run command…`.
Footer: `Last key press  key 1 · 21:14:02 · Start / stop`.

> 🚩 **There is no HID binding layer in this codebase.** See the handoff — this pane is the
> single largest new subsystem in v3 and cannot be drawn "connected" until one exists.

---

## 03 — Hero card states

> "Only the hero card changes; **nothing else on the dashboard moves**. Same 22px padding,
> same button row position — swap the eyebrow, the tint, and the primary action."

| Frame | State | Eyebrow | Body | Actions | Note |
|---|---|---|---|---|---|
| **2f** | Idle — watching | `Idle — watching` | `No game in focus` / "Foreground: chrome.exe — classified as not a game." | `Record anyway`, `Pause monitoring` | neutral tint, **no timer, no scene preview** |
| **2g** | Paused | `Paused — idle 4 s` | `Helldivers 2` · `01:47:22` | `Resume`, `Stop & save` | accent tint, **timer frozen at 60% opacity** |
| **2h** | Disconnected | `OBS disconnected` | `Can't reach OBS` / "Retrying every 10s — next attempt in 6s. Launching from `obs_path` …" | `Retry now`, `Connection settings` | **the only place the ember hue leads** |

Plus the fourth state drawn in 2a: **Recording** (`Stop recording`, `Pause`, `Mark clip`).

---

## 04 — Off-window surfaces

> "The three surfaces the last build got wrong. **Read the rules under each frame literally.**"

### 2i — Toast

`Recording started` / `Helldivers 2 · D:/OBS Recordings`

- **One toast, ever.** A new event **replaces the current one in place** — never a stack,
  never a queue.
- Bottom-right of the **active screen**, 24px from both edges, above the taskbar.
- **4s life, 2px drain line left→right.** Replacing an event **resets the line to full**.
- **Hover freezes the drain**; leaving resumes it. Click anywhere focuses the window.
- Icon + tint per event: start / stop → **ember**, pause / resume → **accent**,
  error → **ember**.

### 2j — Tray + mini

Header block: `Recording` / `Helldivers 2 · 01:47:22`.
Menu: `Show Nebula`, `Pause recording`, `Stop recording`, `Monitoring on`,
`Open recordings`, `Quit Nebula`.

- **Both `−` and `×` hide to tray. Quit exists only in this menu.**
- Tray icon states: idle = **accent outline**, recording = **ember filled**,
  disconnected = **neutral with a slash**.
- Single click = show window. Right click = this menu. Tooltip = game + elapsed.
- **The header block is not a menu item** — not hoverable, not clickable.

### 2k — Mini overlay

`01:47:22` / `Helldivers 2`

- **296×54**, frameless, always-on-top, drag anywhere on the body.
- Snaps to the nearest screen corner within 32px; **remembers position per monitor**.
- Drops to **55% opacity after 3s** without the pointer; full opacity on hover.
- Collapse restores the main window; **it never appears while idle**.
