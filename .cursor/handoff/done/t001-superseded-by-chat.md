# t001 - Clips pane: by-game, search, sort, actions, thumbs

Deepen the Clips pane to match frame 2b (design/ui-v3/frames/2b.png).

The pane already renders a flat list. 2b shows considerably more:

1. **By-game column** (left, ~254px): each game with its clip count, selectable,
   filtering the list. Counts come from a real scan of `recording_root`, grouped
   by the folder each clip sits in. Plus the "Reveal recording root" button at
   the bottom of that column.

2. **Header controls**: a "Search clips" field and a "Newest" sort control.
   Search filters on filename and game. Sort at minimum Newest/Oldest/Largest.
   The header eyebrow reads "<n> CLIPS · <total size>" from the real scan.

3. **Table header row**: CLIP / LENGTH / SIZE / RECORDED / ACTIONS.

4. **Row actions**: play, reveal-in-folder, delete. Delete must respect the
   same rule tests/test_clips.py encodes for v3 — read that test before
   implementing it and keep the behaviour identical.

5. **Length and thumbnails** via `obsauto/thumbs.py`. ffmpeg is an OPTIONAL
   soft-dep: when `thumbs.available()` is False, show the placeholder and no
   Length, never a guess. Thumbnail work must be single-flight — v3 had a bug
   where every visit to Clips spawned a thread launching an ffprobe per clip.

6. **Footer note**: "Clips under min_clip_seconds (Ns) are deleted
   automatically and never listed here." N from config.

Notes:
- `ffprobe` reports no duration for a file still being written (Matroska writes
  it on finalisation). That is correct, not a failure — show no Length, do not
  paper over it.
- The relative "RECORDED" column ("2 min ago", "Yesterday", "Tue") is real
  formatting off mtime, not filler.
- Do NOT implement row-action *play* by shelling out to a player if that needs
  a new dependency; reveal-in-folder is enough, and say so in your deviations.


## Project contract - read before writing any code

Repo root: C:\Users\antho\nebula

Read these first, in order:
  1. .claude/skills/nebula-ui/SKILL.md      rules, traps, the screenshot loop
  2. .claude/skills/nebula-polish/SKILL.md  the aesthetic checklist
  3. design/ui-v3/BUILD-SPEC.md             THE AUTHORITY on every number
  4. V4-GUIDE.md                            what v4 is, and the build order

Authority order:
  BUILD-SPEC.md > design/ui-v3/frames/*.png > everything else.
  If a frame and the spec table disagree, the table wins.

Hard rules - these outrank the design:
  1. Animate ONLY `transform` and `opacity`. Never width/height/top/left/filter.
  2. NO FABRICATED NUMBERS. Every figure comes from a real source through
     window.pywebview.api. No source -> render the honest empty state. The
     mockup is full of filler (418 clips, 1.9 TB, a connected macropad with an
     HID id) - do not copy any of it.
  3. No hand-typed colours, radii, durations or easings. Everything comes from
     spike/web/tokens.css, GENERATED from obsauto/design_v3.py by
     `python spike/gen_tokens.py`. Need a new token? Add it to the Python and
     re-run. Never edit tokens.css by hand.
  4. Do not modify obsauto/, main.py or tests/. Need data that isn't exposed?
     Add a method to the Api class in spike/app.py that calls the existing
     modules.
  5. Every card is two layers: tinted shell wrapping a darker core, with
     inner radius = outer radius - padding. A flat card is a bug.
  6. No npm, no bundler, no framework, no dependency. Plain HTML/CSS/JS.

Traps that have already cost time:
  - `rgb(var(--x-rgb) / .8)` needs a SPACE-separated triplet. `rgb(24, 20, 40
    / .8)` is a parse error, dropped silently, and the surface does not paint.
  - pywebview injects its bridge asynchronously. Poll for window.pywebview.api;
    do not rely on the pywebviewready event alone.
  - There is no console. Surface JS errors in the HUD (see fail() in app.js).
  - Before trusting a screenshot: `python tools/shoot.py --list`. Two windows
    titled Nebula means you are looking at a stale process.
  - A kill filter matching 'app.py' also matches its own command line. Exclude
    os.getpid() or you kill your own shell.

Definition of done - all of these, every task:
  python -m ruff check .          (or `ruff check .`)
  python tools/lint_tokens.py
  python tests/test_v4_tray.py
  python tests/test_design_v3.py
  python tools/shoot.py --out shots/check.png     and LOOK at it

Deliberate deviations are fine and must be written down with the reason.
Never silently "fix" something the spec asked for by removing it.


## Report back

When finished, write `.cursor/handoff/outbox/t001.md` containing:

  # t001
  status: done | blocked | partial

  ## Changed
  (files touched, one line each)

  ## Deliberate deviations
  (what you did not do the way the design says, and why - or "none")

  ## Gate
  (paste the output of each command in Definition of done)

  ## Notes for review
  (anything the reviewer should look at first)
