"""Run every test file with a hard per-file timeout.

    python tools/run_tests.py                 # all of tests/test_*.py
    python tools/run_tests.py -k toast        # substring filter
    python tools/run_tests.py --timeout 90    # per-file seconds (default 150)

Why this exists
---------------
Three test files once hung their Tk mainloop, so nobody could run "the whole
suite" - which is exactly how two real regressions survived a week on both
machines. Each file here gets its own process and a watchdog; a hang is
reported and the run continues. PYTHONUTF8=1 is forced because several checks
print arrows and box-drawing that cp1252 cannot encode.

Exit code is 1 if anything failed or timed out.
"""
import argparse
import os
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")


def run_one(path, timeout):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    proc = [sys.executable, path]

    result = {"name": os.path.basename(path), "state": "PASS", "detail": ""}

    def target():
        try:
            p = subprocess.run(proc, cwd=ROOT, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               env=env, timeout=timeout)
            if p.returncode != 0:
                # A 3-line tail once hid *which* checks failed on a machine
                # where the file passed everywhere else - CI needs the whole
                # picture, not a teaser. Capped so a runaway print loop
                # cannot flood the log.
                out = (p.stdout or "").strip().splitlines()
                tail = out[-400:]
                result["state"] = "FAIL"
                result["detail"] = " | ".join(tail)[:8000]
        except subprocess.TimeoutExpired:
            result["state"] = "TIMEOUT"
            result["detail"] = "%ds" % timeout
        except Exception as exc:  # noqa: BLE001 - report, don't crash the run
            result["state"] = "FAIL"
            result["detail"] = str(exc)[:200]

    t = threading.Thread(target=target, daemon=True)
    t.start()
    # subprocess.TimeoutExpired kills the child; the thread always ends.
    t.join(timeout + 15)
    if t.is_alive():
        result["state"] = "TIMEOUT"
        result["detail"] = "%ds (runner)" % timeout
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-k", default="", help="only files containing this")
    ap.add_argument("--timeout", type=int, default=150,
                    help="per-file seconds (default 150)")
    args = ap.parse_args(argv)

    files = sorted(
        os.path.join(TESTS, n) for n in os.listdir(TESTS)
        if n.startswith("test_") and n.endswith(".py") and args.k in n)
    if not files:
        print("no test files matched")
        return 1

    bad = []
    for path in files:
        r = run_one(path, args.timeout)
        mark = {"PASS": "PASS", "FAIL": "FAIL",
                "TIMEOUT": "HANG"}[r["state"]]
        line = "%-6s %-40s %s" % (mark, r["name"], r["detail"])
        print(line, flush=True)
        if r["state"] != "PASS":
            bad.append(r["name"])

    print("\n%d/%d passed%s" % (
        len(files) - len(bad), len(files),
        "" if not bad else "  FAILED/HUNG: " + ", ".join(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
