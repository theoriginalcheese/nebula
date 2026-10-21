"""OBS launch helpers — scheduled task, wait, no real OBS process.

    python tests/test_obs_launch.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import fsprobe
from obsauto import monitor as mon

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


def test_isdir_within():
    work = os.path.dirname(os.path.abspath(__file__))
    check("local dir is true", fsprobe.isdir_within(work, timeout=1.0))
    check("missing path is false",
          fsprobe.isdir_within(os.path.join(work, "no-such-dir-xyz"), 1.0)
          is False)
    check("empty path is false", fsprobe.isdir_within("", 1.0) is False)

    real = os.path.isdir

    def slow(_path):
        time.sleep(2.0)
        return True

    os.path.isdir = slow
    try:
        t0 = time.perf_counter()
        ok = fsprobe.isdir_within(work, timeout=0.25)
        dt = time.perf_counter() - t0
        check("timeout returns false", ok is False)
        check("timeout does not wait the full hang", dt < 1.0, "%.2fs" % dt)
    finally:
        os.path.isdir = real


def test_ensure_obs_already_running():
    real = mon.is_obs_running
    logs = []
    mon.is_obs_running = lambda: True
    try:
        check("already running is True",
              mon.ensure_obs_running("C:/nope.exe", log=logs.append) is True)
        check("already running does not log a launch", logs == [], logs)
    finally:
        mon.is_obs_running = real


def test_ensure_obs_logs_missing_task():
    real_run = mon.is_obs_running
    real_task = mon.obs_launch_task_exists
    real_launch = mon._launch_via_scheduled_task
    real_clear = mon.clear_unclean_shutdown_prompt
    logs = []
    mon.is_obs_running = lambda: False
    mon.obs_launch_task_exists = lambda: False
    mon._launch_via_scheduled_task = lambda log: False
    mon.clear_unclean_shutdown_prompt = lambda *a, **k: False
    try:
        ok = mon.ensure_obs_running(
            r"C:\definitely-missing-obs64.exe", log=logs.append, wait=0.4)
        check("missing obs_path returns False", ok is False)
        check("missing task is logged",
              any("NebulaLaunchOBS" in x and "missing" in x.lower()
                  for x in logs), logs)
    finally:
        mon.is_obs_running = real_run
        mon.obs_launch_task_exists = real_task
        mon._launch_via_scheduled_task = real_launch
        mon.clear_unclean_shutdown_prompt = real_clear


def test_wait_for_obs_gives_up():
    real = mon.is_obs_running
    mon.is_obs_running = lambda: False
    try:
        t0 = time.perf_counter()
        ok = mon._wait_for_obs(0.5, log=lambda *_: None)
        dt = time.perf_counter() - t0
        check("wait returns False when OBS never appears", ok is False)
        check("wait respects timeout", 0.4 <= dt < 1.5, "%.2fs" % dt)
    finally:
        mon.is_obs_running = real


def test_clear_unclean_shutdown_prompt():
    import tempfile
    cfg = tempfile.mkdtemp(prefix="nebula-obs-cfg-")
    sentinel = os.path.join(cfg, ".sentinel")
    os.makedirs(os.path.join(sentinel, "inner"))
    legacy = os.path.join(cfg, "safe_mode")
    with open(legacy, "w", encoding="utf-8") as f:
        f.write("left by a crash")
    kept = os.path.join(cfg, "global.ini")
    with open(kept, "w", encoding="utf-8") as f:
        f.write("[General]\n")
    logs = []
    real = mon.is_obs_running
    try:
        mon.is_obs_running = lambda: False
        ok = mon.clear_unclean_shutdown_prompt(
            log=logs.append, config_dirs=[cfg])
        check("sentinel and safe_mode are removed", ok is True)
        check("sentinel directory is gone", not os.path.exists(sentinel))
        check("legacy safe_mode file is gone", not os.path.exists(legacy))
        check("other config files stay", os.path.isfile(kept))
        check("clear is logged", any("start normally" in x for x in logs), logs)

        os.makedirs(sentinel)
        mon.is_obs_running = lambda: True
        logs.clear()
        ok = mon.clear_unclean_shutdown_prompt(
            log=logs.append, config_dirs=[cfg])
        check("running OBS keeps its sentinel", ok is False)
        check("sentinel still there while OBS runs", os.path.isdir(sentinel))
        check("no clear log while OBS runs", logs == [], logs)
    finally:
        mon.is_obs_running = real


def test_launch_args_skip_startup_dialogs():
    import tempfile
    work = tempfile.mkdtemp(prefix="nebula-obs-exe-")
    exe = os.path.join(work, "obs64.exe")
    with open(exe, "wb") as f:
        f.write(b"")
    seen = {}
    logs = []

    def fake_popen(argv, cwd=None):
        seen["argv"] = list(argv)
        seen["cwd"] = cwd
        return object()

    real_run = mon.is_obs_running
    real_task = mon.obs_launch_task_exists
    real_launch = mon._launch_via_scheduled_task
    real_clear = mon.clear_unclean_shutdown_prompt
    real_popen = mon.subprocess.Popen
    real_wait = mon._wait_for_obs
    mon.is_obs_running = lambda: False
    mon.obs_launch_task_exists = lambda: False
    mon._launch_via_scheduled_task = lambda log: False
    mon.clear_unclean_shutdown_prompt = lambda *a, **k: logs.append("cleared") or True
    mon.subprocess.Popen = fake_popen
    mon._wait_for_obs = lambda *a, **k: True
    try:
        ok = mon.ensure_obs_running(exe, log=logs.append, wait=0.1)
        check("fallback launch reports success", ok is True)
        check("prompt cleared before launch", "cleared" in logs, logs)
        argv = seen.get("argv") or []
        check("launches minimized", "--minimize-to-tray" in argv, argv)
        check("skips the missing-files dialog",
              "--disable-missing-files-check" in argv, argv)
        check("skips the updater dialog", "--disable-updater" in argv, argv)
        check("does not force safe mode", "--safe-mode" not in argv, argv)
    finally:
        mon.is_obs_running = real_run
        mon.obs_launch_task_exists = real_task
        mon._launch_via_scheduled_task = real_launch
        mon.clear_unclean_shutdown_prompt = real_clear
        mon.subprocess.Popen = real_popen
        mon._wait_for_obs = real_wait


if __name__ == "__main__":
    test_isdir_within()
    test_ensure_obs_already_running()
    test_ensure_obs_logs_missing_task()
    test_wait_for_obs_gives_up()
    test_clear_unclean_shutdown_prompt()
    test_launch_args_skip_startup_dialogs()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
    print("ALL PASS")
