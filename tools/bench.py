"""Measure what a Nebula window actually costs, so the v4 decision has numbers.

    python tools/bench.py --launch spike   --seconds 20
    python tools/bench.py --launch gui     --seconds 20
    python tools/bench.py --launch spike   --seconds 20 --minimised

The question this exists to answer
----------------------------------
Nebula is a tray app that runs the entire time a game is in the foreground, on a
laptop whose RAM slots are already full. So "is a webview affordable here" is not
about peak throughput, it is about **idle cost while hidden**. A renderer that
draws a beautiful aurora at 4% CPU and never stops is worse for this app than one
that draws nothing and sleeps.

Both renderers are multi-process (WebView2 splits browser/GPU/renderer), so
everything below sums the whole process tree. Measuring the parent alone would
flatter the webview by several hundred megabytes.

`--minimised` is the case that matters most: browsers throttle
requestAnimationFrame to a stop when a window is occluded or minimised, which Tk
`after()` timers do not. If that holds, the aurora is free exactly when it needs
to be.
"""
import argparse
import os
import subprocess
import sys
import time

import psutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TARGETS = {
    "spike": [sys.executable, os.path.join(ROOT, "spike", "app.py")],
    "gui": [sys.executable, os.path.join(ROOT, "main.py")],
}


def tree(pid):
    try:
        p = psutil.Process(pid)
    except psutil.Error:
        return []
    out = [p]
    try:
        out += p.children(recursive=True)
    except psutil.Error:
        pass
    return out


def measure(pid, seconds, interval=1.0):
    """Sample the tree once a second and report the median CPU and peak RSS.

    Median, not mean: a single GC pause or a disk scan otherwise dominates a
    20-second window and the number stops describing the steady state.
    """
    procs = tree(pid)
    for p in procs:                      # prime cpu_percent's internal baseline
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(0.5)

    cores = psutil.cpu_count() or 1
    cpus, rsss, usss, counts = [], [], [], []
    end = time.time() + seconds
    while time.time() < end:
        time.sleep(interval)
        procs = tree(pid)                # children come and go
        cpu = rss = uss = 0.0
        alive = 0
        for p in procs:
            try:
                cpu += p.cpu_percent(None)
                rss += p.memory_info().rss
                # Summed RSS double-counts every page Chromium shares between
                # its browser/GPU/renderer processes, which inflates a webview
                # by hundreds of MB against single-process Tk. USS is the memory
                # that would actually be returned if the tree exited, so it is
                # the only figure the two renderers can be compared on.
                uss += p.memory_full_info().uss
                alive += 1
            except psutil.Error:
                continue
        cpus.append(cpu / cores)
        rsss.append(rss / 1048576.0)
        usss.append(uss / 1048576.0)
        counts.append(alive)

    if not cpus:
        return None
    cpus.sort()
    return {"cpu_median": cpus[len(cpus) // 2],
            "cpu_max": cpus[-1],
            "rss_peak_mb": max(rsss),
            "rss_final_mb": rsss[-1],
            "uss_peak_mb": max(usss),
            "uss_final_mb": usss[-1],
            "procs": max(counts),
            "samples": len(cpus)}


def find_window(title):
    import ctypes
    import ctypes.wintypes as wt
    user32 = ctypes.windll.user32
    hits = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if title.lower() in buf.value.lower():
            hits.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return hits


def minimise(title):
    import ctypes
    SW_MINIMIZE = 6
    for hwnd in find_window(title):
        ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
    return bool(find_window(title))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--launch", choices=sorted(TARGETS), required=True)
    ap.add_argument("--seconds", type=int, default=20)
    ap.add_argument("--settle", type=int, default=12,
                    help="seconds to let the window finish starting before sampling")
    ap.add_argument("--minimised", action="store_true",
                    help="minimise the window before sampling (the tray-app case)")
    ap.add_argument("--keep", action="store_true", help="leave the app running")
    a = ap.parse_args()

    cmd = TARGETS[a.launch]
    print("launching %s ..." % a.launch)
    proc = subprocess.Popen(cmd, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(a.settle)
        if a.minimised:
            ok = minimise("Nebula")
            print("minimised: %s" % ("yes" if ok else "no window found"))
            time.sleep(2)

        print("sampling %ds ..." % a.seconds)
        r = measure(proc.pid, a.seconds)
        if not r:
            print("no samples - did the app exit?")
            return

        state = "minimised" if a.minimised else "visible"
        print()
        print("  %-22s %s (%s)" % ("target", a.launch, state))
        print("  %-22s %d" % ("processes", r["procs"]))
        print("  %-22s %.2f %%" % ("cpu (median)", r["cpu_median"]))
        print("  %-22s %.2f %%" % ("cpu (max)", r["cpu_max"]))
        print("  %-22s %.0f MB" % ("private (uss, peak)", r["uss_peak_mb"]))
        print("  %-22s %.0f MB" % ("private (uss, final)", r["uss_final_mb"]))
        print("  %-22s %.0f MB  (shared pages counted once per process)"
              % ("rss sum (peak)", r["rss_peak_mb"]))
    finally:
        if not a.keep:
            for p in tree(proc.pid)[::-1]:
                try:
                    p.kill()
                except psutil.Error:
                    pass


if __name__ == "__main__":
    main()
