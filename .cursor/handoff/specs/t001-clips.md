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
