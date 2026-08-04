# Building v4

v4 is not a rewrite. It is a **renderer swap**: `obsauto/gui.py` is replaced by HTML/CSS
served into a WebView2 window. Everything else stays.

The spike is built and measured — read `spike/FINDINGS.md` first. The short version:
the webview costs **435 MB vs gui.py's 513 MB**, runs the whole animated backdrop at
**0.00 % CPU**, and drops to **288 MB when minimised**.

## What moves and what doesn't

| | lines | fate |
|---|---|---|
| `obsauto/gui.py` | 6,592 | **deleted**, replaced by ~2–3k of HTML/CSS/JS |
| `obsauto/theme_art.py` | 465 | **deleted** — CSS does the backdrop natively |
| `obsauto/icon_art.py` | 134 | **kept**. Corrected after step 1: the tray icon is a Win32 shell icon, not a CSS surface, so `generate_state_icons()` is still the only thing that can draw it. |
| `obsauto/design_v3.py` | 581 | **kept**, becomes the token source for CSS |
| everything else in `obsauto/` | 4,678 | **untouched** |
| logic tests (`forecast`, `palette`, `profiles`, `replay`, `thumbs`, `gamesync`, `offload`, `obs_meta`) | — | **untouched** |
| GUI tests (`views`, `chassis`, `customise`, `background`, `frame_pacing`, `fidelity`, `list_views`, `settings`, `toast`, `games_pane`) | — | rewritten against the DOM |

`test_frame_pacing.py` and `test_background.py` get **deleted**, not ported. They exist
to police a limitation v4 does not have.

## Ground rules

1. **`design_v3.py` stays the only place a v3 number lives.** `python spike/gen_tokens.py`
   regenerates `web/tokens.css`. Never hand-edit the CSS; never type a hex in a stylesheet.
2. **Only `transform` and `opacity` may be animated.** Both are compositor-only. Animating
   width, top, `filter` or `box-shadow` puts layout and paint back on the main thread and
   you have rebuilt the Tk problem in a browser.
3. **No fabricated numbers.** Unchanged from v3. Build the source or omit the element.
4. **Look at every visual change.** `tools/shoot.py` after, `tools/frames.py` for the
   design. If you have not compared the two PNGs you are not finished.

## Build order

Each step ends with a screenshot compared against its frame.

| # | Step | Frame | Why here |
|---|---|---|---|
| 0 | **Chassis** — tray/core, titlebar, rail, backdrop, cards | 2a, 6a–6b | Everything sits on it. Already done in `spike/`. |
| 1 | **Tray + single instance + hotkeys** | 2j | The app must be able to *live* in the tray before panes matter. Reuses `tray_app.py`, `hotkey.py`, the `main.py` mutex, driving a hidden window instead of a withdrawn one. |
| 2 | **Monitor + OBS wiring** | 2f–2h | The hero's four states are the whole app. `obs_client` and `monitor` are unchanged; only the marshalling back to the UI changes — `_ui()` becomes a JS call. |
| 3 | **Dashboard** — hero, stat tiles, activity log | 2a, 6c–6f | The log is the one thing that was expensive in Tk (a textbox write = one composite, coalesced to 80 ms batches). In a DOM it is an append; drop the coalescing. |
| 4 | **Clips** | 2b, 7f | Mostly built in the spike. Add the by-game column, search, sort, row actions, thumbnails. |
| 5 | **Settings** | 2c | `settings_spec.py` already declares every field with bounds and restart reasons. Walk it to generate the form — same as today. |
| 6 | **Games** | 2d | `classifier.py` unchanged, including `merge_classifications()`. |
| 7 | **Session ribbon, forecast, palette, profiles, replay** | 7a–7e | All pure-Python already. UI only. |
| 8 | **Toast + mini overlay** | 2i, 2k | Second and third pywebview windows. The overlay is 296×54, always-on-top, frameless. ⚠️ **Never call `evaluate_js` from the GUI thread** — it blocks the caller on a semaphore released only by a continuation scheduled on that same thread. Use `_off_gui()`. This froze the app on the first toast and left the overlay blank; see `spike/FINDINGS.md`. |
| 9 | **Customise mode** | 6h | 12-column grid. In CSS this is `grid-template-columns` and a drag handler, not canvas `move()` on tagged items. |
| 10 | **The motion the spec always wanted** | 6a | Aurora drift, star parallax, pointer spotlight, pointer lean, pulsing badges. Already live in the spike — this step is just deleting `BACKGROUND_MOTION_UNUSED`'s "unused". |
| 11 | **Packaging** | — | PyInstaller onefile, as today. Verify WebView2 runtime is present (it ships with Windows 11) and that `APP_DIR` still resolves next to the exe. **Done:** `pyinstaller nebula-v4.spec` → `dist/Nebula-v4.exe`. User data lands next to the exe (`dist/config.json`, `dist/logs/`); the repo-root copies are untouched. Verified by *running* it — a missing `web/` bundle is a styled-vs-unstyled window, not a crash, so the build succeeding proves nothing. Running it is also what surfaced the dead renderer suspend (see `spike/FINDINGS.md`), worth **115 MB** hidden. |
| 12 | **Macropad** | 2e | Still deliberately empty. There is still no HID layer. |

Steps 1 and 2 come before the panes for the same reason v3's step 0 did: a pane built
against a chassis that cannot yet live in the tray inherits its defects.

## The daily loop

```bash
python spike/gen_tokens.py                    # if design_v3.py changed
python spike/app.py                           # run it
python tools/shoot.py --out shots/now.png     # see it
python tools/frames.py --only 2b              # see what it should be
```

Then `Read` both PNGs side by side. That loop is the whole reason this is worth doing —
it is what `gui.py` never had.

For the whole app at once:

```bash
python tools/smoke.py
```

Drives all five panes plus the palette and customise mode, and photographs each into
`shots/smoke/`. It **photographs, it does not judge** — a green run means seven surfaces
rendered and none came back blank, which is a far weaker claim than "they are correct".
Open the PNGs.

⚠️ The perf HUD is `?hud=1` **only**. It used to gate just the frame counter while the
panel itself always rendered, so it shipped visible in the first packaged exe, sitting on
top of the Settings "Test again" button, the last Clips row's actions and the Games
promote hint. Developer instrumentation is not chrome.

Before trusting a capture: `python tools/shoot.py --list`. Two windows titled Nebula
means a stale instance is running and you are looking at the wrong process.

## Measuring

```bash
python tools/bench.py --launch spike --seconds 20 --minimised
```

Compare **private (USS)**, never summed RSS. Re-run it after step 2 and again after step 8
— those are where the process count grows.

## When to reconsider Tauri

**Settled at step 11: don't.** The open question was whether minimised USS stayed above
~300 MB. It is **69 MB** hidden, once the renderer suspend was fixed. A Rust shell would
replace the ~40 MB Python host and leave the WebView2 processes — the bulk — untouched,
so it cannot win back much from here.

The only remaining trigger is if the PyInstaller onefile becomes unacceptably slow to
start. The front end transfers unchanged either way.

## Do not

- Re-link `design/ui-v3/_ds/nocturne-*/styles.css`. Still a decoy.
- Re-fetch the mockup through the DesignSync MCP — it truncates at 256 KiB and 7c–7g
  vanish silently. Use `design/ui-v3/frames/*.png`.
- Weaken `Offloader`'s copy → verify → delete, or `GameSync.push()`'s refusal to PUT
  against an unknown remote. Neither is a UI concern and neither is negotiable.
