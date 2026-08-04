"""Render the v3 mockup's frames to PNGs, one file per frame.

    python tools/frames.py
    python tools/frames.py --only 2b,6a,7b

Why
---
`design/ui-v3/Nebula UI Mockups v3.dc.html` is 347 KB - roughly 87,000 tokens.
No agent has ever read it whole; the DesignSync MCP truncates it at 256 KiB and
loses 7c-7g in silence, and even the committed copy blows a context window. So
the design has only ever reached the implementation through prose: BUILD-SPEC.md
and FRAMES.md, both hand-written compressions.

This turns the same file into ~27 images of a few hundred KB each. An agent can
open exactly the one frame it is building, next to a `tools/shoot.py` capture of
what it actually built, and compare them as pictures rather than as adjectives.

Pair it with shoot.py:

    python tools/frames.py --only 2b        # design/ui-v3/frames/2b.png
    python spike/app.py &
    python tools/shoot.py --out shots/2b.png

...then look at both.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import webview

from tools.shoot import grab, set_dpi_aware, windows

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCKUP = os.path.join(ROOT, "design", "ui-v3", "Nebula UI Mockups v3.dc.html")
OUTDIR = os.path.join(ROOT, "design", "ui-v3", "frames")

TITLE = "Nebula mockup frames"

# Every anchored frame in the file. 2a-2l are the v3 screens, 6a-6h the
# deep-dive fix panels, 7a-7g the new features.
FRAMES = (["2%s" % c for c in "abcdefghijkl"]
          + ["6%s" % c for c in "abcdefgh"]
          + ["7%s" % c for c in "abcdefg"])

JS_RECT = """
(function () {
  var el = document.getElementById(%r);
  if (!el) return null;
  el.scrollIntoView({block: 'start', behavior: 'instant'});
  window.scrollBy(0, -24);
  var r = el.getBoundingClientRect();
  return {x: r.left, y: r.top, w: r.width, h: r.height,
          vw: window.innerWidth, vh: window.innerHeight};
})();
"""


def run(only=None, pad=16):
    os.makedirs(OUTDIR, exist_ok=True)
    wanted = [f for f in FRAMES if not only or f in only]
    written = []

    def worker(window):
        # Let the mockup's own fonts and gradients settle before the first shot.
        time.sleep(3.0)

        hwnd = next((h for h, t in windows(TITLE)), None)
        if hwnd is None:
            print("could not find the mockup window")
            window.destroy()
            return

        for fid in wanted:
            try:
                rect = window.evaluate_js(JS_RECT % fid)
            except Exception as exc:
                print("  %-4s js failed: %s" % (fid, exc))
                continue
            if not rect:
                print("  %-4s no such anchor" % fid)
                continue

            time.sleep(0.45)                 # let the scroll land
            shot = grab(hwnd)

            # The PNG is in device pixels, the rect in CSS pixels. On a 150%
            # panel those differ by 1.5x, and cropping with the wrong one puts
            # the frame off the bottom of the image.
            scale = shot.width / float(rect["vw"] or shot.width)
            x = max(0, int(rect["x"] * scale) - pad)
            y = max(0, int(rect["y"] * scale) - pad)
            w = min(shot.width - x, int(rect["w"] * scale) + pad * 2)
            h = min(shot.height - y, int(rect["h"] * scale) + pad * 2)
            if w <= 2 or h <= 2:
                print("  %-4s empty rect" % fid)
                continue

            path = os.path.join(OUTDIR, "%s.png" % fid)
            shot.crop((x, y, x + w, y + h)).save(path)
            written.append(path)
            print("  %-4s %4dx%-4d -> %s" % (fid, w, h, os.path.relpath(path, ROOT)))

        window.destroy()

    if not os.path.isfile(MOCKUP):
        raise SystemExit("mockup not found: %s" % MOCKUP)

    print("rendering %d frame(s) from %s" % (len(wanted), os.path.basename(MOCKUP)))
    win = webview.create_window(TITLE, MOCKUP, width=1440, height=1000,
                                frameless=True, background_color="#0A0812")
    webview.start(worker, win)
    print("wrote %d file(s) to %s" % (len(written), os.path.relpath(OUTDIR, ROOT)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated frame ids, e.g. 2b,6a")
    ap.add_argument("--pad", type=int, default=16)
    a = ap.parse_args()

    set_dpi_aware()
    only = [s.strip() for s in a.only.split(",") if s.strip()]
    run(only=only or None, pad=a.pad)


if __name__ == "__main__":
    main()
