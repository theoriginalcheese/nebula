"""Version compare helpers for the GitHub Releases updater.

    python tests/test_updater.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.updater import is_newer, parse_version

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


check("parse plain", parse_version("0.9.3") == (0, 9, 3))
check("parse v-prefix", parse_version("v1.2.0") == (1, 2, 0))
check("newer patch", is_newer("0.9.3", "0.9.2"))
check("not older", not is_newer("0.9.1", "0.9.2"))
check("equal not newer", not is_newer("0.9.2", "0.9.2"))
check("longer remote", is_newer("1.0.1", "1.0"))
check("empty remote", not is_newer("", "0.9.2"))

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
