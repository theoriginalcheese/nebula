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
    root = os.path.dirname(APP_DIR) if os.path.basename(APP_DIR) == "obsauto" else APP_DIR
    # APP_DIR in dev is the package parent (repo root).
    if os.path.isdir(os.path.join(APP_DIR, ".git")):
        return APP_DIR
    return None
