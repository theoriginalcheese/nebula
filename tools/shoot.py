"""Capture a Nebula window to PNG, so an agent can see what it built.

    python tools/shoot.py --title Nebula --out shots/clips.png
    python tools/shoot.py --list

Why this exists
---------------
Nebula is a visual product whose renderer nobody could see. Every fidelity
defect in the 6.7 fix list - the aurora measuring 3.6% instead of 19%, stars
over the chrome, the missing second card layer - was found by a human looking
at the window and writing a paragraph about it. This closes that loop: run it,
`Read` the PNG, compare against design/ui-v3/frames/, fix, repeat.

Works against both renderers, deliberately. `gui.py` (tk) and `spike/app.py`
(WebView2) are both just top-level HWNDs, so the same tool measures the old and
the new and the comparison is apples to apples.

The capture path
----------------
PrintWindow(PW_RENDERFULLCONTENT) asks the window to render itself into a DC,
which - unlike a screen grab - works when the window is occluded or partly off
screen, and does not capture whatever is sitting on top of it. It is also the
only one of the two that can capture a GPU-composited surface like WebView2's,
and even then it can come back blank; `--verify` detects that and falls back to
a screen-region grab so a run never silently produces a black rectangle.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import time

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi

PW_RENDERFULLCONTENT = 0x00000002
DWMWA_EXTENDED_FRAME_BOUNDS = 9
SRCCOPY = 0x00CC0020


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


def set_dpi_aware():
    """Without this every coordinate comes back in virtualised 96-DPI space and
    the capture is a blurry crop on a scaled laptop panel."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def windows(match=None):
    """Every visible top-level window, optionally filtered by title substring."""
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        if match is None or match.lower() in title.lower():
            out.append((hwnd, title))
        return True

    user32.EnumWindows(cb, 0)
    return out


def frame_bounds(hwnd):
    """DWM's true bounds. GetWindowRect includes the invisible resize border,
    which on Windows 11 is ~7px of transparent padding on three sides - enough
    to shift every measurement you would then take off the PNG."""
    r = wt.RECT()
    ok = dwmapi.DwmGetWindowAttribute(
        wt.HMODULE(hwnd), wt.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(r), ctypes.sizeof(r))
    if ok != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def grab(hwnd):
    """PrintWindow into a PIL image."""
    r = frame_bounds(hwnd)
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        raise RuntimeError("window has no area (minimised?)")

    src = user32.GetWindowDC(hwnd)
    dc = gdi32.CreateCompatibleDC(src)
    bmp = gdi32.CreateCompatibleBitmap(src, w, h)
    gdi32.SelectObject(dc, bmp)
    try:
        user32.PrintWindow(hwnd, dc, PW_RENDERFULLCONTENT)

        hdr = BITMAPINFOHEADER()
        hdr.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        hdr.biWidth, hdr.biHeight = w, -h        # negative = top-down
        hdr.biPlanes, hdr.biBitCount = 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(dc, bmp, 0, h, buf, ctypes.byref(hdr), 0)
        return Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(hwnd, src)


def looks_blank(img, tol=6):
    """A GPU surface PrintWindow could not read comes back as one flat colour."""
    small = img.resize((48, 48))
    lo, hi = 255, 0
    for px in small.convert("L").getdata():
        lo, hi = min(lo, px), max(hi, px)
    return (hi - lo) < tol


def grab_screen(hwnd):
    """Fallback: pull the window's rectangle off the screen. Requires the
    window to be unobscured, so it is only used when PrintWindow fails."""
    from PIL import ImageGrab
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.35)
    r = frame_bounds(hwnd)
    return ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))


def shoot(title, out, verify=True, settle=0.0):
    found = windows(title)
    if not found:
        raise SystemExit("no visible window matching %r. Try --list." % title)
    # Prefer an exact title match; otherwise the first hit.
    hwnd, real = next(((h, t) for h, t in found if t == title), found[0])

    if settle:
        time.sleep(settle)

    img = grab(hwnd)
    how = "PrintWindow"
    if verify and looks_blank(img):
        img = grab_screen(hwnd)
        how = "screen (PrintWindow returned blank)"

    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    img.save(out)
    print("%s  %dx%d  via %s  -> %s" % (real, img.width, img.height, how, out))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--title", default="Nebula", help="window title substring")
    ap.add_argument("--out", default="shots/window.png")
    ap.add_argument("--settle", type=float, default=0.0,
                    help="seconds to wait before capturing (let animations reach a pose)")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the blank-frame check and its screen fallback")
    ap.add_argument("--list", action="store_true", help="list visible windows and exit")
    a = ap.parse_args()

    set_dpi_aware()

    if a.list:
        for hwnd, title in windows():
            r = frame_bounds(hwnd)
            print("%-10s %5dx%-5d %s" % (hex(hwnd), r.right - r.left, r.bottom - r.top, title))
        return

    shoot(a.title, a.out, verify=not a.no_verify, settle=a.settle)


if __name__ == "__main__":
    main()
