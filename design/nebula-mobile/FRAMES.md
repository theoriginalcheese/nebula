# FRAMES — nebula-mobile

Frame index transcribed from `Nebula Mobile.dc.html` (8 `<x-import>` device
frames inside `#1a`, each `IOSDevice` 390×844 dark). Full behaviour detail is
in `BUILD-SPEC.md` — this is the navigation-shaped index.

| ID | Name | Tab bar shown | Active tab | Purpose |
|----|------|----|----|---------|
| `f-now` | Now | yes | Now | Home / default. Recording status, transport, activity feed. |
| `f-offline` | Disconnected | yes | Now | State swap of Now when Tailscale link to studio PC drops. |
| `f-clips` | Clips | yes | Clips | Search + day-grouped, per-game-filterable clip list. |
| `f-remote` | Remote | yes | Remote | Moonlight launcher (3-state orb), Tailscale peers, NAS offload, per-game Wake toggles. |
| `f-games` | Games | yes | Games | Recently-detected executables; entry point into Classify. |
| `f-classify` | Classify | yes | Games (not itself) | Reached from Games — signal-based game/not-game verdict UI. |
| `f-notify` | Notifications | n/a | n/a | **Not an in-app screen** — iOS Lock Screen mockup (Live Activity + notification types). |
| `f-appearance` | Appearance | yes | *(none highlighted)* | Settings: accent, density, radius, motion, haptics, notification preview. |

## Navigation notes

- **Primary nav = floating pill tab bar**, 4 destinations only: **Now,
  Clips, Remote, Games**. Present on every real in-app screen (all except
  Notifications, which isn't a screen).
- **Disconnected is not a 5th destination** — it's what Now looks like when
  offline. Don't route to it directly; derive it from connection state.
- **Classify has no tab of its own** — pushed from Games, tab bar still
  shows Games as active.
- **Appearance's entry point is undefined in the mockup.** No tab highlights
  while on it, and no settings icon/gear is shown anywhere else in the 8
  frames. Don't invent a nav affordance for this — ask, or scaffold it as
  unreachable-but-present until product decides (e.g. behind a temporary dev
  menu).
- **Notifications is reference-only.** It documents what the Lock Screen /
  Live Activity / notification types must look like; there is nothing to
  build as a "screen" — build the ActivityKit/App Intents/notification
  content instead (see BUILD-SPEC § Screens → 7).

## Frame → real screen mapping for Expo/RN

| Frame | Route | File (as built) |
|---|---|---|
| `f-now` + `f-offline` | `/` (tab: Now) — one screen, two states driven by connection status | `app/(tabs)/index.tsx` |
| `f-clips` | `/clips` (tab: Clips) | `app/(tabs)/clips.tsx` |
| `f-remote` | `/remote` (tab: Remote) | `app/(tabs)/remote.tsx` |
| `f-games` | `/games` (tab: Games) | `app/(tabs)/games/index.tsx` |
| `f-classify` | `/games/classify/[id]` (pushed, not a tab) | `app/(tabs)/games/classify/[id].tsx` |
| `f-notify` | not a route — ActivityKit + notification-content extension work | — |
| `f-appearance` | `/appearance` (modal; **no nav trigger** — see above) | `app/appearance.tsx` |

### Why Classify lives under `(tabs)/games/`

The Games tab owns a nested `Stack` (`app/(tabs)/games/_layout.tsx`). Pushing
Classify from a root-level route would unmount the tab bar entirely, which
contradicts "tab bar shown: yes, active tab: Games". Keeping the push *inside*
the tab group means the single `PillTabBar` — mounted once in
`app/(tabs)/_layout.tsx` — stays put with Games still highlighted.

Appearance is deliberately **not** in the tab group: the frame shows the bar
with no tab highlighted, which a four-destination bar cannot express, and
nothing links to it anyway. It renders without the bar until product decides.
