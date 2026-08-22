"""Version compare helpers for the GitHub Releases updater.

    python tests/test_updater.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.updater import is_newer, parse_version
from obsauto import updater as updater_mod

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
check("tag ahead of release", is_newer("4.0.1", "4.0.0"))
check("ssh auth detects publickey", updater_mod._ssh_auth_failed_text(
    "git@github.com: Permission denied (publickey)."))
check("ssh auth ignores unrelated", not updater_mod._ssh_auth_failed_text(
    "Already up to date."))

# install helper writes a wait-copy-relaunch script (frozen path only — we
# exercise the file shape without claiming to be frozen).
import tempfile
from unittest import mock

# source_checkout_root accepts a .git file (worktree)
wt = tempfile.mkdtemp(prefix="nebula-wt-")
open(os.path.join(wt, ".git"), "w", encoding="utf-8").write("gitdir: /tmp/x\n")
with mock.patch.object(updater_mod, "is_frozen", return_value=False), \
     mock.patch.object(updater_mod, "APP_DIR", wt):
    check("worktree .git file is a checkout",
          updater_mod.source_checkout_root() == wt)

tmpdir = tempfile.mkdtemp(prefix="nebula-upd-")
src = os.path.join(tmpdir, "Nebula-update.exe")
dst = os.path.join(tmpdir, "Nebula.exe")
open(src, "wb").write(b"new")
open(dst, "wb").write(b"old")
helper_path = None
try:
    with mock.patch.object(updater_mod, "is_frozen", return_value=True), \
         mock.patch.object(updater_mod.sys, "executable", dst), \
         mock.patch("subprocess.Popen") as popen:
        helper_path = updater_mod.install_and_relaunch(src, target_path=dst, pid=1)
        check("helper written", os.path.isfile(helper_path), helper_path)
        check("helper is python", helper_path.endswith(".py"), helper_path)
        body = open(helper_path, encoding="utf-8").read()
        check("helper waits on pid", "OpenProcess" in body)
        check("helper copies update", "shutil.copyfile" in body)
        check("helper relaunches", "Popen([target]" in body or "Popen([target," in body)
        check("helper spawned", popen.called)
except Exception as exc:
    check("install_and_relaunch", False, str(exc))
finally:
    for path in (src, dst, helper_path):
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
