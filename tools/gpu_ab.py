"""Measure Nebula's GPU cost under a given backdrop configuration.

    python tools/gpu_ab.py                 # everything on
    python tools/gpu_ab.py --url nowind=1  # parallax instead of wind
    python tools/gpu_ab.py --url nosheet=1 # no baked aurora sheet

Why this exists
---------------
A combined change - baking the aurora into one sheet *and* replacing star
parallax with a shared wind vector - regressed the GPU from 42% to 48%, and
every check in the gate passed because none of them measure a GPU. Two changes,
one number, no way to tell which one did it.

So each half gets a switch and each switch gets a measurement. A perf claim
needs an A and a B.

Attribution matters: there are ~20 msedgewebview2.exe processes on this machine
and only six are Nebula's. Summing by process name reports the whole desktop.
"""
import argparse
import os
import subprocess
import sys
import time

import psutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PS = r"""
$ids = @(%s)
$c = (Get-Counter '\GPU Engine(*)\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples
$s = 0
foreach ($x in $c) { if ($x.InstanceName -match 'pid_(\d+)' -and $ids -contains [int]$Matches[1]) { $s += $x.CookedValue } }
"{0:N2}" -f $s
"""


def webview_pids(root_pid):
    """Nebula's own webview children, by walking the tree - not by name."""
    out = []
    try:
        for k in psutil.Process(root_pid).children(recursive=True):
            try:
                if "msedgewebview2" in k.name().lower():
                    out.append(k.pid)
            except psutil.Error:
                continue
    except psutil.Error:
        pass
    return out


def gpu_of(pids):
    if not pids:
        return 0.0
    script = PS % ",".join(str(p) for p in pids)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       capture_output=True, text=True, timeout=120)
    try:
        return float((r.stdout or "0").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return 0.0


def minimise(title="Nebula", restore=False):
    import ctypes
    u = ctypes.windll.user32
    h = u.FindWindowW(None, title)
    if h:
        u.ShowWindow(h, 9 if restore else 6)
    return bool(h)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="", help="query string, e.g. nowind=1")
    ap.add_argument("--settle", type=int, default=22)
    ap.add_argument("--samples", type=int, default=7)
    a = ap.parse_args()

    for p in psutil.process_iter(["cmdline"]):
        cl = " ".join(p.info["cmdline"] or [])
        if cl.rstrip().endswith("app.py") or "--url=" in cl:
            try:
                p.kill()
            except psutil.Error:
                pass
    time.sleep(3)

    cmd = [sys.executable, "spike/app.py", "--show", "--dev"]
    if a.url:
        cmd.append("--url=%s" % a.url)
    proc = subprocess.Popen(cmd, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    label = a.url or "(all on)"
    try:
        time.sleep(a.settle)
        pids = webview_pids(proc.pid)
        if not pids:
            print("%-14s  no webview processes found - did it start?" % label)
            return 1

        # One Get-Counter call is a single instant. GPU load from a compositor
        # is bursty, so a single sample can catch an idle gap and report 0% for
        # a backdrop that is plainly animating. Sample over a window and take
        # the median of several.
        vals = []
        for _ in range(a.samples):
            vals.append(gpu_of(pids))
            time.sleep(2)
        vals.sort()
        vis = vals[len(vals) // 2]
        minimise()
        time.sleep(10)
        vals = []
        for _ in range(a.samples):
            vals.append(gpu_of(pids))
            time.sleep(2)
        vals.sort()
        mini = vals[len(vals) // 2]

        print("%-14s  visible %5.1f%%   minimised %5.1f%%   (%d webview procs)"
              % (label, vis, mini, len(pids)))
    finally:
        try:
            for k in psutil.Process(proc.pid).children(recursive=True):
                k.kill()
            proc.kill()
        except psutil.Error:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
