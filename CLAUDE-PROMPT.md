# Handoff → Claude Code

**Disposable.** This is a baton-pass, not documentation. Delete it once the branch lands —
along with the pointer line at the top of `CLAUDE.md`. Anything worth keeping is already in
`CLAUDE.md` proper.

Written by Cursor (cloud agent, Linux) after picking up "refine the settings" from
`CURSOR-PROMPT.md`. You're back on Windows with a real OBS and the vault — which is exactly
what the remaining work needs, because the things I couldn't verify are all Windows things.

---

## Start here

Everything below assumes you're on the branch. Check first, because if you're reading this
from `main` you're reading a file that shouldn't be there:

```
cd C:\Users\antho\nebula
git branch --show-current
```

If that isn't `cursor/editable-settings-view-dd92`:

```
git fetch origin cursor/editable-settings-view-dd92
git checkout cursor/editable-settings-view-dd92
```

Local edits in the way? `git stash` first — but **check what they are before stashing**; if
Anthony has been running Nebula from this checkout, uncommitted work here may be his, not
leftovers. `config.json`, `games.json`, `steam_appid_cache.json` and `logs/` are gitignored
and carry across untouched, so his real settings and game list are safe either way.

Then, if you haven't run this checkout before:

```
pip install -r requirements.txt
python tests/test_settings.py
```

**The tests are safe to run on the real machine.** Every test that opens a window stubs both
`save_config` and `hotkey.register`, so none of them can write `config.json` or disturb
Anthony's real key binding (`test_gamesync` and `test_offload` open no window and touch
neither). `test_settings.py` reads his live config as a starting point and mutates only its
own in-memory copy. I had to add the `save_config` stub to `test_async_connect` to make that
true — it was the one window test relying on never happening to trigger a write.

### Where everything is

| | |
|---|---|
| **This brief** | `CLAUDE-PROMPT.md` — the branch state and what still needs verifying |
| **Durable design rules** | `CLAUDE.md` → "Settings view (editable, applies live)" |
| **What the user sees** | `README.md` → Configuration |
| **The change itself** | `obsauto/settings_spec.py`, `_build_settings`/`_apply_settings` in `obsauto/gui.py` |
| **Tests** | `tests/test_settings.py`, `tests/test_settings_typing.py` |
| **PR** | [#1](https://github.com/theoriginalcheese/nebula/pull/1) (draft) — the description is the long-form rationale |
| **Runtime data** | `config.json` and `logs/` next to the repo root (gitignored, per-machine) |

Read `CLAUDE.md`'s Settings section before changing anything in the form. Don't re-derive the
rules from the code — several encode a decision that isn't visible in it.

---

## State of play

Branch `cursor/editable-settings-view-dd92`, PR
[#1](https://github.com/theoriginalcheese/nebula/pull/1) (draft). Commits:
`git log --oneline main..HEAD`.

**Settings is now a real editor.** It was the last view that only reported — it listed eight
config keys and told you to edit `config.json` and restart. It now edits all 18, validates
before writing, and applies the result to the running app. `sync_folder` is the only key that
still needs a restart, and the page says so and says why.

| File | What happened |
|---|---|
| `obsauto/settings_spec.py` | **new** — declares the fields; pure parse/render/validate, no Tk |
| `obsauto/gui.py` | `_build_settings` rewritten as a form; `_apply_settings()` is the live-apply seam |
| `obsauto/hotkey.py` | `register()` returns the hook; `unregister()` takes it down |
| `obsauto/audio_detect.py` | `set_processes()` |
| `obsauto/gamesync.py` | `configure()` — re-reads target, drops the stale blob sha with it |
| `obsauto/offload.py` | `refresh()` — wakes the worker |
| `tests/test_settings.py` | **new** — 76 checks |
| `tests/test_settings_typing.py` | **new** — measures per-keystroke repaint cost (see below) |

## What I could and couldn't verify

The cloud box has a VNC X session, so the suite genuinely runs there — this isn't
"it compiles". Green on both customtkinter **5.2.2 and 6.0.0** (I checked `_textbox` and
`_entry` still exist under 6.x, since `_prepare_log_tags` and the entry bindings reach for
them; `requirements.txt` is unpinned so either can turn up):

```
test_settings 76 · test_views 41 · test_async_connect 11 · test_frame_pacing
test_gamesync 14 · test_offload 15 · stress_test 17/17
```

`test_list_views` fails there only because Linux has no `D:` drive — it failed identically
before my branch. **It should pass for you.** If it doesn't, that's mine.

What an X session cannot tell you: anything about DWM. That's the whole verification gap
below.

---

## Do these first, in this order

### 1. Measure what a keystroke costs — highest risk in the whole change

```
python tests/test_settings_typing.py
```

The design rests on a claim I could not test: a text field costs one window-level composite
per keystroke, and that's acceptable because it's user-initiated. On Linux it reports
**0.0ms**, which tells you nothing — there's no DWM. Your number is the real one.

- **Under ~40ms** → fine, ship it.
- **Near the ~100ms the animation post-mortem measured** → typing is a ~9fps experience and
  the in-view form is the wrong shape.

If it's bad, the fallback is a separate **Toplevel** rather than an in-view page: a smaller
composite surface, and known cheap here (the notification popup animates at 20fps without
trouble). `settings_spec.py`, `_build_settings_form`, `_settings_row`, `_settings_reload`,
`_save_settings` and `_apply_settings` all move across unchanged — only the container and the
nav-item action change. Use the `_dialog_bg()` pattern.

**Don't** try to micro-optimise the canvas instead. The post-mortem is unambiguous: the cost
is flat and scales with window size, not with what changed.

⚠️ The test deliberately does *not* use p50 frame time. Keystrokes are sparse relative to a
16ms heartbeat, so the median stays clean while every keystroke stalls — I proved this by
injecting an 80ms stall per character and watching p50 sit at 16.1ms. It measures the
keystroke directly and cross-checks against event-loop rate. Please don't simplify it back.

### 2. Can you actually type in it from the tray?

The main window is `overrideredirect(True)`, i.e. not a normally activatable window, so a
click may not hand Windows' keyboard focus over and your typing would land in whatever was
focused before. I added `_claim_focus()` on entry click and on opening the view, but I have no
way to confirm it works.

Run it the way you actually run it — `pythonw main.py`, let it minimise to tray, open from the
tray, go to Settings, click a field, type. If characters don't appear:

1. Add `widget.focus_set()` after the `focus_force()`.
2. If that's not enough, the window may need real activation (`SetForegroundWindow` via
   ctypes) — note `show()` already does a topmost flick for a related reason.
3. Worst case, the Toplevel fallback from §1 solves this too, since that *is* a normal window.

### 3. The hotkey rebind — the one that can break your daily typing

This is the check I'd least like skipped, because `suppress=True` hooks are system-wide and
`config.json` already documents that binding by name suppressed apostrophes.

With monitoring running: Settings → Hotkey → set **Toggle key** to `f12`, clear **Scan code**,
Save. Then confirm, in this order:

- F12 toggles monitoring.
- Backtick no longer toggles it — the old hook is genuinely gone, not just shadowed.
- **Typing a backtick and an apostrophe in another app still works.** If the old
  scancode-41 hook leaked, this is where you'd find out.

Then set it back to `` ` `` with scan code `41` and re-check apostrophes.

### 4. OBS reconnect

With OBS up and monitoring on, change the port to a wrong one and save: expect a
"reconnecting" log line, the sidebar to go Disconnected, and the retry loop to run. Put it
back and it should reconnect on its own.

**Known behaviour worth a decision:** repointing OBS calls `_stop()`, which ends any recording
in progress. I judged that the honest outcome of aiming Nebula at a different OBS, but it's
Anthony's call — the alternative is deferring the reconnect until recording stops. Ask him.

### 5. High-DPI pass

You're on a scaled display and I'm not. Check at 150% that the form, the `copy`/`move`
segmented control and the footer don't overflow. It's the usual fixed 1180×760 design times
`self.scale`.

⚠️ If you exercise NAS offload, **don't test `move` mode on real footage.** Use a throwaway
clip. The copy-verify-then-delete invariant is untouched by this branch, but there's no reason
to point it at anything irreplaceable to find that out.

---

## Things I left alone on purpose

Don't read these as oversights, and don't "fix" them without deciding to:

- **`CLAUDE.md`'s "Rearrangeable dashboard" section is stale** — it describes `dashboard_layout`
  / `_saved_layout()` and reordering as pure translation, but the code uses `dashboard_grid` /
  `_saved_grid()` and *rebuilds* the blocks. That predates my branch. I left it because
  Anthony's rule is that CLAUDE.md is additive-only and it's outside this change — but it is
  wrong and worth a separate commit.
- **Macropad is still empty.** Deliberate, per the existing design note.
- **`dashboard_grid` isn't in Settings.** It's owned by Customise mode on the dashboard.
- **No live validation as you type.** This is the repaint rule, not an unfinished feature.
- **`docs/` screenshots not regenerated.** I can only render with fallback fonts, not Segoe UI.
  If you want a Settings shot for the README, take it on Windows.

## Open question for Anthony

Only one from me: should changing the OBS host/port/password interrupt an in-progress
recording (current behaviour), or wait for it to finish?

## Vault

I couldn't reach it — it's laptop-only and I was in a cloud VM, so **nothing from this work is
in your memory yet.** Worth a note under your own protocol; the decisions with real rationale
behind them are:

- Forms on this window get one composite per keystroke, so no live validation — and p50 frame
  time is blind to sparse events, which is why `test_settings_typing.py` measures differently.
- Settings reloads from config on every visit, so unsaved typing is dropped on navigating
  away. Chosen so the page can never show a value that isn't actually in effect.
- A missing path is a warning, never an error — an unmounted NAS has to be configurable ahead
  of time, or the documented setup order breaks.
- `GameSync.configure()` drops the cached blob sha, because reusing a sha from the old file is
  precisely the unknown-remote write that `push()` refuses to make.
- Repointing OBS mid-connect used to leave monitoring off permanently (`autostart()` no-ops
  while `_connecting`, and the in-flight attempt then resolves against `_abort_connect` and
  neither connects nor retries). `_restart_monitoring()` waits for the flight to land.
