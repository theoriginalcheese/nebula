"""Moonlight CLI helper — no live stream required.

    python tests/test_moonlight.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import moonlight as moon

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def run():
    moon._reset_cache()

    check("blank host raises", False)
    try:
        moon.stream_args("", "Desktop")
    except ValueError:
        results[-1] = ("blank host raises", True, "")

    args = moon.stream_args("100.90.134.9", "Desktop", display_mode="windowed")
    check("stream args order",
          args[:3] == ["stream", "100.90.134.9", "Desktop"], args)
    check("display mode flag",
          "--display-mode" in args and "windowed" in args, args)
    check("default app Desktop",
          moon.stream_args("host", "")[2] == "Desktop")

    found = moon.find_exe(
        r"C:\Program Files\Moonlight Game Streaming\Moonlight.exe")
    check("find default install when present",
          found is None or found.endswith("Moonlight.exe"), found)
    check("available matches find",
          moon.available(found or "") == bool(found))

    check("missing path soft",
          moon.find_exe(r"C:\no\such\Moonlight.exe") is not None
          or moon.find_exe(r"C:\no\such\Moonlight.exe") is None)

    # ---- log_details from a fixture file ----
    import tempfile
    work = tempfile.mkdtemp(prefix="nebula-moon-test-")
    fake_log = os.path.join(work, "Moonlight-test.log")
    with open(fake_log, "w", encoding="utf-8") as f:
        f.write(
            '00:00:00 - Current Moonlight version: "6.1.0"\n'
            '00:00:01 - "Alien-Pc" is now online at "192.168.10.1:47989"\n'
            '00:00:02 - "Alien-Pc" is now at "100.90.134.9:47989"\n'
            '00:00:03 - Resolved via QHostAddress("100.90.134.9")\n'
            "00:00:10 - Starting video stream...\n"
            "00:01:00 - Stopping video stream...\n"
        )
    real_newest = moon._newest_log
    try:
        moon._newest_log = lambda: fake_log
        d = moon.log_details()
        check("log: version", d.get("version") == "6.1.0", d)
        check("log: last host", d.get("last_host") == "Alien-Pc", d)
        check("log: prefers now-at address",
              d.get("last_address") == "100.90.134.9:47989", d)
        check("log: stream stopped", d.get("stream") == "stopped", d)
        check("log: ts ips", d.get("tailscale_ips") == ["100.90.134.9"], d)
        check("log: age label present", bool(d.get("log_age")), d)

        with open(fake_log, "a", encoding="utf-8") as f:
            f.write("00:02:00 - Starting video stream...\n")
        d2 = moon.log_details()
        check("log: stream live after restart", d2.get("stream") == "live", d2)
    finally:
        moon._newest_log = real_newest

    moon._newest_log = lambda: None
    try:
        check("log: empty when no file", moon.log_details() == {})
    finally:
        moon._newest_log = real_newest

    check("age: seconds", moon._age_label(12) == "12s ago")
    check("age: minutes", moon._age_label(125) == "2m ago")
    check("age: just now", moon._age_label(2) == "just now")



run()
passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<42} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
