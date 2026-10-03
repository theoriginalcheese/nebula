The current Nebula already looks right. Do not start again.

Read `spike/web/index.html`, `spike/web/app.css`, and `spike/web/tokens.css`. The Dashboard in there is the thing to improve. Settings, the toast, the rail, and the other panes stay as they are. If a frame no longer looks like this app, it is wrong.

You are deciding, because the direction is not chosen yet. Look at the home page and say, in a few sentences, what actually makes it feel ordinary. Then draw three dashboards that fix that. Mark one Recommended. Do not write an essay, and do not edit the code.

## What the home page is

Desktop, dark, 1280 × 808. Same window on every artboard: titlebar, rail (Dashboard, Clips, Games, Remote streaming, Macropad, Settings, Search), storage forecast at the foot of the rail.

Under that, today:

- Pane header: eyebrow “Live session”, title “Dashboard”, ghost pills Open folder and Rescan Steam.
- Hero, two columns. Left: state badge, title, source line, hint, then Elapsed / File size / Bitrate, then the transport buttons. Right: a 16:9 scene preview.
- A row of stat tiles.
- An activity log.

States to respect: disconnected, watching, recording, paused. Recording is violet, not red. Ember `#FF5C7A` is only a real fault. Accent `#8B7CF6`. Ground stays the nebula, aurora showing through glass cards. Type is Segoe UI Variable. Text `#F5F3FF`, secondary `#9A93C4`. Hairlines are faint white, never a solid grey stroke.

No fake numbers. Elapsed, size, bitrate, disk, and clip counts are em dashes or omitted. A game name may appear only as a label. Do not launch Nebula or OBS.

## How to make it better

The layout is allowed to change. The material is not.

Judge the current stack before you draw. Likely problems, discard the ones that are not true after you look:

- The pane title repeats the rail. “Dashboard” is not the news. The state is.
- The hero, the tiles, and the log all weigh the same, so nothing is the screen.
- The badge, the title, the source, and the hint say one fact four times.
- The preview is a large empty gradient whenever OBS has no picture.

Fix it by giving the screen one job: what is happening right now, and the one or two actions that follow. Everything else gets quieter or moves down.

Keep the scene preview, the transport buttons, the readouts, the tiles, and the log. They can shrink, merge, or drop a repeated label. They cannot become a chart, an illustration, or a new product.

## Draw three, same chrome

1. Recommended. Your actual pick. One home, in the watching state, where the improvement is obvious.
2. A second composition, still this app, if the first one is wrong.
3. The same recommended layout in recording, so the tint and the live badge still work.
4. The same recommended layout disconnected, so the empty preview stays honest.

Put Recommended on the first artboard. One sentence under each of the others saying what it changes.

## Do not

- Do not restyle Settings, the toast, Clips, Games, Remote, or Macropad.
- Do not add a light theme, a new typeface, a fifth colour, or a marketing headline.
- Do not remove the rail or replace the activity log with a graphic.
- Do not invent bitrate, disk days, or a clip count.

When the four artboards exist, stop. Implementation comes after one of them is picked.
