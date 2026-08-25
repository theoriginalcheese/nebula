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
    logs = []
    mon.is_obs_running = lambda: False
    mon.obs_launch_task_exists = lambda: False
    mon._launch_via_scheduled_task = lambda log: False
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


if __name__ == "__main__":
    test_isdir_within()
    test_ensure_obs_already_running()
    test_ensure_obs_logs_missing_task()
    test_wait_for_obs_gives_up()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
    print("ALL PASS")
