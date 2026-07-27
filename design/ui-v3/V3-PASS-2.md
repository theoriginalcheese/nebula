# v3, pass 2 — the plan

The mockup grew from 151 KB to 347 KB. Sections **01–05 are unchanged** (verified
by text diff against the previously imported copy — only two nav links differ).
Everything new is:

- **§06 · Feature deep-dives** (`6a`–`6h`) — construction detail for what the last
  pass got wrong, ending in **6.7, a numbered twelve-item fix list**. Where a panel
  says *Wrong*, that is a real defect from the current implementation.
- **§07 · New features — full spec** (`7a`–`7g`) — six additions, each with its
  geometry, `config.json` keys, exact API calls and states, plus **7g, the build
  order and dependency chain**.

Authority is unchanged: `BUILD-SPEC.md` > frames / `.dc.html` > everything.
Nocturne stays a decoy — never link it. Tokens from `obsauto/design_v3.py` only.

## Getting the mockup

The DesignSync MCP caps `get_file` at **256 KiB**. The file is 347 KB, so an MCP
fetch returns it truncated mid-tag and **7c–7g vanish silently**. The complete
copy is committed here. If you must re-fetch, pull it through the design RPC
(`POST /design/anthropic.omelette.api.v1alpha.OmeletteService/GetFile` with
`{projectId, path}`, base64 in `.content`) rather than the MCP.

## Decisions Anthony made (do not re-litigate)

| Question | Decision |
|---|---|
| 2j — "you missed it" | The **tray menu**. Its contract passes all 26 checks and every attribute it reads is initialised, so this is almost certainly Windows 11 filing a new tray icon under the overflow chevron. It now logs once when the shell confirms registration. If it is still missing after that line appears, the cause is not in `tray_app.py`. |
| Customise mode (6.8) | **Rebuild it** on the 12-column grid, not cut it. |
| ffmpeg (7f) | **Install it**; build thumbnails and clip Length as an optional soft-dep that fails gracefully. |
| Mini overlay (2k) | Anthony asked for "nicer, more fleshed out with buttons"; the spec pins it at 296×54 with timer + game + collapse only. Resolution: keep the shell and its rules, add Pause/Resume, Stop & save and Mark clip. **A deliberate, documented deviation.** |

## Build order

7g is explicit that step 0 comes first: "Everything below sits on the chassis.
Fix it first or inherit its defects." The functional bugs went ahead of it
because they are behavioural, not visual, so nothing inherits from them.

| # | Step | State |
|---|---|---|
| 1 | Functional bugs: pause, reclassification, reachability, tray | **done** — `9da66b5` |
| 2 | Living background — 6.7 #1–4 | **done** — `ca4ad8b` |
| 3 | Two-layer cards + fading dividers — #5, #10 | **done** — `a415df9` |
| 4 | Titlebar / stat tiles / activity / scene preview — #6–9 | **done** — `dcaa88f` |
| 5 | Customise mode rebuild — #11, #12 | **done** — `ee277d9` |
| 6 | `sessions.jsonl` event log (7g step 1) | **done** — landed with step 4 |
| 7 | 7a Instant replay | **done** — `5a20994` |
| 8 | 7f Thumbnails + Length (ffmpeg) | **done** — `3c42068` |
| 9 | 7b Session ribbon | todo |
| 10 | 7c Storage forecast | todo |
| 11 | 7e Command palette | todo |
| 12 | 7d Per-game profiles | todo |
| 13 | Mini overlay buttons, exe rebuild, docs | todo |

Steps 9, 10 and 11 all read `sessions.jsonl`. Build step 6 before any of them or
you will rebuild them.

## What steps 1 and 2 actually found

Worth reading before you touch either area again — both were misdiagnosed once.

**Pause.** Not a pause bug. The hero buttons branched on `_is_recording` /
`_is_paused`, refreshed by a poll once a second, so pressing Stop and then Pause
inside that window sent `PauseRecord` to a recording that had already ended:

```
23:05:07 [Manual] Recording stopped.
23:05:08 [Manual] Recording paused.
23:05:24 [OBS] Failed to resume: ResumeRecord failed: unknown error
```

Every transport command now re-reads `GetRecordStatus` on a worker first
(`_transport`). `_poll_now()` cancels before rescheduling — two
self-perpetuating timers is what once drained the toast at double rate.

**"Can't change non games into games."** Also real, also not in the Games pane.
The classification merge was a plain union in three places — the local save, the
sync absorb and the GitHub push — and a union cannot express a *removal*.
Promoting an app added it to `games` and then read its old `non_games` entry
straight back off disk, so it sat in both buckets and kept appearing under
"Not games"; the next sync pull did it again. There is now one
`merge_classifications()` (a key lives in exactly one bucket, the newer view
wins, other machines' additions still survive) and `Classifier._heal()` repairs
existing damage on load — `starrail.exe` was double-filed in two of the three
real game lists on this machine.

**"Can't rescan for games."** Rescan works. There are no Steam games — they come
from HoYoPlay, Roblox and CurseForge, so `[Steam] Found 0 Steam game(s)` is
correct and useless. The button is now "Rescan Steam", beside a new "Add a game"
that picks from running windows. Promotion also got a visible button; it had
been right-click only, which from the outside is the same as not existing.

**The aurora measured zero.** 6.1 was right that it was "entirely absent".
`layer.paste(blob, pos, blob)` passes the blob's alpha as its own mask, squaring
it (19% → 3.6%), and each blob was blurred by the page-level 90–110px rather
than the 54px the CSS puts on the element. Neither would fail a "does it render"
check, which is why `tests/test_background.py` measures each layer against the
one below it instead.

**Stars over the chrome.** The rail and titlebar were not panels at all — text on
bare sky. Both now sit at `.72`. Panels are flattened onto a **second, starless
render** returned alongside the painted one, so the aurora reads through a card
(spec wants that) but the dust never does (reads as dirt on glass). That surface
also seeds `_composite`, which widgets sample for their corner blend.

## Hard rules (unchanged, outrank the mockup)

1. **Never animate the main `tk.Canvas` per-frame.** Any mutation ≈ one full
   window composite. `tests/test_frame_pacing.py` guards it; p50 is 16ms.
2. **No fabricated numbers.** Build the source or omit the element.
3. **Never `obs.connect()` on the Tk thread.**
4. `except X as e:` **unbinds `e`** — bind to a local before any deferred closure.
5. Offloader copy-verify-then-delete and GameSync's never-PUT-against-an-unknown-
   remote are not negotiable.
6. User data via `APP_DIR` (`obsauto/paths.py`), never `os.path.dirname(__file__)`.
7. Anything async must be tested under a real `mainloop()`.

## Tests

Everything under `tests/` should pass; there are 18 files and ~370 checks. New in
this pass: `test_transport.py`, `test_games_pane.py`, `test_background.py`.

```
for %t in (tests\test_*.py) do python %t
```
