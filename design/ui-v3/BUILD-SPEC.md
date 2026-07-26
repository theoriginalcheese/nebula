# Nebula UI v3 — Build spec (section 05, "the contract")

Transcribed verbatim from `Nebula UI Mockups v3.dc.html` § *05 · Build spec*.

> "Every number the frames above imply, written down. **If a frame and this table disagree,
> this table wins.**"

Source project: Claude Design `19d87879-67c8-4a4e-8eb1-d4fbd327a23a`,
file `Nebula UI Mockups v3.dc.html`. Design system: Nocturne
(`_ds/nocturne-ca27441c-01cc-44a6-99a7-7317fdeecd65/`).

⚠️ **Read `../../CURSOR-HANDOFF.md` before implementing.** Three parts of this spec collide
with hard, measured constraints in this repo. They are listed there with the resolutions.

---

## Colour tokens — "Nebula Deep"

| Hex | Role |
|-----|------|
| `#100D1C` | window ground |
| `#12101F` | panel base |
| `#181428` | card core |
| `#241E44` | raised surface, keycaps |
| `#8B7CF6` | accent — lines, dots, glow |
| `#B9AEF9` | accent text / icons on dark |
| `#FF5C7A` | ember — live + errors ONLY |
| `#F5F3FF` | primary text |
| `#9A93C4` | secondary text |
| `#8B84B8` | tertiary / captions |
| `#736BA4` | eyebrow labels, mono meta |

- Hairlines are `rgba(245,243,255, 0.055–0.09)`, **never a solid grey**.
- Tinted fills are the accent or ember at **0.06–0.16 alpha**.
- **No other hues exist in this app** — log tag colours stay as `LOG_TAG_COLORS` in `gui.py`.

## Geometry & type

| Item | Value |
|------|-------|
| Window | **1280×808** core, 6px tray |
| Min window | **1080×700** |
| Radii | 28 tray / 22 core / 17 card / 12 tile / 9 control |
| Nesting rule | `inner = outer − padding` |
| Titlebar | h 46, pad 18 left / 8 right |
| Rail | w **232**, pad 16/12, item h 38, gap 3 |
| Pane header | h 62, pad-x 26 |
| Content | pad 26, stack gap 16 |
| Controls | pill h 40 · field h 36 · icon btn 26–30 |
| Hit target | ≥30px, 8px between siblings |
| UI face | Geist 300/400/500 — **ship as Segoe UI Variable** |
| Numeric face | Geist Mono — **ship as Cascadia Mono** |
| Timer | 34 / 400 / −0.02em |
| Game title | 25 / 500 / −0.02em |
| Pane title | 19 / 500 |
| Body / rows | 13 · 12.5 · 12 |
| Meta / mono | 11.5 · 10.5 |
| Eyebrow | 9.5 / uppercase / 0.22em tracking |

## Config map — control → `config.json`

| Control | Key |
|---------|-----|
| Host / Port / Password | `obs_host`, `obs_port`, `obs_password` |
| OBS executable | `obs_path` |
| Reconnect every | `reconnect_interval_seconds` · seconds, default **10** |
| Recording folder | `recording_root` |
| Discard clips under | `min_clip_seconds` · seconds, default **10** |
| Pause after idle | `idle_timeout_seconds` · seconds, default **4** |
| Window poll rate | `poll_interval_seconds` · seconds, default **1** |
| Keep-alive apps | `keep_alive_audio_processes[]` |
| Toggle hotkey | `toggle_hotkey` |
| … bind by scan code | `toggle_hotkey_scancode` |
| Shared classifications | `sync_folder` |

Rules:
- Every `*_seconds` key is in seconds — **render the unit suffix in every field and every
  status string**.
- **Write on blur, not per keystroke.**
- Show the **saved timestamp** in the pane header.
- **Never silently drop an unknown key** — merge over `DEFAULTS` and keep the rest.

## Icon legend — Phosphor **Light**

Light weight everywhere at 12–24px. The **only** Fill glyphs are `ph-circle`
(status dots, 6–8px) and `ph-square` (stop, 9–11px).

| Glyph | Use |
|-------|-----|
| `broadcast` | Dashboard |
| `film-strip` | Clips |
| `game-controller` | Games |
| `keyboard` | Macropad |
| `sliders-horizontal` | Settings |
| `record` | start |
| `pause` | pause |
| `play` | resume |
| `scissors` | mark clip |
| `stack-simple` | scene |
| `plugs` | disconnected |
| `plugs-connected` | connected |
| `hard-drives` | storage |
| `timer` | idle |
| `moon` | idle pause |
| `command` | hotkey |
| `steam-logo` | rescan |
| `folder-open` | reveal |
| `trash` | delete clip |
| `arrows-out-simple` | show window |
| `arrows-in-simple` | collapse mini |
| `sign-out` | quit (tray only) |
| `minus` | hide to tray |
| `x` | hide to tray |

## Motion & states

| Item | Value |
|------|-------|
| Easing | `cubic-bezier(.32,.72,0,1)` |
| Hover / press | 500ms / 120ms, scale .98 |
| Pane change | opacity + 8px rise, 260ms |
| Live dot | 1.9s pulse, opacity .35→.95 |
| Toast in / out | rise 16px 320ms / fade 200ms |
| Focus ring | 2px `#8B7CF6`, offset 2 |
| Disabled | opacity .45, no hover |

- **Never animate width / height / top / left.**
- The elapsed timer updates **once per second** and must not reflow its neighbours —
  **tabular figures, fixed width**.

## Living background — exact values

Two layers, both **randomised at launch so no two sessions look alike**, and both rendered
inside the app window as well as behind it. Neither layer is driven by the pointer.

| Layer | Values |
|-------|--------|
| Aurora blobs | 3 per surface, blur 54–110px |
| … alpha | .22 accent · .22 deep · .07 ember |
| … cycle | random 46–92s, negative delay |
| … travel | ≤9% translate, scale 1→1.14 |
| Star drift | 2 layers, positions random per load |
| … speed | near 120–170s, far 190–260s |
| … dot size | 1–2px, alpha .2–.85 |
| Vignette | transparent 46% → black .55 |
| Pointer spotlight | 300px, accent .22, **cards only** |
| Pointer lean | ≤16px page, ≤9px in-window |
| Cost budget | transform + opacity only |

- **Reduced motion keeps the colour.** Under `prefers-reduced-motion` — or the Settings
  toggle — every layer stays exactly where it is via `animation-play-state: paused`.
  Nothing is removed, nothing goes flat.
- In-window panels sit on `rgba(16,13,28, 0.72–0.92)` so the aurora reads through them while
  text keeps its contrast. **A fully opaque panel over the aurora is a bug.**

## Build order & don't-forget

1. **Chassis first.** Tray, core, titlebar, rail, empty pane. Nothing else until this matches
   **2a** exactly.
2. **Hero card + its 3 states (2f–2h) driven by one state enum.** Stat tiles and activity log
   next.
3. **Tray + window chrome.** `−` and `×` both hide; **Quit only in the tray menu**; tray icon
   reflects state.
4. **Single-slot toast.** Replace-in-place, 4s drain, hover freeze. **Build the replace path
   before the visuals.**
5. **Clips pane** with real thumbnails, length, size, and the three row actions.
   Empty state = the min-clip note only.
6. **Settings** with the key labels visible in mono under each field — **they are part of the
   design, not a debug aid**.
7. **Games, Macropad, mini overlay last.** Mini overlay **never shows while idle**.

Invariants:
- No emoji, no gradient floods, no second accent hue. **Ember is live-and-errors only.**
- **Every card is two layers**: tinted outer shell, darker inner core. A flat card is a bug.
- Rules and dividers **fade at both ends over 32–48px**. No hard-stopped 1px greys.
- Trailing icons on primary pills live in their own **26–28px circle**, flush to the right
  padding.
- The background is **randomised per launch** — never hard-code blob positions or star
  coordinates.
