"""Nebula updates: GitHub Releases (frozen) + source sync (git checkout).

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


def _ssh_auth_failed_text(err):
    err = err or ""
    needles = (
        "Permission denied",
        "Could not read from remote",
        "Host key verification failed",
        "Authentication failed",
        "publickey",
        "Could not resolve hostname",
        "Repository not found",
        "ERROR: Repository not found",
    )
    return any(n in err for n in needles)


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


def _fetch_latest_release_info(repo=DEFAULT_REPO, token=None, timeout=15):
    """Fetch /releases/latest, return (tag, release_dict) or (None, None) on 404."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"

    def once(tok):
        req = urllib.request.Request(url, headers=_api_headers(tok))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("tag_name") or "", data

    try:
        return once(token)
    except urllib.error.HTTPError as e:
        # Bad/expired local token must not break public Checks — retry anonymous.
        if e.code in (401, 403) and token:
            try:
                return once(None)
            except Exception:
                pass
        if e.code == 404:
            return None, None
        body = e.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"GitHub HTTP {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach GitHub: {e.reason}") from e


def _fetch_latest_tag(repo=DEFAULT_REPO, token=None, timeout=15):
    """Highest semver tag from git/refs/tags, or None if unavailable.

    Soft-fails on network/404 so a tags blip does not break Checks when
    /releases/latest already succeeded. 401/403 with a token retries anonymous.
    """
    url = f"https://api.github.com/repos/{repo}/git/refs/tags"

    def once(tok):
        req = urllib.request.Request(url, headers=_api_headers(tok))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        refs = once(token)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) and token:
            try:
                refs = once(None)
            except Exception:
                return None
        else:
            return None
    except (urllib.error.URLError, ValueError, TypeError):
        return None
    # Single-tag repos return one object; multi-tag return a list.
    if isinstance(refs, dict):
        refs = [refs]
    if not isinstance(refs, list):
        return None
    versions = []
    for ref in refs:
        ref_name = (ref or {}).get("ref", "")
        if not ref_name.startswith("refs/tags/"):
            continue
        tag = ref_name[len("refs/tags/"):]
        ver = parse_version(tag)
        if ver:
            versions.append((tag, ver))
    if not versions:
        return None
    versions.sort(key=lambda x: x[1], reverse=True)
    return versions[0][0]


def fetch_latest_release(repo=DEFAULT_REPO, token=None, timeout=15):
    """Return a dict for the newest GitHub release *or* semver tag.

    Prefer /releases/latest (has notes + assets). If a higher semver **tag**
    exists without a published Release yet (e.g. ``v4.0.1`` tag, only
    ``v4.0.0`` Release), surface that tag so the UI does not lie "latest".
    """
    release_tag, release_data = _fetch_latest_release_info(
        repo=repo, token=token, timeout=timeout)
    latest_tag = _fetch_latest_tag(repo=repo, token=token, timeout=timeout)

    if not release_tag and not latest_tag:
        raise RuntimeError("No releases or tags found on GitHub")

    data = release_data or {"tag_name": "", "assets": []}
    tag_only = False
    if latest_tag and parse_version(latest_tag) > parse_version(release_tag or ""):
        tag_only = True
        data = {
            "tag_name": latest_tag,
            "name": latest_tag,
            "body": "",
            "html_url": f"https://github.com/{repo}/releases/tag/{latest_tag}",
            "assets": [],
            "published_at": "",
        }

    tag = data.get("tag_name") or release_tag or latest_tag or ""
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

    html_url = data.get("html_url") or ""
    if not html_url and tag:
        html_url = (
            f"https://github.com/{repo}/releases/tag/{tag}"
            if tag_only or not release_data
            else f"https://github.com/{repo}/releases/latest"
        )

    return {
        "tag": tag,
        "version": tag.lstrip("vV"),
        "name": data.get("name") or tag,
        "notes": data.get("body") or "",
        "html_url": html_url,
        "asset_name": (exe or {}).get("name"),
        "asset_url": (exe or {}).get("browser_download_url"),
        "published_at": data.get("published_at") or "",
        "tag_only": tag_only,
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
    # APP_DIR in dev is the package parent (repo root). Worktrees use a
    # ``.git`` *file* pointing at the common dir — still a checkout.
    git_meta = os.path.join(APP_DIR, ".git")
    if os.path.isdir(git_meta) or os.path.isfile(git_meta):
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


def sync_source_checkout(root=None, timeout=90, branch=None, do_push=True):
    """Two-way sync with ``origin``/``SYNC_BRANCH`` when the tree is clean.

    1. Fetch
    2. Refuse if local edits (porcelain non-empty) — never clobber WIP
    3. Fast-forward pull if behind
    4. Push if ahead (and ``do_push``)
    5. Refuse if diverged (needs a real merge)

    Returns ``{"ok", "message", "head", "pulled", "pushed", "skipped"}``.
    """
    import subprocess

    root = root or source_checkout_root()
    empty = {
        "ok": False, "message": "Not a git checkout.", "head": "",
        "pulled": False, "pushed": False, "skipped": False,
    }
    if not root:
        return empty
    sync = (branch or SYNC_BRANCH or "main").strip() or "main"

    def run(args, t=timeout):
        from .silent_proc import resolve_git, run_kwargs
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
        return _ssh_auth_failed_text(proc.stderr or proc.stdout or "")

    def https_rewrite_args():
        origin = run(["git", "remote", "get-url", "origin"], t=15)
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
            return []
        https = "https://github.com/%s.git" % path
        return ["-c", "url.%s.insteadOf=%s" % (https, url)]

    try:
        rewrite = []
        fetch = run(["git", "fetch", "origin"])
        if fetch.returncode != 0 and ssh_auth_failed(fetch):
            rewrite = https_rewrite_args()
            if rewrite:
                fetch = run(["git"] + rewrite + ["fetch", "origin"])
        if fetch.returncode != 0:
            err = (fetch.stderr or fetch.stdout or "fetch failed").strip()
            return {
                "ok": False, "message": err, "head": "",
                "pulled": False, "pushed": False, "skipped": False,
            }

        dirty = run(["git", "status", "--porcelain"], t=15)
        if (dirty.stdout or "").strip():
            head = run(["git", "log", "-1", "--oneline"], t=15)
            return {
                "ok": False,
                "message": (
                    "Local edits present — sync skipped so nothing is "
                    "overwritten. Commit/push (or stash), then Sync again."
                ),
                "head": (head.stdout or "").strip(),
                "pulled": False,
                "pushed": False,
                "skipped": True,
            }

        current = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], t=15)
        current_name = (current.stdout or "").strip() or "HEAD"
        if current_name != sync:
            co = run(["git", "checkout", sync], t=30)
            if co.returncode != 0:
                err = (co.stderr or co.stdout or "checkout failed").strip()
                return {
                    "ok": False,
                    "message": "Need branch %s: %s" % (sync, err),
                    "head": "",
                    "pulled": False,
                    "pushed": False,
                    "skipped": False,
                }

        remote_ref = "origin/%s" % sync
        counts = run([
            "git", "rev-list", "--left-right", "--count",
            "HEAD...%s" % remote_ref,
        ], t=15)
        if counts.returncode != 0:
            # No upstream yet — fall back to pull helper.
            pulled = pull_source_update(root=root, timeout=timeout, branch=sync)
            return {
                "ok": bool(pulled.get("ok")),
                "message": pulled.get("message") or "",
                "head": pulled.get("head") or "",
                "pulled": bool(pulled.get("ok")),
                "pushed": False,
                "skipped": False,
            }
        parts = (counts.stdout or "0\t0").strip().split()
        ahead = int(parts[0]) if parts else 0
        behind = int(parts[1]) if len(parts) > 1 else 0

        if ahead and behind:
            head = run(["git", "log", "-1", "--oneline"], t=15)
            return {
                "ok": False,
                "message": (
                    "Branch has diverged from origin/%s (%d ahead, %d behind). "
                    "Resolve in git, then Sync."
                    % (sync, ahead, behind)
                ),
                "head": (head.stdout or "").strip(),
                "pulled": False,
                "pushed": False,
                "skipped": False,
            }

        pulled = False
        pushed = False
        bits = []

        if behind:
            pull = pull_source_update(root=root, timeout=timeout, branch=sync)
            if not pull.get("ok"):
                return {
                    "ok": False,
                    "message": pull.get("message") or "pull failed",
                    "head": pull.get("head") or "",
                    "pulled": False,
                    "pushed": False,
                    "skipped": False,
                }
            pulled = True
            bits.append(pull.get("message") or "pulled")

        if ahead and do_push:
            push_cmd = ["git"] + rewrite + ["push", "origin", sync]
            push = run(push_cmd)
            # HTTPS rewrite helps fetch on public repos; push usually needs
            # real credentials — try once without rewrite if rewrite failed.
            if push.returncode != 0 and rewrite:
                push = run(["git", "push", "origin", sync])
            if push.returncode != 0:
                err = (push.stderr or push.stdout or "push failed").strip()
                head = run(["git", "log", "-1", "--oneline"], t=15)
                head_line = (head.stdout or "").strip()
                tip = err.splitlines()[-1] if err else "auth"
                if pulled:
                    msg = (
                        "%s Push failed (%s). Fix git auth, then Sync again."
                        % (bits[0] if bits else "Pulled.", tip)
                    )
                else:
                    msg = "Push failed: %s" % tip
                return {
                    "ok": False,
                    "message": msg,
                    "head": head_line,
                    "pulled": pulled,
                    "pushed": False,
                    "skipped": False,
                }
            pushed = True
            bits.append("Pushed %d commit%s to origin/%s." % (
                ahead, "" if ahead == 1 else "s", sync))

        head = run(["git", "log", "-1", "--oneline"], t=15)
        head_line = (head.stdout or "").strip()
        if not bits:
            msg = "Already in sync with origin/%s (%s)." % (
                sync, head_line or sync)
        else:
            msg = " ".join(bits)
            if pulled and "Restart" not in msg:
                msg += " Restart Nebula to load pulled code."
        try:
            from . import version as version_mod
            version_mod.git_describe(force=True)
        except Exception:
            pass
        return {
            "ok": True,
            "message": msg,
            "head": head_line,
            "pulled": pulled,
            "pushed": pushed,
            "skipped": False,
        }
    except FileNotFoundError:
        return {
            "ok": False, "message": "git is not on PATH.", "head": "",
            "pulled": False, "pushed": False, "skipped": False,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False, "message": "git timed out.", "head": "",
            "pulled": False, "pushed": False, "skipped": False,
        }
    except Exception as exc:
        return {
            "ok": False, "message": str(exc), "head": "",
            "pulled": False, "pushed": False, "skipped": False,
        }


def relaunch_source(root=None, pid=None):
    """Relaunch this source checkout after the current process exits.

    Companion to ``load_source_snapshot`` for source installs: Settings can
    pull new code, but a Python process never re-imports itself, so "Load
    latest" needs a clean restart before the new code runs.

    Writes a tiny waiter into %TEMP% - deliberately **not** beside the repo,
    where a stray helper file would dirty the tree and ship on the next
    Save this machine. The waiter waits for ``pid`` to drop (mutex and
    WebView2 children released), then starts ``pythonw spike/app.py --show``
    from the repo root - the same argv as the Start Menu shortcut.
    """
    import subprocess
    import tempfile
    import textwrap

    if is_frozen():
        return {"ok": False,
                "message": "Packaged builds use Install & relaunch."}
    root = root or source_checkout_root()
    if not root:
        return {"ok": False, "message": "Not a git checkout."}
    entry = os.path.join(root, "spike", "app.py")
    if not os.path.isfile(entry):
        return {"ok": False, "message": "spike/app.py missing."}

    pyw = sys.executable
    if pyw.lower().endswith("python.exe"):
        candidate = pyw[:-len("python.exe")] + "pythonw.exe"
        if os.path.isfile(candidate):
            pyw = candidate

    pid = int(pid or os.getpid())
    helper = os.path.join(tempfile.gettempdir(), "_nebula_relaunch.py")
    script = textwrap.dedent("""\
        import os, sys, time, subprocess
        pid, pyw, entry, root = (sys.argv[1], sys.argv[2], sys.argv[3],
                                 sys.argv[4])
        for _ in range(120):
            try:
                import ctypes
                SYNCHRONIZE = 0x00100000
                h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False,
                                                       int(pid))
                if h:
                    ctypes.windll.kernel32.CloseHandle(h)
                    time.sleep(0.5)
                    continue
            except Exception:
                pass
            break
        flags = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP
        subprocess.Popen([pyw, entry, "--show"], cwd=root,
                         close_fds=True, creationflags=flags)
        try:
            os.remove(__file__)
        except OSError:
            pass
        """)
    with open(helper, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(script)

    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [pyw, helper, str(pid), pyw, entry, root],
        cwd=tempfile.gettempdir(),
        close_fds=True,
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"ok": True, "message": "Restarting with the latest source."}


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
