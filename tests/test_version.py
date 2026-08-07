"""Version display helpers.

    python tests/test_version.py
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import version as ver

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


check("release is semver", bool(re_match := __import__("re").match(
    r"^\d+\.\d+\.\d+$", ver.__version__)), ver.__version__)
check("bump target is 4.x", ver.__version__.startswith("4."), ver.__version__)

with mock.patch.object(ver, "is_frozen", return_value=True):
    info = ver.version_info()
    check("frozen display = release", info["display"] == ver.__version__)
    check("frozen channel release", info["channel"] == "release")

with mock.patch.object(ver, "is_frozen", return_value=False), \
     mock.patch.object(ver, "git_describe", return_value="v4.0.0-8-g2af435c"):
    info = ver.version_info()
    check("ahead shows +N", info["display"] == "4.0.0+8", info["display"])
    check("source channel", info["channel"] == "source")

with mock.patch.object(ver, "is_frozen", return_value=False), \
     mock.patch.object(ver, "git_describe", return_value="v4.0.0"):
    info = ver.version_info()
    check("on tag is clean release label", info["display"] == "4.0.0", info["display"])

with mock.patch.object(ver, "is_frozen", return_value=False), \
     mock.patch.object(ver, "git_describe", return_value="v4.0.0-3-gabcdef-dirty"):
    info = ver.version_info()
    check("dirty still shows +N", info["display"] == "4.0.0+3", info["display"])
    check("dirty mentioned in detail", "uncommitted" in info["detail"])

with mock.patch.object(ver, "is_frozen", return_value=False), \
     mock.patch.object(ver, "git_describe", return_value=""):
    info = ver.version_info()
    check("no git shows ·dev", info["display"].endswith("·dev"), info["display"])

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
