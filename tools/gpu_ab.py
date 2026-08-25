"""Measure Nebula's GPU cost under a given backdrop configuration.

    python tools/gpu_ab.py                 # visible + minimised
    python tools/gpu_ab.py --url nowind=1  # parallax instead of wind
    python tools/gpu_ab.py --url nosheet=1 # no baked aurora sheet
    python tools/gpu_ab.py --overlay       # main hidden, mini overlay on
    python tools/gpu_ab.py --url fullsheet=1  # aurora baked at 1x (vs 0.5x default)

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

Adapter split: the same PID-attributed engines are grouped by DXGI LUID and
classified as iGPU (low dedicated VRAM, AMD/Intel) vs dGPU (NVIDIA / >1 GB).
"""
import argparse
import os
import subprocess
import sys
import time

import psutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_nebula_source(cmdline):
    cl = " ".join(cmdline or []).replace("\\", "/").lower()
    if "gpu_ab.py" in cl:
        return True
    if "spike/app.py" in cl:
        return True
    return False


def kill_tree(pid, wait=5.0):
    """Kill a process and every descendant. Wait until the root is gone."""
    try:
        root = psutil.Process(pid)
    except psutil.Error:
        return
    kids = []
    try:
        kids = root.children(recursive=True)
    except psutil.Error:
        pass
    for child in kids:
        try:
            child.kill()
        except psutil.Error:
            pass
    try:
        root.kill()
    except psutil.Error:
        pass
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            if not psutil.pid_exists(pid):
                return
        except psutil.Error:
            return
        time.sleep(0.1)


def kill_nebula_source_hosts(exclude=()):
    """Tear down leftover source Nebulas. Never match by process name alone."""
    mine = {os.getpid(), *exclude}
    for _pass in range(2):
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                if proc.info["pid"] in mine:
                    continue
                if not _is_nebula_source(proc.info["cmdline"]):
                    continue
                kill_tree(proc.info["pid"])
            except psutil.Error:
                continue
        time.sleep(0.4)

PS = r"""
$ids = @(%s)
$c = (Get-Counter '\GPU Engine(*)\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples
$mem = (Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage' -ErrorAction SilentlyContinue).CounterSamples
$ded = @{}
foreach ($m in $mem) {
  if ($m.InstanceName -match 'luid_0x([0-9a-fA-F]+)_0x([0-9a-fA-F]+)') {
    $k = $Matches[1].ToLower() + '_' + $Matches[2].ToLower()
    if (-not $ded.ContainsKey($k) -or $m.CookedValue -gt $ded[$k]) { $ded[$k] = $m.CookedValue }
  }
}
$tot = @{}
foreach ($x in $c) {
  if ($x.InstanceName -match 'pid_(\d+)' -and $ids -contains [int]$Matches[1]) {
    $k = 'unknown'
    if ($x.InstanceName -match 'luid_0x([0-9a-fA-F]+)_0x([0-9a-fA-F]+)') {
      $k = $Matches[1].ToLower() + '_' + $Matches[2].ToLower()
    }
    if (-not $tot.ContainsKey($k)) { $tot[$k] = 0 }
    $tot[$k] += $x.CookedValue
  }
}
foreach ($k in $tot.Keys) {
  $d = 0
  if ($ded.ContainsKey($k)) { $d = $ded[$k] }
  "{0}|{1:N4}|{2:N0}" -f $k, $tot[$k], $d
}
"""

DGPU_DEDICATED_BYTES = 1 * 1024 * 1024 * 1024


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


def _classify(dedicated):
    try:
        dedicated = float(dedicated)
    except (TypeError, ValueError):
        dedicated = 0.0
    return "dgpu" if dedicated >= DGPU_DEDICATED_BYTES else "igpu"


def gpu_of(pids):
    """PID-attributed GPU % split by adapter. Always has total/igpu/dgpu."""
    empty = {"total": 0.0, "igpu": 0.0, "dgpu": 0.0}
    if not pids:
        return dict(empty)
    script = PS % ",".join(str(p) for p in pids)
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       capture_output=True, text=True, timeout=120)
    igpu = dgpu = 0.0
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 3:
            continue
        try:
            util = float(parts[1].replace(",", ""))
            dedicated = float(parts[2].replace(",", ""))
        except ValueError:
            continue
        if _classify(dedicated) == "dgpu":
            dgpu += util
        else:
            igpu += util
    return {"total": igpu + dgpu, "igpu": igpu, "dgpu": dgpu}


def _median(vals):
    if not vals:
        return {"total": 0.0, "igpu": 0.0, "dgpu": 0.0}
    ordered = sorted(vals, key=lambda x: x["total"])
    return dict(ordered[len(ordered) // 2])


def minimise(title="Nebula", restore=False):
    import ctypes
    u = ctypes.windll.user32
    h = u.FindWindowW(None, title)
    if h:
        u.ShowWindow(h, 9 if restore else 6)
    return bool(h)


def focus_window(title="Nebula"):
    """Visible samples are meaningless if play-mode quiet froze the aurora."""
    import ctypes
    u = ctypes.windll.user32
    h = u.FindWindowW(None, title)
    if not h:
        return False
    u.ShowWindow(h, 9)  # SW_RESTORE
    u.SetForegroundWindow(h)
    return True


def _fmt(sample):
    return "igpu %5.1f%%  dgpu %5.1f%%  tot %5.1f%%" % (
        sample["igpu"], sample["dgpu"], sample["total"])


def _sample_window(pids, n, gap=2):
    vals = []
    for _ in range(n):
        vals.append(gpu_of(pids))
        time.sleep(gap)
    return _median(vals)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="", help="query string, e.g. nowind=1")
    ap.add_argument("--settle", type=int, default=22)
    ap.add_argument("--samples", type=int, default=7)
    ap.add_argument("--overlay", action="store_true",
                    help="main hidden + mini overlay (recording stand-in)")
    a = ap.parse_args()

    kill_nebula_source_hosts()
    time.sleep(1)

    cmd = [sys.executable, "spike/app.py", "--dev"]
    if not a.overlay:
        cmd.append("--show")
    if a.url:
        cmd.append("--url=%s" % a.url)
    if a.overlay:
        cmd.append("--gpu-overlay")
    proc = subprocess.Popen(cmd, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    label = a.url or ("overlay" if a.overlay else "(all on)")
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
        n = a.samples
        if a.overlay:
            sample = _sample_window(pids, n)
            print("%-14s  overlay-on  %s   (%d webview procs)"
                  % (label, _fmt(sample), len(pids)))
            return 0

        focus_window()
        time.sleep(2)
        vis = _sample_window(pids, n)
        minimise()
        time.sleep(10)
        pids = webview_pids(proc.pid) or pids
        mini = _sample_window(pids, n)

        print("%-14s  visible %s" % (label, _fmt(vis)))
        print("%-14s  minimised %s   (%d webview procs)"
              % (label, _fmt(mini), len(pids)))
    finally:
        kill_tree(proc.pid)
        kill_nebula_source_hosts(exclude={os.getpid()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
