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

    # ---- wait_until_streaming helpers (no live Moonlight) ----
    import tempfile
    work2 = tempfile.mkdtemp(prefix="nebula-moon-wait-")
    log2 = os.path.join(work2, "Moonlight-wait.log")
    with open(log2, "w", encoding="utf-8") as f:
        f.write("boot\n")
    baseline = os.path.getsize(log2)
    check("stream not started yet",
          moon._stream_started_since(log2, baseline) is False)
    with open(log2, "a", encoding="utf-8") as f:
        f.write("00:00:10 - Starting video stream...\n")
    check("stream started after baseline",
          moon._stream_started_since(log2, baseline) is True)
    check("log grew", moon._log_grew(log2, baseline) is True)
    check("stream title detected",
          moon._is_stream_window("Alien-Pc - Moonlight", 1920 * 1080) is True)
    check("host list not stream",
          moon._is_stream_window("Moonlight", 900 * 600) is False)
    check("host chrome exact title",
          moon._is_host_chrome("Moonlight", 900 * 600) is True)

    moon.stop_chrome_guard()
    moon.start_chrome_guard(poll=0.05)
    check("chrome guard starts", moon._chrome_guard_stop is not None
          and not moon._chrome_guard_stop.is_set())
    moon.start_chrome_guard(poll=0.05)  # idempotent
    first = moon._chrome_guard_stop
    moon.start_chrome_guard(poll=0.05)
    check("chrome guard single-flight", moon._chrome_guard_stop is first)
    moon.stop_chrome_guard()
    check("chrome guard stops", moon._chrome_guard_stop is None)

    # New log file mid-wait (Moonlight's real behaviour per launch).
    from obsauto import session_detect as sd
    old_log = os.path.join(work2, "Moonlight-old.log")
    new_log = os.path.join(work2, "Moonlight-new.log")
    with open(old_log, "w", encoding="utf-8") as f:
        f.write("old session\nStopping video stream...\n")
    with open(new_log, "w", encoding="utf-8") as f:
        f.write("boot\n")
    paths = {"cur": old_log}
    real_newest = sd._newest_moonlight_log
    real_hide = moon.hide_client_windows
    try:
        sd._newest_moonlight_log = lambda: paths["cur"]
        moon.hide_client_windows = lambda configured_path="", host_chrome_only=False: None
        # Flip to the new log + Starting marker after a beat.
        import threading
        def _flip():
            import time as _t
            _t.sleep(0.15)
            with open(new_log, "a", encoding="utf-8") as f:
                f.write("Starting video stream...\n")
            paths["cur"] = new_log
        threading.Thread(target=_flip, daemon=True).start()
        result = moon.wait_until_streaming(
            proc=None, timeout=2.0, hide=True,
            baseline_len=os.path.getsize(old_log), poll=0.05)
        check("wait follows new log file", result == "live", result)
    finally:
        sd._newest_moonlight_log = real_newest
        moon.hide_client_windows = real_hide
run()
passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<42} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
