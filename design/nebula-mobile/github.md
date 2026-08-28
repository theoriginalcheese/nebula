repo: theoriginalcheese/nebula
branch: main
path: spike/web

## Mobile companion (Expo)
repo: theoriginalcheese/nebula
branch: main
path: mobile

Expo SDK 54 React Native app — mirrors `nebula-framework/app/` on Alien-PC.
Design authority stays in this folder (`design/nebula-mobile/`).

## Last sync
date: 2026-08-28T13:20:00Z

### Mobile app pushed to GitHub
- `mobile/` — full Expo Router app (Now / Clips / Remote / Games + Classify)
- `design/nebula-mobile/` — BUILD-SPEC, FRAMES, dc.html, screenshots (incl. states.png)
- Synced from `Downloads/nebula-framework` for Claude Design GitHub import

## Last sync (desktop)
date: 2026-08-26T19:53:42Z

### Updated in this project
- **Nebula Icon** gains turn 14, a shipped receipt: all five specced changes are in `obsauto/icon_art.py` on main, close to verbatim — geometry constants, `_draw_tilted_arc`, the rewritten `render_state_icon`, `render_tile_icon`, native-size `save_ico`.
- Recorded three additions made on top of the spec: a counter-tilted thin violet inner ring (`INNER_RX .406`, gated off below 32px), a `detail_size` parameter so the tile judges the gate on displayed size rather than drawn size, and a full hover animation (`render_animation_frame` comet orbit + `save_webp`).
- Recorded the bug the rewrite exposed: Pillow's ICO writer drops sizes larger than its source image, so the old smallest-first `save_ico` had made `nebula_icon.ico` a **single 16px entry, 702 bytes**, for the life of the file. Fixed by `sorted(sizes, reverse=True)` plus native-size renders.
- Noted where it wired in: `obsauto/tray_app.py` (one `set_tray_state` for both hosts, arc thread only while recording, identity check on teardown) and the new `spike/taskbar_icon.py` (hover-only orbit, button resolved through UI Automation on Win11's XAML content bridge).
- Flagged a new upstream brief, not started: `design/ui-v3/TOAST-ICON-DESIGN-PROMPT.md` — seven toast icon roles, Phosphor Light, ember reserved for start/stop/error, no eye for `watching`, refs in `design/ui-v3/toast-icon-refs/`.

### Also this turn — new screen
- Added **Nebula Mobile** (`Nebula Mobile.dc.html`), an iOS companion app in six screens: Now·recording, Now·disconnected, Clips, Remote, Games, Appearance. Built from `spike/web/index.html` (pane structure), `spike/web/tokens.css` (every colour, radius, easing), `obsauto/icon_art.py` (the mark and its three states), `obsauto/app_icons.py` (monogram tiles hashed to an accent) and `obsauto/moonlight.py` + `tailscale.py` (the Remote screen).
- Scope call: the phone keeps four jobs — is it recording, what did I catch, put the PC on this screen, stop bothering me about that launcher. Macropad, Settings detail and the customise grid stay desktop-only.
- Carried over verbatim from the desktop: the 3.8s lit arc, ember reserved for stop/error/disconnected, the shell+core double-bezel with concentric radii, the six accent presets, and the `cubic-bezier(.32,.72,0,1)` easing.
- Reworked **Nebula Mobile**'s visual layer against `spike/web/toast.css` + `toast.js` rather than the desktop panes: the dust constellation (tinted specks, six named motions, transform/opacity only), the 28px chip with its `0 0 14px` tinted glow, the drain track masked to transparent at both ends, and the two-layer pill button (`inset 0 0 0 1px hairline/.09` shell + `accent/.32` core, `.42` hover, `scale(.97)` press).
- Dust is state-tinted and state-motioned: burst on the recording chip, sink on the disconnected mark, orbit on the Moonlight orb (quickens on handshake, turns gold when live), scatter behind the accent picker where it recolours with the pick.
- Replay-buffer drain added to the Save-last-60s pill, filling across the rolling 60s window; icon chips replace the bare timestamps in both Activity lists.
- Type substitution noted in-file: Segoe UI Variable is a Windows face, so the mobile design is Plus Jakarta Sans with JetBrains Mono on all numeric readouts.

### Not rebuilt this sync
- **Nebula Code Audit** and **Nebula Customise Mode** have upstream drift: `spike/web/app.js`, `app.css`, `index.html`, `tokens.css` and `toast.*` all changed again across the 115 commits since the recorded base. A re-audit is its own pass, not a sync side effect — ask for it explicitly.

## Screen map
| Project screen | Built from |
| --- | --- |
| Nebula Code Audit.dc.html | spike/web/app.js, spike/web/app.css, spike/web/index.html, spike/web/tokens.css |
| Nebula Customise Mode.dc.html | spike/web/app.js (6.8 block), spike/web/tokens.css (customise tokens) |
| Nebula UI Mockups v3.dc.html | design/ui-v3/ (source of the v3 frames this project produced) |
| Nebula Icon.dc.html | obsauto/icon_art.py, obsauto/tray_app.py, spike/taskbar_icon.py, spike/web/app.css (.mark), design/ui-v3/TOAST-ICON-DESIGN-PROMPT.md |
| Nebula Mobile.dc.html | spike/web/index.html, spike/web/tokens.css, obsauto/icon_art.py, obsauto/app_icons.py, obsauto/moonlight.py, obsauto/tailscale.py |

## Sync history
### 2026-08-08T01:14:09Z
- Re-read `obsauto/icon_art.py` and wrote build notes in **Nebula Icon** (turn 13): five drop-in changes covering new geometry constants, a `_draw_tilted_arc` helper, a rewritten `render_state_icon` (violet sparkle in all three states, lit arc for recording, chroma-drained slash for disconnected), a tiled `render_tile_icon` for the taskbar/.ico, and a native-size `save_ico`.
- Noted that `EMBER` should leave `icon_art.py` — it is the web chrome's disconnected colour, and using it for recording gave one token two opposite meanings. Upstream agreed: there is no red anywhere in the shipped mark.
- Rebuilt the app-icon explorations from the real mark: four-point sparkle (`0.34s` outer, `0.34` notch ratio, `#8B7CF6`) plus one gold `#F5A623` orbit ring at `rx 0.46s, ry 0.6·rx`, tilted 22°.
- Rebuilt **Nebula Code Audit** as a re-audit: all 15 findings implemented upstream, so the document became a receipt rather than a fix list.
- Blockers F1–F4 confirmed fixed: `dashGridMetrics()` replaces `measureBlockRect()`, `dropIndexFor()` is row-band-then-column, `.is-drag-src` makes the source block the placeholder, `setKbdHeld()` + `#dash-live` wire the keyboard path.
- The appearance layer (F11) landed: `--density`, `--radius-scale`, `--motion-scale` and six accent presets in `tokens.css`, written by `applyAppearance()`.

### 2026-08-04T10:29:07Z — base 863efe18
- Read the live v4 front end (`spike/web`) and audited the customise mode against it.
- Added **Nebula Code Audit** — 15 findings with the exact code, grouped blockers / quality / polish, plus a tickable fix order.
- Flagged the missing appearance layer (accent / density / radius / motion) as unbuilt despite the tokens existing.
