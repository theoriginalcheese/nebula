Design Nebula UI v4. Read this repo first. You just pulled `main`. Do not invent a new product, and do not edit the code.

The app on `main` is already the Windows app. `spike/` is the window people use (WebView). `design/ui-v3/` is the previous look. This job is the next design of that same app, drawn so it can be built later. Call the file **Nebula UI v4**.

Desktop only. Dark. No phone frame. No fake numbers, bitrates, disk countdowns, or clip counts. If the app does not have the number, leave the spot blank or write an em dash. Do not launch Nebula, OBS, or a game.

## Locked. Draw these, do not redesign them

The toast is done. One capsule, one slot, bottom right, never a stack.

- Status: 384 × 60. Prompt: 456 × 60. Same height. One row. Record and Not now sit on that row, on the right. A tall prompt with buttons underneath is a nope. Do not bring it back.
- True capsule. Ends are semicircles. Two-layer glass. Ground `#100D1C`, accent `#8B7CF6`, ember `#FF5C7A` only for start, stop, error, and a real disconnect. Text `#F5F3FF`, secondary `#9A93C4`.
- A 2px violet line along the bottom, fading at both ends. No countdown number.
- Dust is seven specks. Leave their seats as they are in `spike/web/toast.js`. Do not attach any GIF from `design/claude-inspo/redundant/`.

The rest of the window has to belong to that toast. Same glass, same type (Segoe UI Variable), same two hues.

Also locked, as behaviour, not as a picture:

- Rail destinations, in this order: Dashboard, Clips, Games, Remote streaming, Macropad, Settings. Macropad stays an honest empty state. There is no HID device. Do not draw a connected keypad.
- Hero states: disconnected, watching, recording, paused. Recording is accent, not red. Ember means a real fault.
- First-run setup already exists: welcome, connect OBS, pick a clips folder, optional Steam scan, hotkey. Default clips folder is `Videos\Nebula`. No NAS step.
- A game can record a full clip, use the replay buffer, or both. Recording is the default. The default is a setting. Each game row can override it.
- An update is a small prompt in the bottom right, separate from the toast. It is not a second toast. Dismiss hides that version only.
- Nothing in the UI deletes a recording. No recycle button, no cleanup.

## Draw these frames

One artboard each, 1280 × 808, same window chrome. Label them.

1. Dashboard, disconnected. OBS is off. No invented handshake time.
2. Dashboard, watching. A real game name is allowed only as a label, not with a fake clock.
3. Dashboard, recording.
4. Dashboard, paused.
5. Clips, with rows. Length and size only where a finished file would have them. A file still being written has no duration. Show that honestly.
6. Clips, empty.
7. Games. Each row has the capture choice: Record, Buffer, or Both, plus Default when the row has no choice of its own.
8. Games, the one prompt for an unknown app: It's a game / Not a game.
9. Remote streaming. Peers and Moonlight only as labels. No invented ping.
10. Macropad, empty, saying there is no device.
11. Settings, the Recording group, including "When a game launches".
12. Settings, the update row, and the shared game list with an Upload button. Upload needs a token. Pulling the list does not.
13. First-run setup, the four steps, as one flow on four artboards.
14. The update prompt alone, on the dashboard, bottom right, not covering the toast. Two states: available, and failed (the reason stays visible).
15. The toast row, once, so the rest of the file can be checked against it: start, pause, stop, error, and the Record / Not now prompt. Copy the locked sizes. Do not explore alternatives.

## Spec

End the file with a build-spec table: colour, type, radii, spacing, and the size of every new control (capture choice, update prompt, setup). Write the rule in the table: if a frame and the table disagree, the table wins. Do not copy tokens out of `design/ui-v3/_ds/`. That stylesheet is not the app.

## Do not

- Do not redesign the toast, the dial menu, or the phone app.
- Do not add a fifth hue, a light theme, or a marketing page.
- Do not draw features the repo does not have. Read `spike/web/index.html` and `obsauto/settings_spec.py` before adding a control.
- Do not put Anthony's paths, NAS addresses, or tokens in the mockup.

When the file exists, stop. Implementation is a later job.
