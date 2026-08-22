"""Sync the game/app classification list through a private GitHub repo.

Why GitHub and not the old OneDrive `sync_folder`: OneDrive wasn't syncing
reliably, and the classification list is tiny, needs to appear on other devices
*instantly*, and GitHub has effectively 100% uptime. This talks to the GitHub
**contents API over HTTPS with `requests`** - deliberately not shell `git`,
because the packaged (PyInstaller) build has no git binary.

Design points:
- **Merge, never clobber.** A push GETs the remote first and unions it with the
  local list before PUTing, so two devices classifying different games can't
  wipe each other. Same rule the old `_save()` used for the shared file.
- **Fail soft.** No token / no network / API error never raises into the app;
  it logs and moves on. The local `games.json` remains the source of truth, so
  the app works fully offline and just isn't cross-device until GitHub is back.
- **Off the UI thread.** Every call here does blocking network I/O and must be
  run from a worker (the callers do this).

Config keys (all optional; absent = feature off):
  github_token          a token with `repo` scope (kept in local config only)
  github_gamedata_repo  "owner/name", e.g. "theoriginalcheese/nebula-gamedata"
  github_gamedata_path  file path in the repo (default "games.json")
"""

import base64
import json
import os

from .classifier import merge_classifications

try:
    import requests
except Exception:  # pragma: no cover - requests is a declared dependency
    requests = None

API_ROOT = "https://api.github.com"
_TIMEOUT = 15


class GameSync:
    def __init__(self, config, on_log=None):
        self._log = on_log or (lambda msg: None)
        self.configure(config)

    def configure(self, config):
        """(Re-)read the sync target from config, so editing it in the Settings
        view takes effect without a restart.

        The cached blob sha is dropped as part of this: it identifies a version
        of the *old* file, and reusing it against a different repo or path would
        either fail or - worse - hand the contents API a sha it accepts for the
        wrong file. A None sha forces the next push to fetch first, which is the
        only state from which it's safe to write."""
        self.repo = (config.get("github_gamedata_repo") or "").strip()
        self.token = (config.get("github_token") or "").strip()
        self.path = (config.get("github_gamedata_path") or "games.json").strip()
        # Remember the blob sha of the file we last saw, so a push knows which
        # version it's updating (the contents API needs it to replace a file).
        self._sha = None

    @property
    def label(self):
        return "GitHub"

    @property
    def enabled(self):
        return bool(requests and self.repo and self.token)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self):
        return f"{API_ROOT}/repos/{self.repo}/contents/{self.path}"

    # ---- read ----
    def fetch(self):
        """Return the remote list as a dict, or None on any failure. Caches the
        blob sha so a later push can replace this exact version."""
        if not self.enabled:
            return None
        try:
            resp = requests.get(self._url(), headers=self._headers(), timeout=_TIMEOUT)
            if resp.status_code == 404:
                self._sha = None
                return {"games": {}, "non_games": {}}
            resp.raise_for_status()
            payload = resp.json()
            self._sha = payload.get("sha")
            raw = base64.b64decode(payload["content"])
            data = json.loads(raw)
            data.setdefault("games", {})
            data.setdefault("non_games", {})
            return data
        except Exception as exc:
            self._log(f"[Sync] GitHub fetch failed: {exc}")
            return None

    # ---- write ----
    def push(self, local_data):
        """Merge `local_data` into the remote list and write it back. Returns
        the merged dict (so the caller can adopt it locally) or None on failure.
        The GET-merge-PUT means a concurrent classification on another device
        survives instead of being overwritten."""
        if not self.enabled:
            return None
        # Fetch-merge-PUT in a loop. Each PUT is tagged with the exact sha we
        # just read, so a 409 (someone else pushed in between) sends us round to
        # re-fetch and re-merge against the new head instead of losing their
        # change. Bounded so a hot-contended file can't spin forever.
        for _ in range(6):
            remote = self.fetch()
            if remote is None:
                # We could NOT read the current remote. Pushing now would base a
                # write on an unknown state - if _sha is stale/None the contents
                # API would overwrite whatever is really there, clobbering other
                # devices. So refuse; the caller retries later (data stays safe
                # in the local games.json meanwhile). This was the concurrency
                # data-loss the stress test caught.
                return None
            # Local wins per key, including moving an exe out of the bucket the
            # remote still has it in - otherwise the remote copy would undo a
            # reclassification on the very next pull. Additions made on other
            # machines still survive; that's the whole point of merging.
            merged = merge_classifications(remote, local_data)
            # Remote already has everything - no empty commit.
            if merged == remote and self._sha is not None:
                return merged
            body = json.dumps(merged, indent=2, sort_keys=True) + "\n"
            params = {
                "message": "Update game classifications",
                "content": base64.b64encode(body.encode("utf-8")).decode("ascii"),
            }
            if self._sha:
                params["sha"] = self._sha
            try:
                resp = requests.put(self._url(), headers=self._headers(),
                                    json=params, timeout=_TIMEOUT)
                if resp.status_code == 409:
                    continue  # stale sha; loop to re-fetch + re-merge
                resp.raise_for_status()
                self._sha = resp.json().get("content", {}).get("sha")
                return merged
            except Exception as exc:
                self._log(f"[Sync] GitHub push failed: {exc}")
                return None
        self._log("[Sync] GitHub push gave up after repeated conflicts.")
        return None


class NasGameSync:
    """Same merge contract as :class:`GameSync`, backed by the NAS share.

    Path: ``{nas_offload_root}/.nebula/games.json``. No token. Works over the
    mapped drive / Tailscale path already used for clip offload. Local
    ``games.json`` stays the working copy; this is the cross-device hub when
    GitHub game-data is not configured.
    """

    REL_PARTS = (".nebula", "games.json")

    def __init__(self, config, on_log=None):
        self._log = on_log or (lambda msg: None)
        self.configure(config)

    def configure(self, config):
        root = (config.get("nas_offload_root") or "").strip()
        self._root = os.path.abspath(root) if root else ""
        # Default on whenever a NAS root exists; can disable without clearing root.
        flag = config.get("games_sync_nas")
        self._want = True if flag is None else bool(flag)

    @property
    def label(self):
        return "NAS"

    @property
    def enabled(self):
        return bool(self._want and self._root)

    def path(self):
        if not self._root:
            return ""
        return os.path.join(self._root, *self.REL_PARTS)

    def _nas_reachable(self):
        return bool(self._root and os.path.isdir(self._root))

    def fetch(self):
        """Remote list, or None if the NAS root is unreachable."""
        if not self.enabled:
            return None
        if not self._nas_reachable():
            self._log("[Sync] NAS game list unreachable (%s)" % self._root)
            return None
        path = self.path()
        if not os.path.isfile(path):
            return {"games": {}, "non_games": {}}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                return {"games": {}, "non_games": {}}
            data.setdefault("games", {})
            data.setdefault("non_games", {})
            if not isinstance(data["games"], dict):
                data["games"] = {}
            if not isinstance(data["non_games"], dict):
                data["non_games"] = {}
            return data
        except Exception as exc:
            self._log("[Sync] NAS game list read failed: %s" % exc)
            return None

    def push(self, local_data):
        """Merge into the NAS file and write atomically. None if unreachable."""
        if not self.enabled:
            return None
        if not self._nas_reachable():
            self._log("[Sync] NAS game list unreachable — push deferred")
            return None
        remote = self.fetch()
        if remote is None:
            return None
        merged = merge_classifications(remote, local_data or {})
        path = self.path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            body = json.dumps(merged, indent=2, sort_keys=True) + "\n"
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
            os.replace(tmp, path)
            return merged
        except Exception as exc:
            self._log("[Sync] NAS game list write failed: %s" % exc)
            try:
                if os.path.isfile(path + ".tmp"):
                    os.remove(path + ".tmp")
            except OSError:
                pass
            return None


class MultiGameSync:
    """Fan-in/out across NAS and/or GitHub with the same merge rules."""

    def __init__(self, backends, on_log=None):
        self._backends = [b for b in (backends or []) if b is not None]
        self._log = on_log or (lambda msg: None)

    def configure(self, config):
        for b in self._backends:
            if hasattr(b, "configure"):
                b.configure(config)

    @property
    def enabled(self):
        return any(getattr(b, "enabled", False) for b in self._backends)

    def status_label(self):
        names = []
        for b in self._backends:
            if getattr(b, "enabled", False):
                names.append(getattr(b, "label", b.__class__.__name__))
        if not names:
            return "this machine only"
        if len(names) == 1:
            return "shared via %s" % names[0]
        return "shared via %s" % " + ".join(names)

    def fetch(self):
        merged = {"games": {}, "non_games": {}}
        any_ok = False
        for b in self._backends:
            if not getattr(b, "enabled", False):
                continue
            remote = b.fetch()
            if remote is None:
                continue
            any_ok = True
            merged = merge_classifications(merged, remote)
        return merged if any_ok else None

    def push(self, local_data):
        data = local_data or {"games": {}, "non_games": {}}
        last = None
        any_ok = False
        for b in self._backends:
            if not getattr(b, "enabled", False):
                continue
            got = b.push(data)
            if got is None:
                continue
            any_ok = True
            last = got
            data = got
        return last if any_ok else None

