"""Check GitHub Releases for a newer Nebula build, and install it when frozen.

Dev / source clones use Settings → Updates → Save this machine / Load latest.
This module is also for the packaged ``Nebula.exe`` next to the user's config.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from . import __version__
from .paths import APP_DIR

DEFAULT_REPO = "theoriginalcheese/nebula"
# Laptop/desktop Save/Load always uses this branch. No wip shuttle — Anthony
# tracks one place, and leftover cursor/* branches were the whole problem.
SYNC_BRANCH = "main"
USER_AGENT = f"Nebula/{__version__} (+https://github.com/{DEFAULT_REPO})"


def parse_version(text):
    """Turn 'v1.2.3' / '1.2.3-beta' into a comparable tuple of ints."""
    if not text:
        return ()
    cleaned = text.strip().lstrip("vV")
    nums = re.findall(r"\d+", cleaned.split("-", 1)[0])
    return tuple(int(n) for n in nums)


def is_newer(remote, local=__version__):
    a, b = parse_version(remote), parse_version(local)
    if not a:
        return False
    # Pad so 1.2 vs 1.2.0 compares cleanly.
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return a > b


def _api_headers(token=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_latest_release(repo=DEFAULT_REPO, token=None, timeout=15):
    """Return a dict for the latest GitHub release, or raise RuntimeError."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers=_api_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"GitHub HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach GitHub: {e.reason}") from e

    tag = data.get("tag_name") or ""
    assets = data.get("assets") or []
    exe = None
    for asset in assets:
        name = (asset.get("name") or "").lower()
        if name.endswith(".exe") and "nebula" in name:
            exe = asset
            break
    if exe is None:
        for asset in assets:
            if (asset.get("name") or "").lower().endswith(".exe"):
                exe = asset
                break

    return {
        "tag": tag,
        "version": tag.lstrip("vV"),
        "name": data.get("name") or tag,
        "notes": data.get("body") or "",
        "html_url": data.get("html_url") or "",
        "asset_name": (exe or {}).get("name"),
        "asset_url": (exe or {}).get("browser_download_url"),
        "published_at": data.get("published_at") or "",
    }


def check_for_update(repo=DEFAULT_REPO, token=None, local_version=__version__):
    """Compare this install to GitHub.

    Source checkouts compare ``HEAD`` to ``origin/main``. Packaged builds
    still compare Releases.
    """
    if not is_frozen() and source_checkout_root():
        return check_source_sync()
    release = fetch_latest_release(repo=repo, token=token)
    remote = release.get("version") or release.get("tag") or ""
    if not is_newer(remote, local_version):
        return {"status": "current", "release": release, "local": local_version,
                "kind": "release",
                "message": "You're on the latest (%s)." % local_version}
    if not release.get("asset_url"):
        return {"status": "no_asset", "release": release, "local": local_version,
                "kind": "release",
                "message": "%s is on GitHub but has no .exe asset yet." % (
                    release.get("tag") or remote or "?")}
    return {"status": "update", "release": release, "local": local_version,
            "kind": "release",
            "message": "%s is available (you have %s)." % (
                release.get("tag") or remote, local_version)}


def download_update(asset_url, dest_path, token=None, timeout=120):
    """Download a release asset to ``dest_path`` (atomic via .partial)."""
    req = urllib.request.Request(asset_url, headers=_api_headers(token))
    partial = dest_path + ".partial"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(partial, "wb") as out:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
        os.replace(partial, dest_path)
    finally:
        if os.path.exists(partial):
            try:
                os.remove(partial)
            except OSError:
                pass
    return dest_path


def default_download_path(asset_name=None):
    name = asset_name or "Nebula.exe"
    # Don't overwrite the running exe in place — write beside it.
    base, ext = os.path.splitext(name)
    return os.path.join(APP_DIR, f"{base}-update{ext or '.exe'}")


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def source_checkout_root():
    """Repo root when running from a git clone; else None."""
    if is_frozen():
        return None
    if os.path.isdir(os.path.join(APP_DIR, ".git")):
        return APP_DIR
    return None


def _run_git(root, args, timeout=90, rewrite=None):
    import subprocess
    from .silent_proc import resolve_git, run_kwargs

    cmd = list(args)
    if cmd and cmd[0] == "git":
        cmd = [resolve_git()] + list(rewrite or []) + cmd[1:]
    kwargs = {
        "cwd": root,
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }
    kwargs.update(run_kwargs())
    return subprocess.run(cmd, **kwargs)


def _ssh_auth_failed(proc):
    err = (proc.stderr or proc.stdout or "")
    return (
        "Permission denied" in err
        or "Could not read from remote" in err
        or "Host key verification failed" in err
    )


def _https_rewrite(root, timeout=15):
    origin = _run_git(root, ["git", "remote", "get-url", "origin"], timeout)
    url = (origin.stdout or "").strip()
    if not url or url.startswith("https://") or url.startswith("http://"):
        return []
    path = ""
    if url.startswith("git@"):
        _, _, rest = url.partition(":")
        path = rest
    elif url.startswith("ssh://"):
        after = url.split("://", 1)[-1]
        path = after.split("/", 1)[-1] if "/" in after else ""
    path = path.removeprefix("/").removesuffix(".git")
    if "/" not in path:
        path = DEFAULT_REPO
    https = "https://github.com/%s.git" % path
    return ["-c", "url.%s.insteadOf=%s" % (https, url)]


def _fetch_origin(root, timeout=90):
    rewrite = []
    fetch = _run_git(root, ["git", "fetch", "origin"], timeout)
    if fetch.returncode != 0 and _ssh_auth_failed(fetch):
        rewrite = _https_rewrite(root)
        if rewrite:
            fetch = _run_git(
                root, ["git", "fetch", "origin"], timeout, rewrite=rewrite)
    return fetch, rewrite


def _head_oneline(root):
    proc = _run_git(root, ["git", "log", "-1", "--oneline"], 15)
    return (proc.stdout or "").strip()


def _porcelain(root):
    proc = _run_git(root, ["git", "status", "--porcelain"], 15)
    return (proc.stdout or "").strip()


def _rev_parse(root, ref):
    proc = _run_git(
        root, ["git", "rev-parse", "--verify", "--quiet", ref], 15)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _ahead_count(root, a, b):
    proc = _run_git(root, ["git", "rev-list", "--count", "%s..%s" % (a, b)], 15)
    if proc.returncode != 0:
        return 0
    try:
        return int((proc.stdout or "0").strip() or "0")
    except ValueError:
        return 0


def _refresh_version():
    try:
        from . import version as version_mod
        version_mod.git_describe(force=True)
    except Exception:
        pass


def _git_exc_result(exc, head=""):
    import subprocess
    if isinstance(exc, FileNotFoundError):
        return {"ok": False, "message": "git is not on PATH.", "head": head}
    if isinstance(exc, subprocess.TimeoutExpired):
        return {"ok": False, "message": "git timed out.", "head": head}
    return {"ok": False, "message": str(exc), "head": head}


def check_source_sync(root=None, timeout=90):
    from .version import display_version

    root = root or source_checkout_root()
    if not root:
        raise RuntimeError("Not a git checkout.")
    fetch, _rewrite = _fetch_origin(root, timeout)
    if fetch.returncode != 0:
        err = (fetch.stderr or fetch.stdout or "fetch failed").strip()
        raise RuntimeError(err)
    remote = "origin/%s" % SYNC_BRANCH
    ahead = _ahead_count(root, "HEAD", remote) if _rev_parse(root, remote) else 0
    dirty = bool(_porcelain(root))
    local_label = display_version()
    if ahead > 0:
        status = "update"
        message = "GitHub is %d commit%s ahead. Load latest." % (
            ahead, "" if ahead == 1 else "s")
    else:
        status = "current"
        message = "You're on the latest snapshot (%s)." % local_label
        if dirty:
            message = (
                "You're on the latest snapshot (%s) with uncommitted "
                "changes — Save this machine before switching PCs."
                % local_label)
    return {
        "status": status,
        "release": {},
        "local": local_label,
        "message": message,
        "kind": "source",
        "ahead": ahead,
        "head": _rev_parse(root, "HEAD"),
        "dirty": dirty,
    }


def save_source_snapshot(root=None, timeout=90, now=None, host=None):
    """Commit the working tree onto ``main`` and push it."""
    root = root or source_checkout_root()
    if not root:
        return {"ok": False, "message": "Not a git checkout.", "head": ""}
    try:
        current = _run_git(
            root, ["git", "rev-parse", "--abbrev-ref", "HEAD"], 15)
        name = (current.stdout or "").strip() or "HEAD"
        if name != SYNC_BRANCH:
            co = _run_git(root, ["git", "checkout", "-B", SYNC_BRANCH], 30)
            if co.returncode != 0:
                err = (co.stderr or co.stdout or "checkout failed").strip()
                return {
                    "ok": False,
                    "message": "Could not switch to main: %s" % err,
                    "head": _head_oneline(root),
                }

        add = _run_git(root, ["git", "add", "-A"], timeout)
        if add.returncode != 0:
            err = (add.stderr or add.stdout or "git add failed").strip()
            return {"ok": False, "message": err, "head": _head_oneline(root)}
        _run_git(
            root,
            ["git", "rm", "--cached", "-f", "--ignore-unmatch",
             "--", "offload_queue.json"],
            15,
        )

        committed = False
        if _porcelain(root):
            host = host or (
                os.environ.get("COMPUTERNAME")
                or os.environ.get("HOSTNAME")
                or "machine")
            if now is None:
                stamp = time.strftime("%Y-%m-%d %H:%M")
            elif hasattr(now, "strftime"):
                stamp = now.strftime("%Y-%m-%d %H:%M")
            else:
                stamp = str(now)
            msg = "nebula: save %s %s" % (host, stamp)
            commit = _run_git(root, [
                "git",
                "-c", "user.name=Nebula",
                "-c", "user.email=nebula@local",
                "commit", "-m", msg,
            ], timeout)
            if commit.returncode != 0:
                err = (commit.stderr or commit.stdout or "commit failed").strip()
                if "nothing to commit" in err.lower():
                    committed = False
                else:
                    return {"ok": False, "message": err,
                            "head": _head_oneline(root)}
            else:
                committed = True

        push = _run_git(
            root, ["git", "push", "-u", "origin", SYNC_BRANCH], timeout)
        replaced = False
        if push.returncode != 0:
            err = (push.stderr or push.stdout or "push failed").strip()
            rejected = (
                "non-fast-forward" in err
                or "Updates were rejected" in err
                or "failed to push some refs" in err
            )
            if rejected:
                lease = _run_git(
                    root,
                    ["git", "push", "--force-with-lease",
                     "origin", SYNC_BRANCH],
                    timeout,
                )
                if lease.returncode == 0:
                    replaced = True
                else:
                    err2 = (lease.stderr or lease.stdout or err).strip()
                    return {"ok": False, "message": err2,
                            "head": _head_oneline(root)}
            else:
                return {"ok": False, "message": err,
                        "head": _head_oneline(root)}

        _refresh_version()
        head = _head_oneline(root)
        if replaced:
            out_msg = (
                "Saved — replaced the previous GitHub snapshot (%s)." % head)
        elif committed:
            out_msg = "Saved this machine to GitHub (%s)." % head
        else:
            out_msg = "Already saved (%s)." % head
        return {
            "ok": True, "message": out_msg, "head": head,
            "replaced": replaced, "committed": committed,
        }
    except Exception as exc:
        return _git_exc_result(exc, _head_oneline(root) if root else "")


def load_source_snapshot(root=None, timeout=90):
    """Make this checkout match origin/main."""
    root = root or source_checkout_root()
    if not root:
        return {"ok": False, "message": "Not a git checkout.", "head": ""}
    try:
        if _porcelain(root):
            return {
                "ok": False,
                "message": (
                    "Save this machine first or you will lose uncommitted "
                    "work."),
                "head": _head_oneline(root),
            }
        fetch, _rewrite = _fetch_origin(root, timeout)
        if fetch.returncode != 0:
            err = (fetch.stderr or fetch.stdout or "fetch failed").strip()
            return {"ok": False, "message": err, "head": ""}

        remote = "origin/%s" % SYNC_BRANCH
        if not _rev_parse(root, remote):
            return {"ok": False, "message": "No origin/main to load.",
                    "head": ""}
        local_ahead = _ahead_count(root, remote, "HEAD")
        if local_ahead > 0:
            return {
                "ok": False,
                "message": (
                    "This PC has %d unpushed commit%s — Save this machine "
                    "first or you will lose them." % (
                        local_ahead, "" if local_ahead == 1 else "s")),
                "head": _head_oneline(root),
            }
        co = _run_git(
            root, ["git", "checkout", "-B", SYNC_BRANCH, remote], 30)
        if co.returncode != 0:
            err = (co.stderr or co.stdout or "checkout failed").strip()
            return {"ok": False, "message": err, "head": ""}
        _refresh_version()
        head = _head_oneline(root)
        return {
            "ok": True,
            "message": (
                "Loaded latest snapshot (%s). Restart Nebula to load it."
                % head),
            "head": head,
        }
    except Exception as exc:
        return _git_exc_result(exc)


def pull_source_update(root=None, timeout=90, branch=None):
    """Load origin/main. ``branch`` is ignored."""
    return load_source_snapshot(root=root, timeout=timeout)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    action = (argv[0] if argv else "load").strip().lower()
    if action in ("save", "push"):
        result = save_source_snapshot()
    elif action in ("load", "pull"):
        result = load_source_snapshot()
    elif action == "check":
        result = check_for_update()
        print(result.get("message") or "")
        return 0 if result.get("status") == "current" else 1
    else:
        print("usage: python -m obsauto.updater save|load|check")
        return 2
    print(result.get("message") or "")
    return 0 if result.get("ok") else 1


def install_and_relaunch(update_path, target_path=None, pid=None):
    """Replace the running packaged exe after this process exits, then relaunch.

    Writes a tiny helper beside the exe, detaches it, and returns. The caller
    must quit Nebula so the file lock drops. Windows cannot overwrite a running
    image in place. Uses pythonw (not cmd) so no console window flashes.
    """
    import subprocess
    import textwrap

    if not is_frozen():
        raise RuntimeError("install_and_relaunch is for packaged builds only")
    update_path = os.path.abspath(update_path)
    if not os.path.isfile(update_path):
        raise RuntimeError("Update file missing: %s" % update_path)
    target_path = os.path.abspath(target_path or sys.executable)
    pid = int(pid or os.getpid())
    work = os.path.dirname(target_path)
    helper = os.path.join(work, "_nebula_apply_update.py")

    script = textwrap.dedent("""\
        import os, sys, time, shutil, subprocess
        target, new, pid = sys.argv[1], sys.argv[2], int(sys.argv[3])
        # Wait until the old process is gone (file lock released).
        for _ in range(120):
            try:
                import ctypes
                SYNCHRONIZE = 0x00100000
                h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if h:
                    ctypes.windll.kernel32.CloseHandle(h)
                    time.sleep(0.5)
                    continue
            except Exception:
                pass
            break
        else:
            sys.exit(1)
        for _ in range(20):
            try:
                shutil.copyfile(new, target)
                break
            except OSError:
                time.sleep(0.5)
        else:
            sys.exit(2)
        try:
            os.remove(new)
        except OSError:
            pass
        flags = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP
        subprocess.Popen([target], cwd=os.path.dirname(target),
                         close_fds=True, creationflags=flags)
        try:
            os.remove(__file__)
        except OSError:
            pass
        """)
    with open(helper, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)

    # Prefer pythonw.exe next to the frozen bootloader's embedded python,
    # otherwise the same interpreter that packed us (dev) / sys.executable.
    pyw = sys.executable
    if pyw.lower().endswith("python.exe"):
        candidate = pyw[:-len("python.exe")] + "pythonw.exe"
        if os.path.isfile(candidate):
            pyw = candidate

    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        [pyw, helper, target_path, update_path, str(pid)],
        cwd=work,
        close_fds=True,
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return helper


if __name__ == "__main__":
    raise SystemExit(main())
