Polish the Nebula that is already on `main`. Do not design a new app.

Open `spike/web/index.html`, `spike/web/app.css`, and `spike/web/tokens.css` and draw from those. The last pass looked dead because it replaced this window with a flatter one. If a frame could be mistaken for a different product, it is wrong.

This is a sleeker pass on two screens: the Dashboard (home) and Settings. Same chassis, same panes, same features. Desktop, dark, 1280 × 808. No phone frame. No fake numbers. Do not launch Nebula or OBS.

## Keep

- The tray and core: nebula ground, aurora and stars showing through the glass. Cards are a tinted shell around a darker core, not flat grey boxes. Hairlines are a faint white, never a solid grey stroke.
- Two hues only. Violet `#8B7CF6` is the accent. Ember `#FF5C7A` is for a real disconnect, a stop, or an error. Recording is violet, not red.
- Type stays Segoe UI Variable. Text `#F5F3FF`, secondary `#9A93C4`.
- The rail, in this order: Dashboard, Clips, Games, Remote streaming, Macropad, Settings, then Search. Storage forecast stays at the foot of the rail.
- Home layout, top to bottom: pane title, then the hero, then the stat tiles, then the activity log. Do not restack these.
- The hero stays two columns. Left: state badge, game title, elapsed / size / bitrate, the transport buttons. Right: the 16:9 scene preview. Disconnected, watching, recording, paused are the same card, tinted differently.
- Settings stays two columns. Left: the group list and the config-file card. Right: one group’s blurb, then its fields, then the footer. Groups stay in this order: OBS connection, Recording, Instant replay, Hotkey, Game list sync, NAS offload, Remote streaming, Storage, Appearance, Updates.

## Make it sleeker

Quieter, not emptier. Less box, more air, the same information.

Home:

- Let the aurora read through the hero. The card should feel like glass on the nebula, not a panel dropped on black.
- Tighten the hero. The title is the one loud line. The badge, the readouts, and the buttons sit closer, with one clear vertical rhythm. Don’t add a second headline or an illustration.
- Stat tiles stay a short row. Thinner, same content, no extra icons.
- Activity is a quiet log under a hairline, not another heavy card. Tag colours may stay. Don’t replace the log with a timeline graphic.

Settings:

- The group list is a light rail, not a stack of buttons. The active group is a soft violet wash.
- Fields are rows, not boxed forms. Label on the left, control on the right, a hairline between rows. Hints sit under the label in the secondary colour, one line.
- Inputs, toggles, and choices use the existing pill and field shapes. Don’t invent a new control style.
- More space between groups of rows than between rows. The blurb is one quiet line under the group name, then the fields.

## Draw only these

1. Dashboard, disconnected. Honest empty preview: no scene, OBS offline. No invented handshake time.
2. Dashboard, watching. This is the home page to get right.
3. Dashboard, recording. Accent tint, live badge, readouts as em dashes unless you are copying a label that already exists.
4. Settings, Recording. Include “When a game launches”.
5. Settings, Updates. Save this machine / Load latest, and the corner-prompt idea only as a setting row, not a new widget family.
6. Settings, Game list sync. The shared-list address and Upload, still in the same field-row style.

One artboard each. Same window chrome on all six, so Dashboard and Settings are obviously one app.

## Do not

- Do not restyle the toast, the rail destinations, Clips, Games, Remote, or Macropad.
- Do not add a light theme, a fifth colour, a marketing hero, illustrations, or a new typeface.
- Do not move the preview under the title, and do not turn Settings into a single scrolling page with no group list.
- Do not put real paths, tokens, or NAS addresses in the mockup.

End with a short note of what changed: spacing, glass, and type size only. If a frame and that note disagree, the frames above win only where they still match this prompt. When the six frames exist, stop.
