"""Durable clip index + re-evictable fetch cache for on-demand NAS opens.

Why APP_DIR (not recording_root) for both index and cache
--------------------------------------------------------
- ``offload_queue.json`` / ``offload_state.json`` already live under APP_DIR.
  The catalog is the same class of durable bookkeeping: it must survive
  move-mode deletion of the local recording.
- The offloader backlog walk scans ``recording_root/<game>/*``. Keeping the
  cache out of that tree means a fetch can never be mistaken for a new
  recording to re-offload, and a concurrent offload cannot race a cache write
  under the same folder.
- ``recording_root`` can change (drive letter, folder rename). APP_DIR is the
  process lifetime for user data; the index key is ``game/name`` (rel), not an
  absolute path under the recording root.

Sacred rule (fetch direction)
-----------------------------
Fetch **never** deletes or rewrites the NAS copy. Cache writes use
``.part`` then ``os.replace``. Hash/size mismatch drops the ``.part`` only.
Index removal never implies NAS delete.

Failure modes handled here
--------------------------
- NAS down mid-fetch → ``.part`` cleaned or left incomplete; status=error;
  NAS untouched; index untouched.
- Stale ``.part`` → never listed as complete; ``ensure_local`` removes and
  restarts the copy.
- Index drift (manual NAS delete) → ``ensure_local`` fails clearly; optional
  ``backfill_from_nas`` re-syncs presence when the share is up.
- Hash/size mismatch → delete ``.part`` only; return error.
- Concurrent offload + fetch → fetch only reads the final NAS path (never
  writes NAS); per-rel lock serialises cache writes.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

from . import paths as paths_mod
from .fsprobe import isdir_within

_CHUNK = 4 * 1024 * 1024
_VIDEO_EXTS = (".mkv", ".mp4", ".mov", ".flv", ".ts", ".m4v")
_INDEX_NAME = "clip_index.json"
# A backfill that changes nothing still says so this often, so a quiet run
# is distinguishable from a dead one.
_BACKFILL_QUIET_LOG_S = 3600.0
_CACHE_DIRNAME = "clip_cache"
_FETCH_PROBE_TIMEOUT_S = 8.0
_PAUSE_POLL_S = 0.12
_CACHE_MAX_GB_DEFAULT = 50.0


class FetchCancelled(Exception):
    """User cancelled an in-flight cache download."""


def _now() -> float:
    return time.time()


def _rel_key(game: str, name: str) -> str:
    game = (game or "").replace("\\", "/").strip("/")
    name = (name or "").replace("\\", "/").strip("/")
    return "%s/%s" % (game, name)


def _safe_rel(rel: str) -> str | None:
    """Reject path traversal; return normalised ``game/name`` or None."""
    rel = (rel or "").replace("\\", "/").strip("/")
    if not rel or ".." in rel.split("/"):
        return None
    parts = [p for p in rel.split("/") if p]
    if len(parts) < 2:
        return None
    # game may contain spaces; name is the final segment
    game = "/".join(parts[:-1])
    name = parts[-1]
    if not game or not name or name.endswith(".part"):
        return None
    return "%s/%s" % (game, name)


class ClipCatalog:
    """Thread-safe index + cache. Construct per config (cheap; file I/O lazy)."""

    def __init__(self, config, on_log=None, app_dir=None):
        self._config = config
        self._log = on_log or (lambda msg: None)
        # Read APP_DIR at construct time (not import time) so tests — and a
        # frozen vs source switch — can patch obsauto.paths.APP_DIR.
        self._app_dir = app_dir or paths_mod.APP_DIR
        self._index_path = os.path.join(self._app_dir, _INDEX_NAME)
        self._cache_root = os.path.join(self._app_dir, _CACHE_DIRNAME)
        self._lock = threading.RLock()
        self._entries = {}  # rel -> dict
        self._fetches = {}  # rel -> status dict
        self._fetch_locks = {}  # rel -> Lock
        self._cancel = {}  # rel -> threading.Event
        self._pause = {}  # rel -> threading.Event (set => paused)
        self._loaded = False
        # Last backfill result that was worth an activity line, and when.
        self._last_backfill_said = None
        self._last_backfill_said_at = 0.0

    # ---- config helpers -------------------------------------------------
    @property
    def recording_root(self) -> str:
        return (self._config.get("recording_root") or "").strip()

    def nas_root(self) -> str:
        """Best-effort active NAS root (manual config only).

        Prefer ``resolve_active_root`` / an Offloader-supplied override when
        auto LAN/remote is enabled — the manual drive letter is often offline
        while the UNC share is up.
        """
        return self._normalize_root(self._config.get("nas_offload_root"))

    def candidate_nas_roots(self):
        """All configured offload destinations, de-duplicated (manual/lan/remote)."""
        keys = (
            "nas_offload_root",
            "nas_offload_root_lan",
            "nas_offload_root_remote",
        )
        out, seen = [], set()
        for key in keys:
            root = self._normalize_root(self._config.get(key))
            if not root:
                continue
            marker = root.lower()
            if marker in seen:
                continue
            seen.add(marker)
            out.append(root)
        return out

    @staticmethod
    def _normalize_root(raw) -> str:
        raw = (raw or "").strip()
        if not raw:
            return ""
        if len(raw) == 2 and raw[1] == ":":
            raw = raw + os.sep
        return os.path.normpath(raw)

    def resolve_active_root(self, preferred: str | None = None) -> str:
        """Pick a live NAS root: preferred, else first reachable candidate."""
        preferred = self._normalize_root(preferred) if preferred else ""
        if preferred and self.nas_reachable(preferred):
            return preferred
        for root in self.candidate_nas_roots():
            if self.nas_reachable(root):
                return root
        # Fall back to preferred / manual even if currently unreachable so
        # callers still have a path to show in errors.
        return preferred or self.nas_root()

    def nas_reachable(self, root: str | None = None) -> bool:
        """True when ``root`` is a directory — or, if root is None, any candidate."""
        if root is not None:
            root = self._normalize_root(root)
            if not root:
                return False
            try:
                return isdir_within(root)
            except OSError:
                return False
        return any(self.nas_reachable(r) for r in self.candidate_nas_roots())

    @staticmethod
    def online_from_reachability(reachability) -> bool | None:
        """Interpret an Offloader diagnose code without touching the filesystem.

        ``True`` / ``False`` when the code is conclusive. ``None`` means the
        caller may probe. UI threads must treat ``None`` as offline rather than
        ``isdir()`` a dead mapped drive or Tailscale UNC (20–60s hang).
        """
        if not reachability:
            return None
        code = str(reachability)
        if code.startswith("nas_up") or code == "nas_reachable":
            return True
        if code.startswith("nas_down") or code == "off":
            return False
        return None

    def nas_online(self, nas_root: str | None = None, reachability: str | None = None,
                   probe=True) -> bool:
        """Listing-level online signal.

        Prefer Offloader's cached diagnose when provided — it already resolved
        LAN vs remote. A conclusive ``nas_down*`` / ``off`` must not fall
        through to ``isdir()``: a dead ``Z:`` or unreachable UNC hangs 20–60s
        on the thread that asked, and the v4 snapshot runs on the JS bridge.

        Live probes (``reachability`` absent/unknown) still walk candidates so
        a background scan can see a share that just came back. UI threads pass
        ``probe=False`` and treat unknown as offline.
        """
        known = self.online_from_reachability(reachability)
        if known is not None:
            return known
        if not probe:
            return False
        if nas_root is not None and self.nas_reachable(nas_root):
            return True
        return self.nas_reachable(None)

    # ---- persistence ----------------------------------------------------
    def _ensure_loaded(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entries = data.get("entries") if isinstance(data, dict) else data
                if isinstance(entries, list):
                    for item in entries:
                        rel = _safe_rel(item.get("rel") or "")
                        if rel:
                            self._entries[rel] = self._normalise_entry(item, rel)
                elif isinstance(entries, dict):
                    for rel, item in entries.items():
                        safe = _safe_rel(rel)
                        if safe and isinstance(item, dict):
                            self._entries[safe] = self._normalise_entry(item, safe)
            except (OSError, ValueError, TypeError):
                self._entries = {}
            self._loaded = True

    @staticmethod
    def _normalise_entry(item: dict, rel: str) -> dict:
        game, _, name = rel.partition("/")
        return {
            "rel": rel,
            "game": item.get("game") or game,
            "name": item.get("name") or name,
            "size": int(item.get("size") or 0),
            "mtime": float(item.get("mtime") or 0),
            "sha256": (item.get("sha256") or "") or "",
            "nas_path": item.get("nas_path") or "",
            "offloaded_at": float(item.get("offloaded_at") or 0),
        }

    def _save(self):
        try:
            os.makedirs(self._app_dir, exist_ok=True)
            tmp = self._index_path + ".tmp"
            payload = {
                "version": 1,
                "entries": sorted(
                    self._entries.values(), key=lambda e: e["rel"].lower()),
            }
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self._index_path)
        except OSError as exc:
            self._log("[Clips] Couldn't save index: %s" % exc)

    # ---- index API ------------------------------------------------------
    def upsert(self, *, game, name, size=0, mtime=0.0, sha256="",
               nas_path="", offloaded_at=None, rel=None, save=True):
        rel = _safe_rel(rel or _rel_key(game, name))
        if not rel:
            return None
        game, _, name = rel.partition("/")
        self._ensure_loaded()
        with self._lock:
            prev = self._entries.get(rel) or {}
            entry = {
                "rel": rel,
                "game": game,
                "name": name,
                "size": int(size or prev.get("size") or 0),
                "mtime": float(mtime or prev.get("mtime") or 0),
                "sha256": (sha256 or prev.get("sha256") or "") or "",
                "nas_path": nas_path or prev.get("nas_path") or "",
                "offloaded_at": float(
                    offloaded_at if offloaded_at is not None
                    else prev.get("offloaded_at") or _now()),
            }
            self._entries[rel] = entry
            if save:
                self._save()
            return dict(entry)

    def flush(self):
        """Persist the in-memory index (after a batch of save=False upserts)."""
        self._ensure_loaded()
        with self._lock:
            self._save()

    def record_offload(self, src, dest, game="", sha256="", size=None,
                       mtime=None):
        """Called from Offloader._finalize after a verified NAS copy."""
        name = os.path.basename(src or dest or "")
        if not name:
            return None
        folder = (game or "").strip()
        if not folder:
            # Prefer the NAS parent folder name (mirrors local game folder).
            folder = os.path.basename(os.path.dirname(dest or src or "")) or "Unknown"
        try:
            st_size = int(size) if size is not None else os.path.getsize(dest)
        except OSError:
            st_size = 0
        try:
            st_mtime = float(mtime) if mtime is not None else os.path.getmtime(
                dest if os.path.isfile(dest) else src)
        except OSError:
            st_mtime = _now()
        return self.upsert(
            game=folder,
            name=name,
            size=st_size,
            mtime=st_mtime,
            sha256=sha256 or "",
            nas_path=os.path.normpath(dest) if dest else "",
            offloaded_at=_now(),
        )

    def get(self, rel: str):
        rel = _safe_rel(rel)
        if not rel:
            return None
        self._ensure_loaded()
        with self._lock:
            entry = self._entries.get(rel)
            return dict(entry) if entry else None

    def list_entries(self):
        self._ensure_loaded()
        with self._lock:
            return [dict(e) for e in self._entries.values()]

    def remove_index_entry(self, rel: str) -> bool:
        """Drop a listing only. Never touches NAS or recording_root."""
        rel = _safe_rel(rel)
        if not rel:
            return False
        self._ensure_loaded()
        with self._lock:
            if rel not in self._entries:
                return False
            del self._entries[rel]
            self._save()
            return True

    # ---- cache ----------------------------------------------------------
    def cache_path(self, rel: str) -> str | None:
        rel = _safe_rel(rel)
        if not rel:
            return None
        return os.path.join(self._cache_root, *rel.split("/"))

    def cached_file(self, rel: str) -> str | None:
        path = self.cache_path(rel)
        if path and os.path.isfile(path) and not path.endswith(".part"):
            return path
        return None

    def local_path(self, rel: str) -> str | None:
        rel = _safe_rel(rel)
        if not rel:
            return None
        root = self.recording_root
        if not root:
            return None
        path = os.path.normpath(os.path.join(root, *rel.split("/")))
        # Stay inside recording_root.
        try:
            root_abs = os.path.abspath(root)
            path_abs = os.path.abspath(path)
            prefix = root_abs.rstrip("\\/") + os.sep
            if not path_abs.lower().startswith(prefix.lower()):
                return None
        except (OSError, ValueError):
            return None
        if os.path.isfile(path):
            return path
        return None

    def evict(self, rel: str) -> bool:
        """Remove a cache file (and its ``.part``). Never touches NAS."""
        rel = _safe_rel(rel)
        if not rel:
            return False
        path = self.cache_path(rel)
        if not path:
            return False
        removed = False
        for candidate in (path, path + ".part"):
            try:
                if os.path.isfile(candidate):
                    os.remove(candidate)
                    removed = True
            except OSError as exc:
                self._log("[Clips] Cache evict failed (%s): %s" % (
                    os.path.basename(candidate), exc))
        with self._lock:
            self._fetches.pop(rel, None)
        return removed

    def evict_all(self) -> int:
        self._ensure_loaded()
        n = 0
        for entry in self.list_entries():
            if self.evict(entry["rel"]):
                n += 1
        # Also sweep orphan cache files.
        root = self._cache_root
        if os.path.isdir(root):
            for dirpath, _dirnames, filenames in os.walk(root):
                for name in filenames:
                    try:
                        os.remove(os.path.join(dirpath, name))
                        n += 1
                    except OSError:
                        pass
        return n

    # ---- merge / listing ------------------------------------------------
    def location_for(self, rel: str, nas_root: str | None = None) -> str:
        """``local`` | ``cached`` | ``remote`` — presence, not reachability."""
        if self.local_path(rel):
            return "local"
        if self.cached_file(rel):
            return "cached"
        return "remote"

    def availability_for(self, rel: str, nas_root: str | None = None,
                         nas_up=None) -> str:
        """Reachability for a remote row.

        Listing must not ``isfile`` every NAS path — that is a multi-second
        SMB round-trip per clip. Pass ``nas_up`` from a single probe at merge
        time; missing files are discovered when the user opens the clip.
        """
        loc = self.location_for(rel, nas_root)
        if loc in ("local", "cached"):
            return "online"
        if nas_up is None:
            nas_up = self.nas_online(nas_root)
        return "online" if nas_up else "offline"

    def merge_with_local(self, local_clips, nas_root: str | None = None,
                         nas_up=None):
        """Merge a recording_root scan with the durable index.

        Local presence wins (``location=local``). Index-only rows become
        ``remote`` or ``cached``. ``.part`` files are never emitted.

        Trusts the local index for the list — one online probe, no per-file
        network stats. ``nas_up`` may be supplied by the Offloader diagnose.
        """
        self._ensure_loaded()
        nas_root = (self._normalize_root(nas_root)
                    if nas_root is not None else self.resolve_active_root())
        if nas_up is None:
            nas_up = self.nas_online(nas_root)
        by_rel = {}

        for raw in local_clips or []:
            name = raw.get("name") or os.path.basename(raw.get("path") or "")
            game = raw.get("game") or ""
            rel = _safe_rel(raw.get("rel") or _rel_key(game, name))
            if not rel or name.endswith(".part"):
                continue
            path = os.path.normpath(raw["path"]) if raw.get("path") else ""
            by_rel[rel] = {
                "rel": rel,
                "game": game or rel.split("/", 1)[0],
                "name": name,
                "path": path,
                "size": int(raw.get("size") or 0),
                "mtime": float(raw.get("mtime") or 0),
                "sha256": "",
                "nas_path": "",
                "location": "local",
                "availability": "online",
                "offloaded_at": 0.0,
            }

        for entry in self.list_entries():
            rel = entry["rel"]
            if rel in by_rel:
                # Local wins; attach NAS metadata if we have it.
                if entry.get("nas_path"):
                    by_rel[rel]["nas_path"] = entry["nas_path"]
                if entry.get("sha256"):
                    by_rel[rel]["sha256"] = entry["sha256"]
                by_rel[rel]["offloaded_at"] = entry.get("offloaded_at") or 0
                continue
            loc = self.location_for(rel, nas_root)
            cache = self.cached_file(rel) if loc == "cached" else None
            # Prefer a live path under the active root when the stored
            # nas_path was recorded against a different mount (Z: vs UNC).
            stored = entry.get("nas_path") or ""
            inferred = ""
            if nas_root:
                inferred = os.path.normpath(
                    os.path.join(nas_root, *rel.split("/")))
            by_rel[rel] = {
                "rel": rel,
                "game": entry["game"],
                "name": entry["name"],
                "path": cache or inferred or stored,
                "size": int(entry.get("size") or 0),
                "mtime": float(entry.get("mtime") or 0),
                "sha256": entry.get("sha256") or "",
                "nas_path": stored or inferred,
                "location": loc,
                "availability": self.availability_for(
                    rel, nas_root, nas_up=nas_up),
                "offloaded_at": float(entry.get("offloaded_at") or 0),
            }

        return sorted(by_rel.values(), key=lambda c: -c["mtime"])

    # ---- backfill -------------------------------------------------------
    def backfill_from_nas(self, nas_root: str | None = None) -> dict:
        """One-shot walk of the NAS tree into the index (no downloads).

        Batches index writes — one save at the end — so a large library does
        not rewrite ``clip_index.json`` once per file.
        """
        root = nas_root if nas_root is not None else self.nas_root()
        if not root:
            return {"ok": False, "message": "No NAS root configured.",
                    "added": 0, "seen": 0}
        if not self.nas_reachable(root):
            return {"ok": False, "message": "NAS unreachable — index unchanged.",
                    "added": 0, "seen": 0}
        added = seen = 0
        try:
            games = sorted(
                (g for g in os.listdir(root)
                 if os.path.isdir(os.path.join(root, g))
                 and not g.startswith(".")),
                key=lambda s: s.lower())
        except OSError as exc:
            return {"ok": False, "message": "NAS scan failed: %s" % exc,
                    "added": 0, "seen": 0}
        for game in games:
            folder = os.path.join(root, game)
            try:
                with os.scandir(folder) as it:
                    entries = list(it)
            except OSError:
                continue
            for ent in entries:
                name = ent.name
                if name.endswith(".part"):
                    continue
                if not name.lower().endswith(_VIDEO_EXTS):
                    continue
                try:
                    if not ent.is_file(follow_symlinks=False):
                        continue
                    st = ent.stat(follow_symlinks=False)
                except OSError:
                    continue
                seen += 1
                rel = _rel_key(game, name)
                prev = self.get(rel)
                path = os.path.normpath(ent.path)
                if prev and prev.get("nas_path") == path \
                        and int(prev.get("size") or 0) == st.st_size:
                    continue
                self.upsert(
                    game=game,
                    name=name,
                    size=st.st_size,
                    mtime=st.st_mtime,
                    nas_path=path,
                    offloaded_at=(prev or {}).get("offloaded_at") or st.st_mtime,
                    save=False,
                )
                added += 1
        if added:
            self.flush()
        msg = "Indexed %d NAS clip%s (%d scanned)." % (
            added, "" if added == 1 else "s", seen)
        # The activity pane is the only place these land, and a reconcile that
        # found nothing is not news. "Indexed 0 NAS clips (4767 scanned)."
        # every few minutes buried everything else in the feed. Speak when
        # something changed - anything indexed, or a different file count -
        # and otherwise no more than once an hour, so a long quiet run still
        # shows the scan is alive.
        now = time.time()
        state = (added, seen)
        if (added or state != self._last_backfill_said
                or now - self._last_backfill_said_at >= _BACKFILL_QUIET_LOG_S):
            self._last_backfill_said = state
            self._last_backfill_said_at = now
            self._log("[Clips] Backfill: %s" % msg)
        return {"ok": True, "message": msg, "added": added, "seen": seen}

    # ---- fetch / ensure_local -------------------------------------------
    def fetch_status(self, rel: str):
        rel = _safe_rel(rel)
        if not rel:
            return {"rel": "", "state": "error", "error": "invalid rel"}
        with self._lock:
            st = self._fetches.get(rel)
            if st:
                return dict(st)
        if self.local_path(rel) or self.cached_file(rel):
            path = self.local_path(rel) or self.cached_file(rel)
            return {
                "rel": rel,
                "state": "ready",
                "path": path,
                "bytes": 0,
                "total": 0,
                "error": "",
            }
        return {
            "rel": rel,
            "state": "idle",
            "path": "",
            "bytes": 0,
            "total": 0,
            "error": "",
        }

    def _set_fetch(self, rel: str, **fields):
        with self._lock:
            cur = self._fetches.get(rel) or {
                "rel": rel, "state": "idle", "path": "",
                "bytes": 0, "total": 0, "error": "",
            }
            cur.update(fields)
            cur["rel"] = rel
            self._fetches[rel] = cur
            return dict(cur)

    def _control_events(self, rel: str):
        with self._lock:
            cancel = self._cancel.get(rel)
            if cancel is None:
                cancel = threading.Event()
                self._cancel[rel] = cancel
            pause = self._pause.get(rel)
            if pause is None:
                pause = threading.Event()
                self._pause[rel] = pause
            return cancel, pause

    def _clear_controls(self, rel: str):
        cancel, pause = self._control_events(rel)
        cancel.clear()
        pause.clear()

    def pause_fetch(self, rel_or_path: str) -> dict:
        """Pause an in-flight download; keeps the ``.part`` for resume."""
        rel = _safe_rel(rel_or_path)
        if not rel:
            return {"ok": False, "error": "invalid clip id"}
        st = self.fetch_status(rel)
        # Finished between the caller seeing "downloading" and this call:
        # same reasoning as resume-on-ready - success, not an error toast.
        if st.get("state") == "ready":
            return {"ok": True, "status": st}
        if st.get("state") not in ("downloading", "paused"):
            return {"ok": False, "error": "Nothing downloading to pause.",
                    "status": st}
        _, pause = self._control_events(rel)
        pause.set()
        self._set_fetch(
            rel, state="paused",
            bytes=int(st.get("bytes") or 0),
            total=int(st.get("total") or 0),
            error="")
        return {"ok": True, "status": self.fetch_status(rel)}

    def resume_fetch(self, rel_or_path: str) -> dict:
        """Clear the pause flag so a waiting (or restarted) copy continues."""
        rel = _safe_rel(rel_or_path)
        if not rel:
            return {"ok": False, "error": "invalid clip id"}
        st = self.fetch_status(rel)
        # A download that finished while paused (small file, fast disk) has
        # nothing to resume - which is success, not an error. The UI would
        # otherwise show a failure toast for pressing Resume one second late.
        if st.get("state") == "ready":
            return {"ok": True, "status": st}
        if st.get("state") not in ("paused", "downloading"):
            return {"ok": False, "error": "Nothing paused to resume.",
                    "status": st}
        _, pause = self._control_events(rel)
        pause.clear()
        self._set_fetch(
            rel, state="downloading",
            bytes=int(st.get("bytes") or 0),
            total=int(st.get("total") or 0),
            error="")
        return {"ok": True, "status": self.fetch_status(rel)}

    def cancel_fetch(self, rel_or_path: str) -> dict:
        """Cancel download; ``.part`` is removed when the worker exits."""
        rel = _safe_rel(rel_or_path)
        if not rel:
            return {"ok": False, "error": "invalid clip id"}
        cancel, pause = self._control_events(rel)
        pause.clear()
        cancel.set()
        st = self.fetch_status(rel)
        self._set_fetch(
            rel, state="idle", path="",
            bytes=int(st.get("bytes") or 0),
            total=int(st.get("total") or 0),
            error="")
        return {"ok": True, "status": self.fetch_status(rel)}

    def _lock_for(self, rel: str) -> threading.Lock:
        with self._lock:
            lock = self._fetch_locks.get(rel)
            if lock is None:
                lock = threading.Lock()
                self._fetch_locks[rel] = lock
            return lock

    def resolve_nas_path(self, rel: str, nas_root: str | None = None) -> str | None:
        entry = self.get(rel)
        if entry and entry.get("nas_path") and os.path.isfile(entry["nas_path"]):
            return entry["nas_path"]
        roots = []
        preferred = self._normalize_root(nas_root) if nas_root is not None else ""
        if preferred:
            roots.append(preferred)
        for root in self.candidate_nas_roots():
            if root not in roots:
                roots.append(root)
        for root in roots:
            inferred = os.path.normpath(os.path.join(root, *rel.split("/")))
            if os.path.isfile(inferred):
                return inferred
        return None

    def ensure_local(self, rel_or_path: str, nas_root: str | None = None,
                     progress=None) -> dict:
        """Return a local filesystem path ready to open, fetching if needed.

        Never deletes NAS. Never enqueues offload. On failure returns
        ``{ok: False, error: ...}`` without hanging forever when the share is
        down (isdir probe first).
        """
        rel = _safe_rel(rel_or_path)
        if not rel:
            # Allow absolute local paths → derive rel under recording_root.
            path = os.path.normpath(rel_or_path or "")
            root = self.recording_root
            if root and path and os.path.isfile(path):
                try:
                    root_abs = os.path.abspath(root)
                    path_abs = os.path.abspath(path)
                    prefix = root_abs.rstrip("\\/") + os.sep
                    if path_abs.lower().startswith(prefix.lower()):
                        rel = _safe_rel(path_abs[len(prefix):].replace("\\", "/"))
                except (OSError, ValueError):
                    rel = None
            if not rel and path and os.path.isfile(path):
                return {"ok": True, "path": path, "location": "local",
                        "rel": ""}
            return {"ok": False, "error": "invalid clip id", "rel": ""}

        local = self.local_path(rel)
        if local:
            self._set_fetch(rel, state="ready", path=local, error="")
            return {"ok": True, "path": local, "location": "local", "rel": rel}

        cached = self.cached_file(rel)
        entry = self.get(rel) or {}
        if cached:
            if self._cache_ok(cached, entry):
                self._set_fetch(rel, state="ready", path=cached, error="")
                return {"ok": True, "path": cached, "location": "cached",
                        "rel": rel}
            # Corrupt/partial cache — drop and refetch.
            self.evict(rel)

        root = nas_root if nas_root is not None else self.resolve_active_root()
        if not self.nas_online(root):
            msg = "NAS unreachable — can't download this clip right now."
            self._set_fetch(rel, state="error", error=msg, path="")
            return {"ok": False, "error": msg, "rel": rel, "availability": "offline"}

        src = self.resolve_nas_path(rel, root)
        if not src:
            # Last chance: resolve against every candidate even if the
            # preferred root probe flaked.
            src = self.resolve_nas_path(rel, None)
        if not src:
            msg = "Clip not found on the NAS (index may be stale)."
            self._set_fetch(rel, state="error", error=msg, path="")
            return {"ok": False, "error": msg, "rel": rel, "availability": "missing"}

        lock = self._lock_for(rel)
        if not lock.acquire(timeout=_FETCH_PROBE_TIMEOUT_S):
            msg = "Another download is already in progress for this clip."
            return {"ok": False, "error": msg, "rel": rel}
        try:
            # Re-check after lock (another thread may have finished).
            cached = self.cached_file(rel)
            if cached and self._cache_ok(cached, entry):
                self._set_fetch(rel, state="ready", path=cached, error="")
                return {"ok": True, "path": cached, "location": "cached",
                        "rel": rel}

            dest = self.cache_path(rel)
            if not dest:
                return {"ok": False, "error": "invalid cache path", "rel": rel}
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            part = dest + ".part"
            # Resume only when the .part is a real prefix of the NAS file
            # (paused downloads) — a stale/corrupt .part is wiped and redone.
            resume_from = 0
            if os.path.isfile(part):
                try:
                    resume_from = int(os.path.getsize(part))
                except OSError:
                    resume_from = 0
                    self._cleanup(part)
                if resume_from > 0 and not self._part_is_prefix(src, part, resume_from):
                    self._cleanup(part)
                    resume_from = 0
            else:
                self._cleanup(dest)

            try:
                total = os.path.getsize(src)
            except OSError as exc:
                msg = "Can't read NAS clip: %s" % exc
                self._set_fetch(rel, state="error", error=msg)
                return {"ok": False, "error": msg, "rel": rel}

            if resume_from > total:
                self._cleanup(part)
                resume_from = 0

            self._clear_controls(rel)
            self._set_fetch(rel, state="downloading", bytes=resume_from,
                            total=total, path="", error="")
            expected_sha = (entry.get("sha256") or "").lower()
            try:
                digest = self._copy_part(
                    src, part, rel, total, progress, resume_from=resume_from)
            except FetchCancelled:
                self._cleanup(part)
                self._set_fetch(rel, state="idle", path="", bytes=0,
                                total=0, error="")
                self._log("[Clips] Download cancelled (%s)" % rel)
                return {"ok": False, "error": "Download cancelled.",
                        "rel": rel, "cancelled": True}
            except (OSError, RuntimeError) as exc:
                # Keep .part on transient I/O so a retry can resume, unless
                # the file is clearly useless.
                msg = "Download failed: %s" % exc
                self._set_fetch(rel, state="error", error=msg)
                self._log("[Clips] %s (%s)" % (msg, rel))
                return {"ok": False, "error": msg, "rel": rel}

            try:
                part_size = os.path.getsize(part)
            except OSError:
                part_size = -1
            if part_size != total:
                self._cleanup(part)
                msg = "Download incomplete (size mismatch)."
                self._set_fetch(rel, state="error", error=msg)
                return {"ok": False, "error": msg, "rel": rel}

            if expected_sha and digest and digest != expected_sha:
                self._cleanup(part)
                msg = "Download checksum mismatch — NAS copy left untouched."
                self._set_fetch(rel, state="error", error=msg)
                self._log("[Clips] %s (%s)" % (msg, rel))
                return {"ok": False, "error": msg, "rel": rel}

            try:
                os.replace(part, dest)
            except OSError as exc:
                self._cleanup(part)
                msg = "Couldn't finalise cache: %s" % exc
                self._set_fetch(rel, state="error", error=msg)
                return {"ok": False, "error": msg, "rel": rel}

            # Refresh index metadata from the NAS source we just read.
            self.upsert(
                game=entry.get("game") or rel.split("/", 1)[0],
                name=entry.get("name") or os.path.basename(rel),
                size=total,
                mtime=entry.get("mtime") or _now(),
                sha256=digest or expected_sha,
                nas_path=os.path.normpath(src),
            )
            self._clear_controls(rel)
            self._set_fetch(rel, state="ready", path=dest, bytes=total,
                            total=total, error="")
            self._prune_cache(keep_rel=rel)
            return {"ok": True, "path": dest, "location": "cached", "rel": rel}
        finally:
            lock.release()

    def _prune_cache(self, keep_rel: str = "") -> None:
        """Keep the fetch cache under ``clip_cache_max_gb`` (default 50).

        A week of Tailscale clip opens can otherwise quietly eat tens of GB
        of C:. Oldest-mtime first, only files the index knows about (orphans
        wait for evict_all), never an in-flight download, never the clip just
        fetched. Cache-only by construction - evict() cannot touch the NAS
        or recording_root.
        """
        raw = (self._config or {}).get("clip_cache_max_gb")
        try:
            cap_gb = _CACHE_MAX_GB_DEFAULT if raw is None else float(raw or 0)
        except (TypeError, ValueError):
            cap_gb = _CACHE_MAX_GB_DEFAULT
        if cap_gb <= 0:
            return
        cap_bytes = int(cap_gb * 1024 ** 3)
        root = self._cache_root
        if not os.path.isdir(root):
            return
        stats = []
        total = 0
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                p = os.path.join(dirpath, name)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                total += st.st_size
                stats.append((st.st_mtime, st.st_size, p))
        over = total - cap_bytes
        if over <= 0:
            return
        keep_path = self.cache_path(keep_rel) if keep_rel else None
        freed = 0
        stats.sort()  # oldest mtime first
        for _mtime, size, p in stats:
            if freed >= over:
                break
            if keep_path and os.path.abspath(p) == os.path.abspath(keep_path):
                continue
            rel = _safe_rel(
                os.path.relpath(p, root).replace("\\", "/"))
            if not rel:
                continue
            if (self._fetches.get(rel) or {}).get("state") == "downloading":
                continue
            with self._lock:
                if rel not in self._entries:
                    continue  # unknown/orphan file - evict_all sweeps those
            if self.evict(rel):
                freed += size
                self._log("[Clips] Cache prune: removed %s (%.0f MB)" % (
                    rel, size / (1024 * 1024)))
        if freed:
            self._log("[Clips] Cache pruned %.2f GB over the %g GB cap." % (
                freed / 1024 ** 3, cap_gb))

    def _part_is_prefix(self, src: str, part: str, nbytes: int) -> bool:
        """True when ``part`` matches the first ``nbytes`` of ``src``."""
        if nbytes <= 0:
            return False
        try:
            with open(src, "rb") as fin, open(part, "rb") as pin:
                left = nbytes
                while left > 0:
                    n = min(_CHUNK, left)
                    a = fin.read(n)
                    b = pin.read(n)
                    if not a or a != b:
                        return False
                    left -= len(a)
            return True
        except OSError:
            return False

    def _cache_ok(self, path: str, entry: dict) -> bool:
        try:
            size = os.path.getsize(path)
        except OSError:
            return False
        expected = int(entry.get("size") or 0)
        if expected and size != expected:
            return False
        sha = (entry.get("sha256") or "").lower()
        if sha:
            digest = self._hash(path)
            if digest and digest != sha:
                return False
        return size > 0

    def _copy_part(self, src, part, rel, total, progress, resume_from=0):
        """Copy ``src`` → ``part`` with pause/cancel. Returns SHA-256 hex.

        When ``resume_from`` > 0, appends to ``part`` and seeks the source.
        Hash is only returned for a full start-to-end copy (resume_from==0);
        resumed copies return ``""`` so size check remains the gate unless
        the index has no sha (callers already treat empty digest as skip).
        """
        cancel, pause = self._control_events(rel)
        h = hashlib.sha256()
        copied = max(0, int(resume_from or 0))
        stream_hash = copied == 0
        mode = "ab" if copied else "wb"
        with open(src, "rb") as fin, open(part, mode) as fout:
            if copied:
                fin.seek(copied)
            while True:
                if cancel.is_set():
                    raise FetchCancelled()
                while pause.is_set():
                    self._set_fetch(rel, state="paused", bytes=copied,
                                    total=total, error="")
                    if cancel.is_set():
                        raise FetchCancelled()
                    # Stay in the worker while paused so resume is instant.
                    pause.wait(timeout=_PAUSE_POLL_S)
                    if cancel.is_set():
                        raise FetchCancelled()
                    if not pause.is_set():
                        self._set_fetch(rel, state="downloading",
                                        bytes=copied, total=total, error="")
                        break
                chunk = fin.read(_CHUNK)
                if not chunk:
                    break
                if stream_hash:
                    h.update(chunk)
                fout.write(chunk)
                copied += len(chunk)
                self._set_fetch(rel, state="downloading", bytes=copied,
                                total=total, error="")
                if progress:
                    try:
                        progress(copied, total)
                    except Exception:
                        pass
            fout.flush()
            os.fsync(fout.fileno())
        if stream_hash:
            return h.hexdigest()
        return self._hash(part) or ""

    def _hash(self, path: str):
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(_CHUNK), b""):
                    h.update(chunk)
        except OSError:
            return None
        return h.hexdigest()

    def _cleanup(self, path: str):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass
