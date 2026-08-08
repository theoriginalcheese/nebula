"""Check GitHub Releases for a newer Nebula build, and install it when frozen.

Dev / source clones use ``scripts/update-from-github.ps1`` (git pull) instead —
this module is for the packaged ``Nebula.exe`` next to the user's config.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

from . import __version__
from .paths import APP_DIR

DEFAULT_REPO = "theoriginalcheese/nebula"
# Source "Pull from GitHub" always tracks this branch — feature branches
# staying checked out was why Updates said "up to date" after a desktop push.
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
    """Compare local version to the latest release.

    Returns ``{"status": "update"|"current"|"no_asset", "release": {...}, ...}``.
    """
    release = fetch_latest_release(repo=repo, token=token)
    remote = release.get("version") or release.get("tag") or ""
    if not is_newer(remote, local_version):
        return {"status": "current", "release": release, "local": local_version}
    if not release.get("asset_url"):
        return {"status": "no_asset", "release": release, "local": local_version}
    return {"status": "update", "release": release, "local": local_version}


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
    # APP_DIR in dev is the package parent (repo root).
    if os.path.isdir(os.path.join(APP_DIR, ".git")):
        return APP_DIR
    return None


def pull_source_update(root=None, timeout=90, branch=None):
    """Fetch and fast-forward the sync branch (``main`` by default).

    Always targets :data:`SYNC_BRANCH`, not whatever feature branch happens to
    be checked out — that mismatch is what made Updates claim "up to date"
    after work landed on another branch.

    Returns ``{"ok": bool, "message": str, "head": str}``.
    """
    import subprocess

    root = root or source_checkout_root()
    if not root:
        return {"ok": False, "message": "Not a git checkout.", "head": ""}
    sync = (branch or SYNC_BRANCH or "main").strip() or "main"

    def run(args, t=timeout):
        from .silent_proc import resolve_git, run_kwargs
        # Rewrite bare "git" to the non-flashing binary (Git\cmd\git.exe
        # re-execs and briefly pops a console under pythonw).
        if args and args[0] == "git":
            args = [resolve_git()] + list(args[1:])
        kwargs = {
            "cwd": root,
            "capture_output": True,
            "text": True,
            "timeout": t,
        }
        kwargs.update(run_kwargs())
        return subprocess.run(args, **kwargs)

    def ssh_auth_failed(proc):
        err = (proc.stderr or proc.stdout or "")
        return (
            "Permission denied" in err
            or "Could not read from remote" in err
            or "Host key verification failed" in err
        )

    def https_rewrite_args():
        """Map whatever SSH origin URL we have onto HTTPS for public fetch.

        Remotes are often ``git@github.com-alias:owner/repo.git`` (custom SSH
        host), so a hard-coded ``git@github.com:`` insteadOf does nothing.
        """
        origin = run(["git", "remote", "get-url", "origin"], t=15)
        url = (origin.stdout or "").strip()
        if not url or url.startswith("https://") or url.startswith("http://"):
            return []
        # git@host:owner/repo.git  OR  ssh://git@host/owner/repo.git
        path = ""
        if url.startswith("git@"):
            # git@host:path
            _, _, rest = url.partition(":")
            path = rest
        elif url.startswith("ssh://"):
            # ssh://git@host/path
            after = url.split("://", 1)[-1]
            path = after.split("/", 1)[-1] if "/" in after else ""
        path = path.removeprefix("/").removesuffix(".git")
        if "/" not in path:
            path = DEFAULT_REPO
        https = "https://github.com/%s.git" % path
        return ["-c", "url.%s.insteadOf=%s" % (https, url)]

    try:
        rewrite = []
        fetch = run(["git", "fetch", "origin"])
        if fetch.returncode != 0 and ssh_auth_failed(fetch):
            # Dev machines often have SSH remotes without a key loaded.
            rewrite = https_rewrite_args()
            if rewrite:
                fetch = run(["git"] + rewrite + ["fetch", "origin"])
        if fetch.returncode != 0:
            err = (fetch.stderr or fetch.stdout or "fetch failed").strip()
            return {"ok": False, "message": err, "head": ""}

        current = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], t=15)
        current_name = (current.stdout or "").strip() or "HEAD"
        switched = False
        if current_name != sync:
            # Move onto the sync branch so the working tree matches what Pull
            # claims to update. Refuse if checkout is blocked by local edits.
            co = run(["git", "checkout", sync], t=30)
            if co.returncode != 0:
                err = (co.stderr or co.stdout or "checkout failed").strip()
                return {
                    "ok": False,
                    "message": (
                        "Pull syncs %s, but checkout failed (you are on %s): %s"
                        % (sync, current_name, err)
                    ),
                    "head": "",
                }
            switched = True

        pull_cmd = ["git"] + rewrite + ["pull", "--ff-only", "origin", sync]
        pull = run(pull_cmd)
        if pull.returncode != 0 and ssh_auth_failed(pull) and not rewrite:
            rewrite = https_rewrite_args()
            if rewrite:
                pull = run(["git"] + rewrite + [
                    "pull", "--ff-only", "origin", sync])
        head = run(["git", "log", "-1", "--oneline"], t=15)
        head_line = (head.stdout or "").strip()
        if pull.returncode != 0:
            err = (pull.stderr or pull.stdout or "pull failed").strip()
            return {"ok": False, "message": err, "head": head_line}
        out = (pull.stdout or "").strip()
        if "Already up to date" in out or "Already up-to-date" in out:
            if switched:
                msg = "Switched to %s — already up to date (%s)." % (
                    sync, head_line or sync)
            else:
                msg = "Already up to date on %s (%s)." % (
                    sync, head_line or sync)
        else:
            prefix = ("Switched to %s and updated" % sync
                      if switched else "Updated")
            msg = "%s to %s. Restart Nebula to load it." % (
                prefix, head_line or sync)
        # Refresh the version badge cache after a successful pull.
        try:
            from . import version as version_mod
            version_mod.git_describe(force=True)
        except Exception:
            pass
        return {"ok": True, "message": msg, "head": head_line}
    except FileNotFoundError:
        return {"ok": False, "message": "git is not on PATH.", "head": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "git timed out.", "head": ""}
    except Exception as exc:
        return {"ok": False, "message": str(exc), "head": ""}


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
