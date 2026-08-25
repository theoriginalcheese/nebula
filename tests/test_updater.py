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


# --- Save / Load on a throwaway pair of clones --------------------------------
import shutil
import subprocess
import tempfile as _tempfile

from obsauto.updater import (
    SYNC_BRANCH, load_source_snapshot, save_source_snapshot,
)


def _git(cwd, *args, check=True):
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(
            (proc.stderr or proc.stdout or "git failed").strip()
            or "git %s" % " ".join(args))
    return proc


work = _tempfile.mkdtemp(prefix="nebula-sync-")
bare = os.path.join(work, "origin.git")
clone_a = os.path.join(work, "a")
clone_b = os.path.join(work, "b")
try:
    os.makedirs(bare)
    _git(bare, "init", "--bare", "-b", SYNC_BRANCH)
    seed = os.path.join(work, "seed")
    os.makedirs(seed)
    _git(seed, "init", "-b", SYNC_BRANCH)
    _git(seed, "config", "user.email", "nebula-test@local")
    _git(seed, "config", "user.name", "Nebula Test")
    with open(os.path.join(seed, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("seed\n")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-m", "seed")
    _git(seed, "remote", "add", "origin", bare)
    _git(seed, "push", "-u", "origin", SYNC_BRANCH)

    subprocess.run(
        ["git", "clone", bare, clone_a], check=True,
        capture_output=True, text=True)
    subprocess.run(
        ["git", "clone", bare, clone_b], check=True,
        capture_output=True, text=True)
    for clone in (clone_a, clone_b):
        _git(clone, "config", "user.email", "nebula-test@local")
        _git(clone, "config", "user.name", "Nebula Test")

    marker = os.path.join(clone_a, "handoff.txt")
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write("from A\n")
    queue = os.path.join(clone_a, "offload_queue.json")
    with open(queue, "w", encoding="utf-8") as fh:
        fh.write("{}\n")
    ignore = os.path.join(clone_a, ".gitignore")
    with open(ignore, "w", encoding="utf-8") as fh:
        fh.write("offload_queue.json\n")
    # Pretend the queue was tracked (the bug Save has to kill).
    _git(clone_a, "add", "-f", "offload_queue.json")
    _git(clone_a, "commit", "-m", "track queue by mistake")

    result = save_source_snapshot(root=clone_a, host="TEST-PC", now="2026-08-23 02:00")
    check("save ok", result.get("ok"), result.get("message"))
    check("save commits onto main",
          _git(clone_a, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
          == SYNC_BRANCH)
    check("save does not keep queue tracked",
          "offload_queue.json" not in _git(clone_a, "ls-files").stdout)
    check("save committed the handoff file",
          os.path.isfile(os.path.join(clone_a, "handoff.txt")))

    dirty = os.path.join(clone_b, "scratch.txt")
    with open(dirty, "w", encoding="utf-8") as fh:
        fh.write("nope\n")
    refused = load_source_snapshot(root=clone_b)
    check("load refuses dirty", not refused.get("ok"), refused.get("message"))
    check("load dirty names Save",
          "Save this machine" in (refused.get("message") or ""))
    os.remove(dirty)

    loaded = load_source_snapshot(root=clone_b)
    check("load ok on clean clone", loaded.get("ok"), loaded.get("message"))
    got = os.path.join(clone_b, "handoff.txt")
    check("second clone received the file",
          os.path.isfile(got) and open(got, encoding="utf-8").read() == "from A\n")
    check("second clone did not receive the queue",
          not os.path.isfile(os.path.join(clone_b, "offload_queue.json"))
          or "offload_queue.json" not in _git(clone_b, "ls-files").stdout)
except Exception as exc:
    check("save/load temp-repo", False, str(exc))
finally:
    shutil.rmtree(work, ignore_errors=True)


# --- relaunch_source: waiter goes to TEMP, argv mirrors the shortcut ---------
import tempfile
import subprocess as _subprocess_mod


class _FakePopen:
    calls = []

    def __init__(self, *a, **k):
        _FakePopen.calls.append((a, k))


# relaunch_source does its own ``import subprocess``, which yields the same
# module object - patching the attribute here reaches it either way.
_real_popen = _subprocess_mod.Popen
_subprocess_mod.Popen = _FakePopen
try:
    _fake_root = tempfile.mkdtemp(prefix="nebula_relaunch_test_")

    # Frozen builds must refuse (is_frozen probes sys.frozen).
    _frozen_flag = getattr(sys, "frozen", None)
    sys.frozen = True
    try:
        r = updater_mod.relaunch_source(root=_fake_root)
    finally:
        if _frozen_flag is None:
            del sys.frozen
        else:
            sys.frozen = _frozen_flag
    check("relaunch refuses frozen builds", not r.get("ok"), r)

    r = updater_mod.relaunch_source(root=os.path.join(_fake_root, "nope"))
    check("relaunch refuses non-checkout", not r.get("ok"), r)

    # Happy path: entry exists, Popen gets waiter + shortcut argv.
    os.makedirs(os.path.join(_fake_root, "spike"), exist_ok=True)
    _entry = os.path.join(_fake_root, "spike", "app.py")
    with open(_entry, "w", encoding="utf-8") as fh:
        fh.write("# entry stub\n")
    _FakePopen.calls.clear()
    r = updater_mod.relaunch_source(root=_fake_root, pid=4321)
    check("relaunch happy path ok", bool(r.get("ok")), r)
    _argv = list(_FakePopen.calls[0][0][0]) if _FakePopen.calls else []
    check("waiter spawned with pyw+waiter+pid+pyw+entry+root",
          len(_argv) == 6 and _argv[1].endswith("_nebula_relaunch.py")
          and _argv[2] == "4321" and _argv[4] == _entry
          and _argv[5] == _fake_root, _argv)
    _waiter = _argv[1] if len(_argv) > 1 else ""
    check("waiter lives in TEMP, not the repo",
          bool(_waiter) and
          os.path.dirname(os.path.abspath(_waiter)) ==
          os.path.abspath(tempfile.gettempdir()), _waiter)
    if _waiter and os.path.isfile(_waiter):
        with open(_waiter, encoding="utf-8") as fh:
            _src = fh.read()
        check("waiter waits on the given pid", "int(pid)" in _src, "")
        check("waiter passes --show like the Start Menu shortcut",
              '"--show"' in _src, "")
        os.remove(_waiter)
finally:
    _subprocess_mod.Popen = _real_popen


failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
