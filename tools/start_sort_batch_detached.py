"""Detached launcher for sort_recovered_clips — survives Cursor shell death.

Refuses to start a second copy if one is already running (WMI scan + pid lock).
Default: drain until empty with freeform retry + keep vision loaded.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(ROOT, "logs", "sort_recovered_drain.pid")
LOG = os.path.join(ROOT, "logs", "sort_recovered_drain_live.log")


def _live_sorter_pids() -> list[int]:
    try:
        out = subprocess.check_output(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Where-Object { $_.CommandLine -match 'sort_recovered_clips\\.py' } | "
                "Select-Object -ExpandProperty ProcessId",
            ],
            text=True,
            errors="replace",
            timeout=20,
        )
    except Exception:
        return []
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def main():
    os.chdir(ROOT)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)

    live = _live_sorter_pids()
    if live and "--force" not in sys.argv:
        print("already running pid=%s — refuse duplicate (pass --force to override)"
              % ",".join(str(p) for p in live))
        with open(LOCK, "w", encoding="utf-8") as fh:
            fh.write("%s\n" % live[0])
        return 0

    cmd = [
        sys.executable,
        os.path.join(ROOT, "tools", "sort_recovered_clips.py"),
        "--apply",
        "--resume",
        "--retry-skipped",
        "--until-empty",
        "--keep-loaded",
    ]
    if "--" in sys.argv:
        cmd.extend(sys.argv[sys.argv.index("--") + 1 :])

    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write("\n--- detached launch %s ---\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        fh.flush()
        proc = subprocess.Popen(
            cmd,
            stdout=fh,
            stderr=subprocess.STDOUT,
            cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
            close_fds=True,
        )
    # Detached Popen pid can be the wrapper; resolve the real sorter.
    time.sleep(2.0)
    live = _live_sorter_pids()
    pid = live[0] if live else proc.pid
    with open(LOCK, "w", encoding="utf-8") as fh:
        fh.write("%s\n" % pid)
    print("started pid=%s log=%s" % (pid, LOG))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
