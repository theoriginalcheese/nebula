"""TeraCopy background helper — no live TeraCopy transfer required.

    python tests/test_teracopy.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import teracopy as tc

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


check("find_exe returns str", isinstance(tc.find_exe(), str))
check("available is bool", isinstance(tc.available(), bool))
check("hide invalid pid is safe", tc._hide_pid_windows(0) == 0)
check("hide missing pid is safe", tc._hide_pid_windows(1) >= 0)

# Suppressor stops when asked.
stop = threading.Event()
t = threading.Thread(target=tc._window_suppressor, args=(os.getpid(), stop, 0.02), daemon=True)
t.start()
time.sleep(0.05)
stop.set()
t.join(timeout=1.0)
check("suppressor joins", not t.is_alive())

# Tiny local copy only if TeraCopy is installed — otherwise skip.
exe = tc.find_exe()
if exe:
    src_dir = tempfile.mkdtemp(prefix="nebula-tc-src-")
    dst_dir = tempfile.mkdtemp(prefix="nebula-tc-dst-")
    src = os.path.join(src_dir, "probe.bin")
    with open(src, "wb") as fh:
        fh.write(b"nebula-teracopy-probe\n" * 64)
    try:
        out = tc.copy_into(src, dst_dir, log=lambda m: None)
        check("copy_into wrote file", os.path.isfile(out), out)
        check("copy_into size matches",
              os.path.getsize(out) == os.path.getsize(src))
    except Exception as exc:
        check("copy_into", False, str(exc))
    finally:
        for path in (src, os.path.join(dst_dir, "probe.bin")):
            try:
                os.remove(path)
            except OSError:
                pass
        for d in (src_dir, dst_dir):
            try:
                os.rmdir(d)
            except OSError:
                pass
else:
    check("TeraCopy not installed — hide path still tested", True)

failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("%s  %s" % ("PASS" if ok else "FAIL", name))
          + ((" — " + detail) if detail and not ok else ""))
print("%d/%d passed" % (len(results) - len(failed), len(results)))
sys.exit(1 if failed else 0)
