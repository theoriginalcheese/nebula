# BUILD-SPEC — nebula-mobile

> Source of truth for the iOS companion app. Transcribed from
> `Nebula Mobile.dc.html` (Claude Design project "Nebula UI mockups",
> `19d87879-67c8-4a4e-8eb1-d4fbd327a23a`) + `ios-frame.jsx` + `github.md`
> (the project's own provenance log). Imported 2026-08-28.

## Meta

| Field | Value |
|-------|-------|
| Slug | `nebula-mobile` |
| Product | Nebula iOS companion (not the desktop app) |
| Status | designed, live-interactive mockup, **not built** |
| Stack | **Expo / React Native** (chosen: Windows-friendly dev, EAS for device builds) |
| Upstream design source | `theoriginalcheese/nebula` repo, branch `main`, path `spike/web` (desktop web spike — not in this repo) |
| Mockup device frame | iOS 26 "Liquid Glass", 390×844, via `ios-frame.jsx` (`IOSDevice` etc.) — that file is a **preview harness**, not app code; do not port its inline-style React components verbatim, rebuild as RN components using the tokens below |

## Product framing (read this before building anything)

> "The desktop app is a six-pane console you sit in front of. The phone is
> not that. It is the two minutes you spend away from the machine."

The app keeps exactly four jobs and drops the rest:
1. **Is it recording** (Now screen)
2. **What did I catch** (Clips screen)
3. **Put the PC on this screen** (Remote screen — Moonlight launcher)
4. **Stop bothering me about that launcher** (Games/Classify — game-detection triage)

Settings detail, the macropad, and the desktop "customise" grid are explicitly
**desktop-only** — do not add them to the phone app.

## Screens / frames

See `FRAMES.md` for the full index. Eight frames exist in the mockup;
`github.md` (the project's sync log) records only six as of its last entry —
**Classify** and **Notifications** were added after that log entry, so treat
the `.dc.html` itself as the newer/authoritative source when the two disagree.

## Navigation

- **Primary nav is a floating pill tab bar**, 4 items, present on every
  in-app screen: **Now · Clips · Remote · Games**.
  - Container: `margin: 0 14px 26px`, `height: 64px`, `border-radius: 26px`,
    background `rgba(18,16,31,.72)`, `1px solid rgba(245,243,255,.08)`,
    `backdrop-filter: blur(22px)`, `grid-template-columns: repeat(4,1fr)`.
  - This is the **one place a real drop shadow is allowed**
    (`0 12px 34px rgba(0,0,0,.5)`) — elevation everywhere else is the
    lightness ladder, not a shadow (see Tokens § Elevation).
  - Active tab: icon+label at `--color-text-primary`; inactive at
    `--color-text-tertiary` (`#736BA4`), `color` transition `400ms` on the
    shared ease.
- **Disconnected** is not a tab — it's a state swap of the **Now** screen
  when the Tailscale link to the studio PC drops.
- **Classify** is reached *from* Games (tapping a detected item that needs a
  verdict); the tab bar still shows **Games** as active while on Classify.
- **Appearance** (settings) has **no shown entry point** in the mockup — none
  of the 4 tabs highlight when on it. Flag this to Anthony/design rather than
  inventing a settings icon; don't guess a gear-icon placement.
- **Notifications is not an in-app screen.** It's a mockup of the iOS **Lock
  Screen**, showing what the Live Activity / notifications look like from
  outside the app. There is nothing to route to — it documents OS-level
  surfaces the app must produce (see Screens § Notifications below).

## Tokens

**Important:** the Nocturne design system (`_ds/nocturne-…/`) is the meta
framework used to author the *mockup document's own chrome* (headers, the
frame gallery, the closing notes cards) — it is **not** what the iOS screens
inside the phone frames use. The phone UI defines its own token set, carried
over verbatim from the desktop app's `spike/web/tokens.css` (per `github.md`).
Use the table below for anything inside an `IOSDevice` frame; use Nocturne's
`readme.md`/`styles.css` only if you also touch this project's own docs.

### Colour

| Token | Value | Use |
|---|---|---|
| `--bg-page` | `#0A0812` | outermost background |
| `--bg-screen` | `#100D1C` | screen background inside the device frame |
| `--bg-card` | `#181428` | card / panel fill |
| `--bg-card-soft` | `rgba(245,243,255,.025)` on `rgba(245,243,255,.07)` border | secondary cards (Tailscale peers, NAS offload) |
| `--text-primary` | `#F5F3FF` / `#F7F5FF` | headings, primary values |
| `--text-secondary` | `#9A93C4` | body copy, meta |
| `--text-muted` | `#8B84B8` | subdued captions |
| `--text-label` | `#736BA4` | uppercase eyebrow labels, inactive tab |
| `--accent-default` | `#8B7CF6` (violet) | primary accent — user-selectable, see Appearance |
| `--accent-indigo` | `#6E8BF7` | accent preset |
| `--accent-cyan` | `#5AB6E8` | accent preset |
| `--accent-teal` | `#4FC7B8` | accent preset — also "success" (offload finished) |
| `--accent-amber` | `#E9B872` (picker swatch) / `#F5A623` (live) | recording/live state, disk warning |
| `--accent-magenta` | `#D471E0` | accent preset |
| `--danger` | `#FF5C7A` core / `#FFD3DC` text / `#FF9DB0` offline text | Stop button, offline/error state |
| `--gold-text` | `#FFE8BC` | live recording clock/numerals |

Six accent presets total (violet/indigo/cyan/teal/amber/magenta), carried
over verbatim from the desktop app. `EMBER` (the desktop's disconnected/error
red) is deliberately **not** reused for "recording" — one token, one meaning.

### Type

| Token | Value | Use |
|---|---|---|
| `--font-ui` | `'Plus Jakarta Sans', system-ui, sans-serif` | all headings, labels, body — substitutes for the desktop's Windows-only Segoe UI Variable |
| `--font-mono` | `'JetBrains Mono', monospace` | **every numeric readout**: clocks, bitrate, file size, ping ms, disk countdown |

Scale in use (not a formal ramp, taken as-observed): 60/42/32/27/23/21/17/
15.5/14.5/14/13.5/13/12.5/12/11.5/11/10.5/10/9.5/9px. Large title screens use
32px/700 weight (`Clips`, `Remote`, `Games`, `Appearance`); Classify uses
27px/700; section eyebrows are 9.5px/600, `letter-spacing:.16–.22em`,
uppercase, `--text-label` colour.

### Motion

- **One easing everywhere**: `cubic-bezier(.32,.72,0,1)` (the `--ease`
  token). Do not introduce a second curve.
- **Press feedback is a scale, never a colour change**: `transform:
  scale(.97)` on pill/rect buttons, `scale(.94)` on circular transport
  buttons and swatches — both on `:active`.
- **Motion carries state, never decoration.** Every animation ties to a real
  condition:
  - The recording arc spins only while recording; stops dead on stop.
  - The Moonlight orb quickens during handshake, turns gold when live.
  - Ribbon/list items stagger in once on arrival (`nm-in`), never loop.
  - The "dust constellation" (small tinted specks, `transform`/`opacity`
    only) bursts on the recording chip, sinks on the disconnected mark,
    orbits the Moonlight orb, scatters behind the accent picker.
- **Respect `--motion-scale`.** Appearance's Motion slider is real: at zero
  it stops every ambient animation across all screens. This is the
  accessibility hook (reduce-motion) — wire it to a real setting, don't fake
  the slider.

### Elevation

Elevation is a **lightness ladder**, not a shadow: cards lift by surface step
(`#100D1C → #181428`) plus a `1px` inset highlight
(`inset 0 1px 0 rgba(245,243,255,.08)`). The **only** real drop-shadow in the
system is under the floating tab bar, where blur needs to sell "above the
page." Do not add box-shadows to cards.

### Radii

Pills/buttons/tags: `999px` (fully round). Cards: `18–26px`. Icon buttons /
list-row icons: `13–22px` (roughly matching the desktop's 8px-radius-derived
scale, but the phone screens use larger absolute values throughout).

## Screens

### 1. Now (`f-now`) — default tab, home
- Nav row: Nebula wordmark + "Studio PC" subtitle, live status dot.
- Recording card: status chip (dust-burst icon + REC/PAUSED/STOPPED label),
  encoder readout top-right (`1080p60 · NVENC`), game title + scene name,
  decorative spinning arc/spark icon (spins only while recording), large mono
  clock, 3-stat grid (File / Bitrate / Disk).
- Transport: while recording/paused — Pause (60px circle) + Stop (76px
  circle, red glow, pulsing halo) side by side, both labelled. Once stopped —
  single gold "Record again" circle, replaces the pair (`nm-rise` entrance).
- Activity feed: timestamped icon rows (recording started, scene switched,
  replay buffer armed…).
- "Recording saved" toast: slides up from the bottom, auto-dismisses
  (`nm-toast` animation), shows file size.
- Disk-warning card style also appears here when relevant (see Notifications
  § Time Sensitive — same visual language, in-app version).

### 2. Disconnected (`f-offline`) — state swap of Now
- Triggered when Tailscale reports the studio PC offline.
- Nav subtitle becomes "No route" (red).
- Grey/"dead" starburst icon (desaturated, diagonal slash), dust motion
  switches from burst to **sink**.
- Headline "Can't reach Studio PC" + reassurance line ("nothing was
  recording when the link dropped, so no clip is at risk" — **only show this
  line if actually true**; don't hardcode it).
- "last seen HH:MM · Nm ago" pill.
- Primary CTA: **Try again**. Secondary CTA: **Wake over LAN**.
- Activity feed continues, now showing the offline event.

### 3. Clips (`f-clips`)
- Large title "Clips", search field ("Search clips").
- Horizontal filter chip row: All + one chip per recent game (toggleable,
  active/inactive visual states).
- Day-grouped list ("Today" section header) of clip cards: thumbnail, title,
  meta line.

### 4. Remote (`f-remote`)
- Large title "Remote".
- Hero Moonlight control: animated orb, 3 states —
  - **Ready**: "Studio PC is awake" / "Moonlight 6.1 · GeForce host paired.
    Stream will open at 1080p60 over Tailscale."
  - **Busy** (handshake): "Handshaking…" / "Negotiating the encoder over the
    tailnet. This is usually under two seconds."
  - **Live**: "Streaming · 1080p60" / "4 ms round trip, 18 Mb/s. Nebula keeps
    recording locally at full quality."
  - CTA pill relabels/re-icons per state (`{{ ctaLabel }}`, `{{ ctaGlow }}`).
- Tailscale peers card: eyebrow "Tailscale · N peers", per-peer row (name,
  online dot, ping in ms; offline peers dim + show "offline").
- NAS offload card: eyebrow "NAS offload", progress bar (masked-fade ends,
  scanning highlight sweep), "`X of Y · size`" counter, current-file line
  with throughput.
- Per-game Wake toggle list further down the screen (one toggle row per
  recent game — configures which titles trigger Wake-on-LAN).

### 5. Games (`f-games`)
- Large title "Games", "Seen while you were away" section.
- List of recently-detected executables as cards (title + placeholder art).
- Tapping an item that needs a verdict → Classify.

### 6. Classify (`f-classify`) — reached from Games
- Header: "Classify · tap a verdict".
- Per-item card: exe name, publisher, confidence badge, **5 signal rows**
  (fullscreen state, input device, GPU load, store-library membership,
  window-chrome) each with a coloured status dot + icon + text bound to
  live signals — this is the game/not-game heuristic surfaced to the user,
  not decided silently.
- Summary line ("`{{ verdict }}`, so Nebula is asking instead of guessing")
  with a warning icon when signals conflict.
- Actions: **"It is a game"** / **"Not a game"** (two large pill buttons),
  plus tertiary **"Skip for now"**.
- The mockup's built-in test queue is intentionally adversarial — useful as
  real QA fixtures, not just demo data:
  - *Sifu* — obvious game, all 5 signals agree (`high` confidence).
  - *Blender* — fullscreen + high GPU trips the naive heuristic, but
    keyboard/mouse-only + not-in-library + has menu chrome correctly flags
    it as **not** a game (`low` confidence, "trips every heuristic").
  - *Yakuza 0* — borderless window, low GPU, keyboard-only — looks like
    **not** a game by most signals, but is (`low` confidence, "hides from
    the heuristics"). Only "in Steam library" + "chrome hidden" catch it.
  - See `game_list.txt` in this folder for real exe-name examples the
    desktop classifier has seen (not wired into this screen's queue, but a
    reference for realistic test data).

### 7. Notifications (`f-notify`) — NOT an in-app screen
Mockup of the **iOS Lock Screen**, documenting the OS surfaces the app must
produce, not a screen to route to:
- **Live Activity** card: "Nebula is recording", game + resolution, live
  mono clock, masked-fade progress bar, inline Pause/Stop buttons — updates
  in place via ActivityKit.
- **Time Sensitive** notification: "Four days of disk left" + badge.
- **Background/passive** notification: "Offload finished · 4 clips moved to
  nas-vault".
- **Actionable** notification: includes a "Decide" button that deep-links to
  Classify (`#f-classify`) — real API is `UNNotificationAction`.

**Three real engineering constraints, called out explicitly in the design
notes — plan for these, they are not optional:**
1. The Live Activity/transport buttons/Time-Sensitive level/Decide action are
   ActivityKit + App Intents + `UNNotificationAction` respectively — all
   real, buildable APIs.
2. **The phone cannot poll a sleeping PC.** State must arrive by **push**
   from the agent; the Live Activity is updated via a push token, not by the
   phone asking.
3. **Wake over LAN needs an always-on peer on the tailnet** to send the
   magic packet — the phone will not be on the same L2 as the studio PC.
4. **App Review will want the streaming screen to be a launcher into
   Moonlight**, not a bundled decoder — deep-link out to the Moonlight app,
   don't embed a stream player.

### 8. Appearance (`f-appearance`) — settings
- Large title "Appearance".
- Accent swatch picker: 6 swatches (violet/indigo/cyan/teal/amber/magenta
  from Tokens § Colour) — live-updates sliders, hex readout, and the
  notification preview below.
- Density slider, Corner radius slider, Motion slider (drag-anywhere-on-track
  to set) — Motion is the real `--motion-scale` accessibility control, see
  Tokens § Motion.
- Haptics-on-transport toggle.
- Live notification preview card ("Recording started") styled with whatever
  accent is currently selected — lets the user see the Live Activity look
  before it happens for real.

## Behaviour contracts

- No fabricated recording state, bitrate, disk-remaining, clip counts, or
  peer/ping numbers — every stat above is a live binding in the mockup
  (`{{ }}` placeholders); wire to real data or show an honest empty/loading
  state, never a hardcoded demo value.
- OBS/Nebula footage is sacred — no delete/cleanup affordance in this app
  without the same copy → hash-verify → optional-delete rule as desktop.
- Streaming screen launches Moonlight externally; do not attempt to embed a
  decoder (see Notifications § constraint 4).
- Wake-on-LAN and Live Activity updates depend on backend/push
  infrastructure that doesn't exist yet in this repo — scaffold the UI
  states (ready/busy/live, awake/asleep) but don't fake working
  connectivity.

## Definition of done (per screen)

- [ ] Matches this spec's spacing / type / colour tokens (§ Tokens), not
      Nocturne's
- [ ] Wired to real data or shows an honest empty/loading state (never
      mocked numbers)
- [ ] Motion respects `--motion-scale`; no purely-decorative loops
- [ ] Inbox task outbox note written (`.cursor/handoff/outbox/`)
