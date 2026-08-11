"""Find and verify a Segoe Fluent codepoint by rendering it - never from memory.

CLAUDE.md: "every codepoint was verified by rendering it". This is that check,
made repeatable. It renders candidates at the sizes Nebula actually draws icons
(12-24px), rejects blanks and .notdef boxes, and measures whether a glyph is a
*hollow ring* - ink around the perimeter, hole in the middle - which is what
`circle-dashed` needs to be to read as "armed, not live" against filled `record`.

    python tools/verify_glyph.py --scan            # find ring candidates
    python tools/verify_glyph.py --check 0xEA3A    # inspect one
    python tools/verify_glyph.py --montage out.png 0xEA3A 0xE7C8
"""

from __future__ import annotations

import argparse
import sys

from PIL import Image, ImageDraw, ImageFont

FONT_FILE = r"C:\Windows\Fonts\SegoeIcons.ttf"
SIZES = (12, 16, 24)
BOX = 64


def render(cp: int, px: int) -> Image.Image:
    img = Image.new("L", (BOX, BOX), 0)
    font = ImageFont.truetype(FONT_FILE, px)
    ImageDraw.Draw(img).text((BOX // 2, BOX // 2), chr(cp), font=font, fill=255, anchor="mm")
    return img


def ink(img: Image.Image) -> float:
    px = img.load()
    return sum(1 for y in range(BOX) for x in range(BOX) if px[x, y] > 40) / (BOX * BOX)


def bbox(img: Image.Image):
    return img.point(lambda v: 255 if v > 40 else 0).getbbox()


def is_notdef(cp: int) -> bool:
    """A .notdef box renders identically to an unmapped codepoint far out of range."""
    a = render(cp, 24).tobytes()
    return a == render(0xFFFD, 24).tobytes() or a == render(0x10FFFD, 24).tobytes()


def hollow_ratio(cp: int, px: int = 24) -> float:
    """Ink in the middle third vs ink overall. Low = hollow ring, high = filled."""
    img = render(cp, px)
    box = bbox(img)
    if not box:
        return 1.0
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w < 3 or h < 3:
        return 1.0
    px_ = img.load()
    cx0, cx1 = x0 + w // 3, x1 - w // 3
    cy0, cy1 = y0 + h // 3, y1 - h // 3
    centre = sum(1 for y in range(cy0, cy1) for x in range(cx0, cx1) if px_[x, y] > 40)
    area = max(1, (cx1 - cx0) * (cy1 - cy0))
    return centre / area


def squareness(cp: int, px: int = 24) -> float:
    box = bbox(render(cp, px))
    if not box:
        return 0.0
    w, h = box[2] - box[0], box[3] - box[1]
    return min(w, h) / max(w, h) if max(w, h) else 0.0


def describe(cp: int) -> dict:
    blank = all(ink(render(cp, s)) < 0.002 for s in SIZES)
    return {
        "cp": cp,
        "blank": blank,
        "notdef": is_notdef(cp),
        "hollow": round(hollow_ratio(cp), 3),
        "square": round(squareness(cp), 3),
        "ink24": round(ink(render(cp, 24)), 4),
        "ink12": round(ink(render(cp, 12)), 4),
    }


def scan(lo: int, hi: int, limit: int) -> list[dict]:
    """Round, hollow, still legible at 12px - the shortlist for a status ring."""
    out = []
    for cp in range(lo, hi):
        try:
            d = describe(cp)
        except Exception:  # noqa: BLE001 - a bad codepoint is just not a candidate
            continue
        if d["blank"] or d["notdef"]:
            continue
        if d["square"] < 0.85:        # must be round, not a wide pictogram
            continue
        if d["hollow"] > 0.12:        # must be genuinely hollow
            continue
        if d["ink12"] < 0.004:        # must survive 12px
            continue
        out.append(d)
        if len(out) >= limit:
            break
    return out


def montage(path: str, cps: list[int]) -> None:
    cell = BOX
    img = Image.new("L", (cell * len(SIZES), cell * len(cps)), 0)
    for row, cp in enumerate(cps):
        for col, px in enumerate(SIZES):
            img.paste(render(cp, px), (col * cell, row * cell))
    img.save(path)
    print(f"wrote {path}  rows={[hex(c) for c in cps]}  cols={SIZES}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--lo", type=lambda s: int(s, 0), default=0xE700)
    ap.add_argument("--hi", type=lambda s: int(s, 0), default=0xF8B3)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--check", type=lambda s: int(s, 0), nargs="*")
    ap.add_argument("--montage", nargs="+")
    a = ap.parse_args(argv)

    if a.montage:
        montage(a.montage[0], [int(c, 0) for c in a.montage[1:]])
        return 0
    if a.check:
        for cp in a.check:
            d = describe(cp)
            print(f"  {hex(cp)}  blank={d['blank']} notdef={d['notdef']} "
                  f"hollow={d['hollow']} square={d['square']} ink24={d['ink24']} ink12={d['ink12']}")
        return 0
    if a.scan:
        found = scan(a.lo, a.hi, a.limit)
        print(f"{'codepoint':11} {'hollow':>7} {'square':>7} {'ink24':>7} {'ink12':>7}")
        for d in found:
            print(f"  {hex(d['cp']):9} {d['hollow']:7.3f} {d['square']:7.3f} "
                  f"{d['ink24']:7.4f} {d['ink12']:7.4f}")
        print(f"\n{len(found)} candidate(s)")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
