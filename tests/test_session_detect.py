"""Moonlight session detection from its per-launch log.

    python tests/test_session_detect.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import session_detect as sd

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def run():
    work = tempfile.mkdtemp(prefix="nebula-moon-test-")
    real_glob = sd.MOONLIGHT_LOG_GLOB
    # Point the module at our temp dir's Moonlight-*.log pattern.
    sd.MOONLIGHT_LOG_GLOB = os.path.join(work, "Moonlight-*.log")

    try:
        check("no log -> None", sd.moonlight_session_active() is None)

        empty = os.path.join(work, "Moonlight-empty.log")
        with open(empty, "w", encoding="utf-8") as f:
            f.write("Moonlight started\nNo session yet\n")
        check("log with no markers -> False",
              sd.moonlight_session_active() is False)

        live = os.path.join(work, "Moonlight-live.log")
        with open(live, "w", encoding="utf-8") as f:
            f.write("Starting video stream...\n")
        # Newer mtime wins; bump past empty.
        time.sleep(0.05)
        os.utime(live, None)
        check("last marker Starting -> True",
              sd.moonlight_session_active() is True)

        with open(live, "a", encoding="utf-8") as f:
            f.write("Stopping video stream...\n")
        check("last marker Stopping -> False",
              sd.moonlight_session_active() is False)

        with open(live, "a", encoding="utf-8") as f:
            f.write("Starting video stream...\n")
        check("reconnect Starting after Stopping -> True",
              sd.moonlight_session_active() is True)

        # An older log with a live start must not override a newer stopped one.
        older = os.path.join(work, "Moonlight-old.log")
        with open(older, "w", encoding="utf-8") as f:
            f.write("Starting video stream...\n")
        # Make `live` clearly newest and stopped.
        with open(live, "w", encoding="utf-8") as f:
            f.write("Starting video stream...\nStopping video stream...\n")
        now = time.time()
        os.utime(older, (now - 10, now - 10))
        os.utime(live, (now, now))
        check("newest log wins over older live log",
              sd.moonlight_session_active() is False)
    finally:
        sd.MOONLIGHT_LOG_GLOB = real_glob


run()
passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
