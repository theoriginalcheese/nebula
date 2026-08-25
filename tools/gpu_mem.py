"""Who is holding GPU dedicated / shared memory right now.

    python tools/gpu_mem.py

PID-attributed and split by adapter LUID. Does not sum msedgewebview2 by name.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

import psutil

PS = r"""
$c = Get-Counter '\GPU Adapter Memory(*)\Dedicated Usage','\GPU Adapter Memory(*)\Shared Usage','\GPU Process Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Shared Usage' -ErrorAction SilentlyContinue
foreach ($x in $c.CounterSamples) {
  '{0}|{1}|{2}' -f $x.Path, $x.InstanceName, $x.CookedValue
}
"""


def _rows():
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", PS],
        capture_output=True, text=True, timeout=90,
    )
    out = []
    for line in (r.stdout or "").splitlines():
        parts = line.strip().split("|")
        if len(parts) < 3:
            continue
        path, inst, val = parts[0], parts[1], parts[2]
        try:
            n = float(val.replace(",", ""))
        except ValueError:
            continue
        out.append((path.lower(), inst, n))
    return out


def _luid_of(inst):
    inst = inst.lower()
    if "luid_0x" not in inst:
        return None
    try:
        a, b = inst.split("luid_0x", 1)[1].split("_phys")[0].split("_0x")
        return (a + "_" + b).lower()
    except (IndexError, ValueError):
        return None


def _pid_of(inst):
    inst = inst.lower()
    if "pid_" not in inst:
        return None
    try:
        return int(inst.split("pid_")[1].split("_")[0], 10)
    except (IndexError, ValueError):
        return None


def _proc_name(pid):
    try:
        p = psutil.Process(pid)
        return p.name()
    except psutil.Error:
        return "?"


def _parent_name(pid):
    try:
        return psutil.Process(pid).parent().name()
    except (psutil.Error, AttributeError):
        return "?"


def _proc_cmd(pid):
    try:
        cl = psutil.Process(pid).cmdline() or []
        return " ".join(cl)[:140]
    except psutil.Error:
        return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    a = ap.parse_args()
    del a
    rows = _rows()

    adapters = {}
    for path, inst, n in rows:
        if "gpu adapter memory" not in path:
            continue
        luid = _luid_of(inst) or inst
        slot = adapters.setdefault(luid, {"dedicated": 0.0, "shared": 0.0})
        if "dedicated" in path:
            slot["dedicated"] = max(slot["dedicated"], n)
        else:
            slot["shared"] = max(slot["shared"], n)

    # iGPU = the adapter with more *shared* than dedicated (610M). dGPU = rest.
    labeled = []
    for luid, mem in adapters.items():
        kind = "igpu" if mem["shared"] > mem["dedicated"] else "dgpu"
        if mem["dedicated"] < 1 and mem["shared"] < 1:
            kind = "empty"
        labeled.append((kind, luid, mem))
    labeled.sort(key=lambda x: 0 if x[0] == "igpu" else 1)

    print("=== adapters (usage, not capacity) ===")
    igpu_luids = set()
    for kind, luid, mem in labeled:
        print("  %-5s  ded %7.1f MB  shared %7.1f MB  %s" % (
            kind, mem["dedicated"] / 1048576.0, mem["shared"] / 1048576.0, luid))
        if kind == "igpu":
            igpu_luids.add(luid)

    by = {}
    for path, inst, n in rows:
        if "gpu process memory" not in path:
            continue
        pid = _pid_of(inst)
        luid = _luid_of(inst)
        if pid is None:
            continue
        key = (pid, luid)
        slot = by.setdefault(key, {"dedicated": 0.0, "shared": 0.0})
        if "dedicated" in path:
            slot["dedicated"] += n
        else:
            slot["shared"] += n

    print("\n=== iGPU process memory ===")
    print("%-8s %8s %8s  %-22s %s" % ("pid", "ded MB", "shr MB", "name", "parent"))
    igpu_rows = [(pid, luid, mem) for (pid, luid), mem in by.items() if luid in igpu_luids]
    igpu_rows.sort(key=lambda x: x[2]["dedicated"] + x[2]["shared"], reverse=True)
    nebula_ded = nebula_shr = 0.0
    for pid, luid, mem in igpu_rows[:20]:
        name = _proc_name(pid)
        parent = _parent_name(pid)
        cmd = _proc_cmd(pid)
        print("%-8s %8.1f %8.1f  %-22s %s" % (
            pid, mem["dedicated"] / 1048576.0, mem["shared"] / 1048576.0, name[:22], parent))
        marker = ("nebula" in cmd.lower() or "spike" in cmd.lower()
                  or "spike/app.py" in cmd.replace("\\", "/").lower())
        if marker or "nebula" in name.lower():
            nebula_ded += mem["dedicated"]
            nebula_shr += mem["shared"]
            print("         %s" % cmd[:140])

    print("\nNebula-attributed on iGPU: ded %.1f MB  shared %.1f MB" % (
        nebula_ded / 1048576.0, nebula_shr / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
