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

try:
    import requests
except Exception:  # pragma: no cover - requests is a declared dependency
    requests = None

API_ROOT = "https://api.github.com"
_TIMEOUT = 15


class GameSync:
    def __init__(self, config, on_log=None):
        self.repo = (config.get("github_gamedata_repo") or "").strip()
        self.token = (config.get("github_token") or "").strip()
        self.path = (config.get("github_gamedata_path") or "games.json").strip()
        self._log = on_log or (lambda msg: None)
        # Remember the blob sha of the file we last saw, so a push knows which
        # version it's updating (the contents API needs it to replace a file).
        self._sha = None

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
        remote = self.fetch()
        if remote is None:
            remote = {"games": {}, "non_games": {}}
        merged = {
            "games": {**remote.get("games", {}), **local_data.get("games", {})},
            "non_games": {**remote.get("non_games", {}), **local_data.get("non_games", {})},
        }
        # Nothing to do if the remote already matches - avoids an empty commit
        # every startup.
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
            # 409 = our cached sha is stale (another device pushed). Re-fetch and
            # retry once against the new head.
            if resp.status_code == 409:
                self.fetch()
                if self._sha:
                    params["sha"] = self._sha
                resp = requests.put(self._url(), headers=self._headers(),
                                    json=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            self._sha = resp.json().get("content", {}).get("sha")
            return merged
        except Exception as exc:
            self._log(f"[Sync] GitHub push failed: {exc}")
            return None
