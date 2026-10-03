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

# Packaged update copies this exe aside and starts it with --apply-update
# (frozen path only — we exercise the launch shape without a real window).
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
        check("updater copy written", os.path.isfile(helper_path), helper_path)
        check("updater copy is an exe", helper_path.endswith("_nebula_updater.exe"),
              helper_path)
        check("updater spawned", popen.called)
        spawned = popen.call_args[0][0]
        check("spawn is the updater exe", spawned[0] == helper_path, spawned)
        check("spawn asks for the update window",
              "--apply-update" in spawned and "--source" in spawned
              and src in spawned, spawned)
        check("spawn waits on the given pid",
              "--pid" in spawned and spawned[spawned.index("--pid") + 1] == "1",
              spawned)
        env = popen.call_args.kwargs.get("env") or {}
        check("updater resets the pyinstaller unpack dir",
              env.get("PYINSTALLER_RESET_ENVIRONMENT") == "1", env)
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

# The swap itself, with no window: a dead pid, and a cancel while the app
# is still open.
import shutil
import subprocess

from obsauto.update_apply import apply_downloaded_exe

swap_dir = tempfile.mkdtemp(prefix="nebula-apply-")
try:
    new_exe = os.path.join(swap_dir, "Nebula-update.exe")
    old_exe = os.path.join(swap_dir, "Nebula.exe")
    with open(new_exe, "wb") as fh:
        fh.write(b"updated-bytes")
    with open(old_exe, "wb") as fh:
        fh.write(b"old-bytes")
    stages = []
    apply_downloaded_exe(
        old_exe, new_exe, pid=0, launch=False,
        on_status=lambda text, pct: stages.append((text, pct)))
    with open(old_exe, "rb") as fh:
        swapped = fh.read()
    check("swap writes the download", swapped == b"updated-bytes", swapped)
    check("swap removes the download", not os.path.exists(new_exe))
    check("swap reports the real steps",
          [text for text, _pct in stages][:4] == [
              "Waiting for Nebula to close…",
              "Replacing Nebula…",
              "Verifying the new file…",
              "Starting Nebula…",
          ], stages)
    check("swap leaves no staged copy", not os.path.exists(old_exe + ".new"))

    kept_bytes = open(old_exe, "rb").read()
    again = os.path.join(swap_dir, "again.exe")
    with open(again, "wb") as fh:
        fh.write(b"another-download")
    with mock.patch("obsauto.update_apply.os.replace", side_effect=OSError("denied")), \
         mock.patch("obsauto.update_apply._spawn") as spawn:
        replace_error = ""
        try:
            apply_downloaded_exe(old_exe, again, pid=0, launch=True)
        except RuntimeError as exc:
            replace_error = str(exc)
    with open(old_exe, "rb") as fh:
        after = fh.read()
    check("failed replace keeps the installed exe",
          after == kept_bytes and "not changed" in replace_error
          and "opening again" in replace_error, replace_error or after)
    check("failed replace opens Nebula again", spawn.called)
    check("failed replace removes the staged copy",
          not os.path.exists(old_exe + ".new"))

    kept = os.path.join(swap_dir, "kept.exe")
    fresh = os.path.join(swap_dir, "fresh.exe")
    with open(kept, "wb") as fh:
        fh.write(b"keep-me")
    with open(fresh, "wb") as fh:
        fh.write(b"do-not-copy")
    cancel = __import__("threading").Event()

    def _cancel_on_wait(text, _pct):
        if text.startswith("Waiting"):
            cancel.set()

    raised = ""
    try:
        apply_downloaded_exe(
            kept, fresh, pid=os.getpid(), launch=False,
            on_status=_cancel_on_wait, cancel=cancel)
    except RuntimeError as exc:
        raised = str(exc)
    with open(kept, "rb") as fh:
        still = fh.read()
    check("cancel leaves the exe alone", still == b"keep-me" and "cancelled" in raised,
          raised or still)
    check("cancel keeps the download", os.path.isfile(fresh))

    # A cancel while the old process is still alive must not start another
    # copy. That copy loses the mutex, focuses the one that's quitting, and
    # exits — so the user is left with nothing.
    live = os.path.join(swap_dir, "live.exe")
    pending = os.path.join(swap_dir, "pending.exe")
    with open(live, "wb") as fh:
        fh.write(b"still-running")
    with open(pending, "wb") as fh:
        fh.write(b"do-not-install")
    early = __import__("threading").Event()
    early.set()
    spawned_early = {"called": False}

    def _no_spawn(_target):
        spawned_early["called"] = True

    early_error = ""
    with mock.patch("obsauto.update_apply.pid_alive", return_value=True), \
         mock.patch("obsauto.update_apply.time.sleep"), \
         mock.patch("obsauto.update_apply._spawn", side_effect=_no_spawn):
        try:
            apply_downloaded_exe(
                live, pending, pid=4242, launch=True, cancel=early)
        except RuntimeError as exc:
            early_error = str(exc)
    with open(live, "rb") as fh:
        live_bytes = fh.read()
    check("cancel while running does not relaunch",
          live_bytes == b"still-running" and not spawned_early["called"]
          and "cancelled" in early_error and "opening again" not in early_error,
          early_error)

    short = os.path.join(swap_dir, "short.exe")
    installed = os.path.join(swap_dir, "installed.exe")
    with open(short, "wb") as fh:
        fh.write(b"tiny")
    with open(installed, "wb") as fh:
        fh.write(b"good-exe")
    size_error = ""
    try:
        apply_downloaded_exe(
            installed, short, pid=0, launch=False, expected_size=50)
    except RuntimeError as exc:
        size_error = str(exc)
    with open(installed, "rb") as fh:
        kept_install = fh.read()
    check("short download is not installed",
          kept_install == b"good-exe" and "wrong size" in size_error, size_error)

    # Both start attempts fail after the swap. The error has to stay
    # _ReplacedNotStarted so the dialog does not claim the exe was untouched.
    from obsauto.update_apply import _ReplacedNotStarted
    swapped_exe = os.path.join(swap_dir, "swapped.exe")
    new_body = os.path.join(swap_dir, "new-body.exe")
    with open(swapped_exe, "wb") as fh:
        fh.write(b"old-body")
    with open(new_body, "wb") as fh:
        fh.write(b"new-body")
    start_error = None
    with mock.patch("obsauto.update_apply._spawn", side_effect=OSError("blocked")):
        try:
            apply_downloaded_exe(swapped_exe, new_body, pid=0, launch=True)
        except _ReplacedNotStarted as exc:
            start_error = exc
        except Exception as exc:
            start_error = exc
    with open(swapped_exe, "rb") as fh:
        swapped_body = fh.read()
    check("failed start after replace stays honest",
          isinstance(start_error, _ReplacedNotStarted) and swapped_body == b"new-body",
          type(start_error).__name__ if start_error else swapped_body)
finally:
    shutil.rmtree(swap_dir, ignore_errors=True)

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The dialog shows the design's stages. Verifying stays on replacing:
# the bar has three segments, and the hash check is part of that step.
from obsauto.update_apply import stage_for_status

check("stage waiting",
      stage_for_status("Waiting for Nebula to close…") == "waiting")
check("stage replacing",
      stage_for_status("Replacing Nebula…") == "replacing")
check("stage verify is still replacing",
      stage_for_status("Verifying the new file…") == "replacing")
check("stage starting",
      stage_for_status("Starting Nebula…") == "starting")
check("stage cancelled",
      stage_for_status(
          "Update cancelled. Nebula was not changed.") == "cancelled")
check("stage failed",
      stage_for_status(
          "Couldn't replace Nebula.exe (denied). "
          "The installed copy was not changed.") == "failed")

_page = os.path.join(_root, "spike", "web", "update.html")
_html = open(_page, encoding="utf-8").read()
for _needle in (
        "Waiting for Nebula to close…",
        "Replacing Nebula.exe…",
        "Starting Nebula…",
        "Updated. Opening Nebula…",
        "Couldn\u2019t replace Nebula.exe.",
        "Update cancelled.",
        "The installed copy was not changed.",
        "Updating Nebula…",
        "@keyframes uw-drift-a",
        "@keyframes uw-drift-b",
        "@keyframes uw-drift-c",
        "@keyframes uw-wind",
        "@keyframes uw-twinkle",
        "@keyframes uw-band",
        "@keyframes uw-breathe",
        "@keyframes uw-orbit",
        "@keyframes uw-sweep",
        "@keyframes uw-dot",
        "@keyframes uw-in",
        "700ms cubic-bezier(.32, .72, 0, 1)",
        "600ms cubic-bezier(.32, .72, 0, 1)",
        "500ms cubic-bezier(.32, .72, 0, 1)",
        "420ms cubic-bezier(.32, .72, 0, 1)",
        "animation-play-state: paused !important",
        "#FF5C7A",
):
    check("update page has %s" % _needle[:32], _needle in _html, _needle)
_spec = open(os.path.join(_root, "nebula-v4.spec"), encoding="utf-8").read()
check("update page is in the v4 bundle", '"update.html"' in _spec)

# The window has to actually come up, swap, and close. A subprocess so a
# stuck message pump cannot hang this file.
try:
    _win = subprocess.run(
        [sys.executable, "-c", """
import os, sys, tempfile, shutil
sys.path.insert(0, %r)
from obsauto.update_apply import run_apply_window
d = tempfile.mkdtemp(prefix="nebula-win-")
src = os.path.join(d, "Nebula-update.exe")
dst = os.path.join(d, "Nebula.exe")
open(src, "wb").write(b"NEW-BYTES")
open(dst, "wb").write(b"OLD")
try:
    run_apply_window(dst, src, pid=0, launch=False)
    got = open(dst, "rb").read()
    assert got == b"NEW-BYTES", got
    assert not os.path.exists(src)
    print("WINDOW_OK")
finally:
    shutil.rmtree(d, ignore_errors=True)
""" % _root],
        capture_output=True, text=True, timeout=20)
    check("update window swaps and closes",
          _win.returncode == 0 and "WINDOW_OK" in _win.stdout
          and "WINDOW_READY" in _win.stdout,
          (_win.stderr or _win.stdout or "")[-500:])
except subprocess.TimeoutExpired:
    check("update window swaps and closes", False, "timed out")

with mock.patch.object(sys, "argv", [sys.argv[0], "--apply-update"]):
    from spike.app import main as _spike_main
    check("apply-update exits before the app", _spike_main() == 0)


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
        check("waiter shows a copy that already holds the mutex",
              "Nebula.SingleInstance" in _src and "Nebula.Wake" in _src, "")
        os.remove(_waiter)
finally:
    _subprocess_mod.Popen = _real_popen

# A short body must not be renamed onto the download path.
import io
_short_dest = os.path.join(tempfile.gettempdir(), "nebula-short-download.exe")


class _ShortBody:
    headers = {"Content-Length": "8"}

    def __init__(self):
        self._buf = io.BytesIO(b"abcd")

    def read(self, _n):
        return self._buf.read(_n)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


try:
    if os.path.exists(_short_dest):
        os.remove(_short_dest)
    with mock.patch("urllib.request.urlopen", return_value=_ShortBody()):
        _short_error = ""
        try:
            updater_mod.download_update("http://example.invalid/Nebula.exe", _short_dest)
        except RuntimeError as exc:
            _short_error = str(exc)
    check("short download is refused",
          "stopped early" in _short_error and not os.path.exists(_short_dest),
          _short_error)
except Exception as exc:
    check("short download is refused", False, str(exc))

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
