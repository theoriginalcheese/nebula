The last gallery only changed the outer corner. That is not the task. Build a new preference gallery where every toast has the identical exterior, and the cards differ by where the contents sit.

Attach every PNG in the refs folder. Do not attach the redundant folder.

## Locked on every card

Same shell, every option. If two cards can be told apart by the border alone, the card is wrong.

- Prompt: 404×116, radius exactly half the height. A full pill.
- Status: 384×60, radius exactly half the height. A full pill.
- Same glass, same nebula, same 3px inset, same hairline. Ground #0A0812 and #100D1C. Violet #8B7CF6. Ember #FF5C7A only on start, stop, and error. Text #F5F3FF, secondary #9A93C4. Segoe UI Variable.
- Same 28px chip, same two buttons reading Record and Not now, same two lines of copy, same seven specks, same 2px line fading at both ends.
- Do not change the corner radius, the stroke, the shadow, the outer size, or the colour between cards.

Show refs/08-prompt-with-controls.png once, labelled REFERENCE, not as a vote. Its arrangement is: chip at the left, “Record again?” over “Helldivers 2”, pills underneath toward the left, specks in a cluster on the right, line along the full bottom.

## What “layout” means

Layout is the position of the chip, the two text lines, the two buttons, the specks, and the line, relative to each other. Padding tweaks are not layouts. A rounder or squarer border is not a layout. Each card must be readable as a different composition from across the room.

Draw them at real size, scaled up, on a dark ground. One page. Sticky bar: ~/prefs-toast-layout, counts, Export picks. One pick per section. Each card: ID, title, one line on what it gives and what it costs, the finished toast, CURRENT or TRIAL, LIKE, NOPE, UNDECIDED, and a note.

## S1 Prompt compositions

All six are the 404×116 pill. Same border.

- L-STILL — TRIAL. The reference. Chip left. Title over the game. Buttons under the words, left side, clear of the curve. Specks clustered at the right. Line along the full bottom.
- L-LINE — CURRENT. One horizontal row in the upper half: chip, then “Record again? · Helldivers 2”. Buttons under that, left. Specks at the right.
- L-SPLIT — TRIAL. Left half is the chip plus the two text lines. Right half is Record over Not now, stacked, vertically centered. The two groups do not share a column.
- L-BAND — TRIAL. Top band: chip, title, game name, one row, vertically centered in the top half. Bottom band: Record and Not now stretched across the inner width, sitting on the line.
- L-CENTER — TRIAL. Everything in one centered column. Chip, then the two lines, then the two buttons side by side. Specks stay in the right bulb so they do not sit on the type.
- L-TRAIL — TRIAL. Two text lines on the left, no buttons under them. Record and Not now sit side by side at the vertical center of the right end, beside the text, not under it.

## S2 Status compositions

All three are the 384×60 pill. Same border. Copy is “Recording paused” and “Helldivers 2”, except T-META which is a stopped recording.

- T-ROW — CURRENT. One row: chip, Recording paused · Helldivers 2. Specks at the right. Line along the bottom.
- T-STACK — TRIAL. Chip at the left. “Recording paused” over “Helldivers 2”, both inside the 60px height. Show the cramp honestly.
- T-META — TRIAL. Chip and “Recording stopped” on the left. “10:47 · 1.7 GB” pinned to the right, same baseline. The game name is not shown.

## Already out. Do not draw these

- Any card whose only difference is corner radius, border width, shadow, or outer size.
- A 420×68 strip.
- Specks that only twinkle in place.
- A grey box, an 8px rounded rectangle, or a window frame.
- A second toast, a stack, a countdown, a bitrate, or a delete action.
- A dial menu, or any extra artboard.

## Export

Export picks copies this. Unvoted cards go under UNDECIDED with `(not voted)`. Empty headings say `- none`.

```
PREFS-TOAST-LAYOUT 2026-10-01
LIKE:
- <ID> — <title> · <note if any>
NOPE:
- <ID> — <title> · <note>
UNDECIDED:
- <ID> — <title> (not voted)
NOTES:

```
