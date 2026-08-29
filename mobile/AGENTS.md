# Nebula mobile — Expo SDK 54

This app is pinned to **Expo SDK 54** because Expo Go on the target device is
54. Do **not** upgrade to 55/57, and do not follow newer Expo docs.

Read the exact versioned docs at https://docs.expo.dev/versions/v54.0.0/
before writing any code.

## Design authority

1. Phone-frame UI in `design/nebula-mobile/Nebula Mobile.dc.html`
   (sections `#f-now`, `#f-offline`, `#f-clips`, `#f-remote`, `#f-games`,
   `#f-classify`, `#f-appearance`)
2. `design/nebula-mobile/BUILD-SPEC.md`
3. `design/nebula-mobile/FRAMES.md`

`_ds/nocturne-…/` styles the **mockup document's own chrome**, not the phone
UI — never apply those tokens inside a screen. `ios-frame.jsx` is a preview
harness (device bezel); do not port it.

## Hard rules

- **One `PillTabBar`**, mounted once in `app/(tabs)/_layout.tsx`. Four
  destinations: Now · Clips · Remote · Games. Never per-screen.
- **Classify is pushed from Games** and lives at
  `app/(tabs)/games/classify/[id].tsx` so the tab bar stays mounted with Games
  active. Do not move it to a root-level route.
- **Disconnected is a state of Now**, not a fifth tab.
- **Appearance has no entry point in the design.** Don't invent a gear icon.
- **No fabricated telemetry.** Recording clocks, bitrates, disk countdowns,
  clip counts, peers and pings are all live bindings in the mockup. Wire them
  to real state or show `—` / an honest empty line. The three classify
  fixtures (Sifu / Blender / Yakuza 0) are the *only* seeded data, and they
  are QA cases named in BUILD-SPEC.
- **OBS footage is sacred.** No delete or cleanup affordance without
  copy → SHA-256 verify → optional delete.
- Moonlight is **launched**, never embedded — App Review expects a launcher.

## Visual system

- One easing everywhere: `cubic-bezier(.32,.72,0,1)`.
- Press feedback is scale (`.97` pills, `.94` circular), never a colour flash.
- Elevation is the lightness ladder (`#100D1C → #181428`) plus
  `inset 0 1px 0 rgba(245,243,255,.08)`. The tab bar's
  `0 12px 34px rgba(0,0,0,.5)` is the **only** drop shadow in the system.
- Motion carries state only, and every ambient animation must stop when
  `motionScale` is 0 (the reduce-motion hook, wired through `useStudio()`).

## Running it

```bash
npm install
npx expo start        # or: npx expo start --web  for visual QA
```

`npx tsc --noEmit` must stay clean.
