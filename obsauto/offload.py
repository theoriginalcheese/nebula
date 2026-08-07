"""Offload finished recordings from the local drive to the NAS.

Governed by one rule above all others (see the vault's "OBS footage is sacred"):
**never remove a local file until a byte-verified copy exists on the NAS.** So
every transfer is copy -> checksum both ends -> only then delete the source.
If anything is off - NAS unreachable, hash mismatch, short write - the local
file stays exactly where it is and the item is retried later.

Mechanics:
- Runs on a single background worker; recording finishes just drop a path on the
  queue and return, so nothing here ever touches the OBS/monitor timing.
- The queue is **persisted** to APP_DIR/offload_queue.json, so a clip waiting on
  an offline NAS survives an app restart and isn't silently forgotten.
- A daily (configurable) scan of ``recording_root`` enqueues anything not yet
  on the NAS once the path is reachable — plus an explicit Sync now.
- Copies to a `.part` sidecar and renames on success, so a half-copied file is
  never mistaken for a complete one.
- Verifies with SHA-256 over the whole file (source hash computed during the
  copy's single read pass; destination read back and hashed). Slower than a size
  check, but this is idle-time background work and the data is irreplaceable.

Config keys (absent/blank root = feature off, a pure no-op):
  nas_offload_root             destination base dir
  nas_offload_mode             "move" or "copy"
  nas_offload_interval_hours   auto backlog scan cadence (0 = manual only)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time

from . import tailscale as ts
from . import teracopy as tc

_CHUNK = 4 * 1024 * 1024  # 4 MiB
_RETRY_BACKOFF = 10       # seconds to wait before retrying a failed item
_UNREACHABLE_LOG_INTERVAL = 60.0  # rate-limit the silent-spin explanation
_IDLE_PROBE_S = 10.0
_FRESH_CLIP_S = 60.0      # skip files still being written (mtime too new)
_VIDEO_EXTS = (".mkv", ".mp4", ".mov", ".flv", ".ts", ".m4v")
_DEFAULT_INTERVAL_H = 24


def _sanitize(name):
    """Match ``monitor.sanitize_folder_name`` so NAS folders mirror local ones."""
    from .monitor import sanitize_folder_name
    return sanitize_folder_name(name or "") or "Unknown"


def _game_folder_for(path, game, recording_root=""):
    """NAS subfolder = the local game folder name under ``recording_root``.

    That is the ground truth (``D:/OBS/Zenless Zone Zero/clip.mkv`` →
    ``Zenless Zone Zero``). Falling back to sanitising the display name only
    when the path is not under the recording root.
    """
    root = (recording_root or "").strip()
    if root and path:
        try:
            path_abs = os.path.abspath(path)
            root_abs = os.path.abspath(root)
            prefix = root_abs.rstrip("\\/") + os.sep
            if path_abs.lower().startswith(prefix.lower()):
                rel = path_abs[len(prefix):]
                folder = rel.split(os.sep, 1)[0].strip()
                if folder and folder not in (".", ".."):
                    return folder
        except (OSError, ValueError):
            pass
    return _sanitize(game or "Unknown")


def _ago(seconds):
    """Short human age for Settings — never invents a time that did not happen."""
    if seconds is None or seconds < 0:
        return ""
    seconds = int(seconds)
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return "%dm ago" % m
    if seconds < 86400:
        h = seconds // 3600
        return "%dh ago" % h
    d = seconds // 86400
    return "%dd ago" % d

class Offloader:
    def __init__(self, config, on_log=None):
        self._config = config
        self._log = on_log or (lambda msg: None)
        from .paths import APP_DIR
        self._queue_file = os.path.join(APP_DIR, "offload_queue.json")
        self._state_file = os.path.join(APP_DIR, "offload_state.json")
        self._queue = []            # list of {"path":..., "game":...}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._worker = None
        self._on_state = None       # optional callback(pending, reachability=None)
        self._last_unreachable_log = 0.0
        self._last_root_up = None   # None unknown; True/False last seen isdir
        self._reachability = None   # last diagnose() code, for the Settings line
        self._last_scan_at = 0.0
        self._last_success_at = 0.0
        self._last_message = ""
        self._scan_busy = False
        self._load_state()

    # ---- config (re-read each item so a live config edit is picked up) ----
    @property
    def root(self):
        raw = (self._config.get("nas_offload_root") or "").strip()
        if not raw:
            return ""
        # Windows quirk: os.path.join("Z:", "Game") → "Z:Game" (cwd-relative on
        # that drive), not "Z:\Game". A bare drive letter must carry a slash.
        if len(raw) == 2 and raw[1] == ":":
            raw = raw + os.sep
        return os.path.normpath(raw)

    @property
    def mode(self):
        return (self._config.get("nas_offload_mode") or "copy").strip().lower()

    @property
    def enabled(self):
        return bool(self.root)

    @property
    def interval_hours(self):
        try:
            return max(0, int(self._config.get("nas_offload_interval_hours")
                              if self._config.get("nas_offload_interval_hours")
                              is not None else _DEFAULT_INTERVAL_H))
        except (TypeError, ValueError):
            return _DEFAULT_INTERVAL_H

    @property
    def recording_root(self):
        return (self._config.get("recording_root") or "").strip()

    def start(self, on_state=None):
        self._on_state = on_state
        self._load_queue()
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
        if self._queue:
            self._log(f"[Offload] {len(self._queue)} clip(s) queued for the NAS.")
            self._wake.set()
        elif self.enabled:
            # Kick an overdue backlog scan once NAS is up (or on first run).
            self._wake.set()

    def stop(self):
        self._stop = True
        self._wake.set()

    def refresh(self):
        """Called after the offload settings are edited. `root`/`mode` are
        properties over the live config dict, so the new values are already in
        effect - what this adds is waking the worker, so a queue that had backed
        off against an unset/unreachable root retries immediately instead of
        sitting out the rest of its backoff."""
        self._wake.set()
        self._notify()

    # ---- public: enqueue a finished clip ----
    def queue(self, path, game):
        if not self.enabled or not path:
            return
        # Persist the local game-folder name so NAS layout matches disk.
        folder = _game_folder_for(path, game, self.recording_root)
        with self._lock:
            if any(item["path"] == path for item in self._queue):
                return
            self._queue.append({"path": path, "game": folder})
            self._save_queue()
        self._log(f"[Offload] Queued {os.path.basename(path)} → {folder}/")
        self._notify()
        self._wake.set()

    def pending_paths(self):
        """Clips still waiting on a verified NAS copy.

        A clip in here has NOT been byte-verified at the far end yet, so the
        Clips pane refuses to delete it - that is the copy-verify-then-delete
        rule applied to a manual delete, not just to this worker's move mode.
        """
        with self._lock:
            return {item["path"] for item in self._queue}

    def reachability(self):
        """Last diagnose() code, or a fresh one if we have never probed.

        Safe to call from the UI thread for a cached snapshot; the worker
        refreshes it on each unreachable attempt and on successful path checks.
        """
        with self._lock:
            cached = self._reachability
        if cached is not None:
            return cached
        if not self.enabled:
            return "off"
        return ts.diagnose(self.root)

    def status_snapshot(self):
        """Honest fields for Settings → Offload. No fabricated counters."""
        with self._lock:
            pending = len(self._queue)
            reach = self._reachability
            last_scan = self._last_scan_at
            last_ok = self._last_success_at
            message = self._last_message
            busy = self._scan_busy
        if reach is None and self.enabled:
            reach = ts.diagnose(self.root)
            self._set_reachability(reach)
        peer = ts.peer_for_path(self.root) if self.enabled else None
        peer_online = ts.peer_online(peer) if peer else None
        interval = self.interval_hours
        now = time.time()
        next_in = None
        if self.enabled and interval > 0 and last_scan > 0:
            next_in = max(0, int(last_scan + interval * 3600 - now))
        elif self.enabled and interval > 0 and last_scan <= 0:
            next_in = 0
        return {
            "enabled": self.enabled,
            "pending": pending,
            "reachability": reach or ("off" if not self.enabled else ""),
            "reach_label": ts.diagnose_label(reach) if reach else "",
            "peer": peer or "",
            "peer_online": peer_online,
            "mode": self.mode if self.enabled else "",
            "root": self.root,
            "interval_hours": interval,
            "last_scan_at": last_scan or None,
            "last_success_at": last_ok or None,
            "last_scan_ago": _ago(now - last_scan) if last_scan else "",
            "last_success_ago": _ago(now - last_ok) if last_ok else "",
            "next_scan_in_s": next_in,
            "message": message,
            "busy": busy,
            "can_sync": self.enabled,
            "transfer": "TeraCopy" if tc.available(
                self._config.get("teracopy_path")) else "built-in",
        }

    def sync_now(self, recording_root=None):
        """Scan local recordings and enqueue anything not yet on the NAS.

        Safe to call from a worker or API thread. Returns a result dict the
        Settings footer can show verbatim — never invents a success.
        """
        if not self.enabled:
            return {"ok": False, "message": "Set a NAS root first.",
                    "queued": 0, "found": 0, "already": 0, "skipped": 0}
        if self._scan_busy:
            return {"ok": False, "message": "A sync is already running.",
                    "queued": 0, "found": 0, "already": 0, "skipped": 0}

        root = self.root
        up = os.path.isdir(root)
        code = ts.diagnose(root)
        self._set_reachability(code)
        if not up:
            clause = ts.diagnose_label(code)
            msg = "NAS unreachable — nothing queued."
            if clause:
                msg = "%s (%s)" % (msg, clause)
            self._last_message = msg
            self._notify()
            return {"ok": False, "message": msg, "reachability": code,
                    "queued": 0, "found": 0, "already": 0, "skipped": 0}

        recording_root = (recording_root or self.recording_root or "").strip()
        if not recording_root or not os.path.isdir(recording_root):
            msg = "Recording folder missing — nothing to scan."
            self._last_message = msg
            self._notify()
            return {"ok": False, "message": msg,
                    "queued": 0, "found": 0, "already": 0, "skipped": 0}

        result = self.enqueue_missing(recording_root)
        self._mark_scan()
        queued = result["queued"]
        if queued:
            msg = "Queued %d clip%s for the NAS." % (
                queued, "" if queued == 1 else "s")
        elif result["already"]:
            msg = "Already up to date (%d on NAS)." % result["already"]
        elif result["found"] == 0:
            msg = "No recordings found to offload."
        else:
            msg = "Nothing new to offload."
        if result["skipped"]:
            msg = "%s · %d skipped (too new)." % (msg.rstrip("."), result["skipped"])
        self._last_message = msg
        self._log("[Offload] Sync now: %s" % msg)
        self._notify()
        self._wake.set()
        return {"ok": True, "message": msg, "reachability": code, **result}

    def enqueue_missing(self, recording_root):
        """Walk ``recording_root/<game>/*`` and queue clips not yet on the NAS.

        Size match at the destination counts as already synced for the scan
        (the worker still SHA-verifies anything it actually copies). Fresh
        mtimes are skipped so an in-progress recording is never half-copied.
        """
        self._scan_busy = True
        try:
            found = already = skipped = queued = 0
            pending = self.pending_paths()
            for path, game in self.iter_local_clips(recording_root):
                found += 1
                try:
                    age = time.time() - os.path.getmtime(path)
                except OSError:
                    skipped += 1
                    continue
                if age < _FRESH_CLIP_S:
                    skipped += 1
                    continue
                if path in pending:
                    already += 1
                    continue
                if self._dest_present(path, game):
                    already += 1
                    continue
                before = self.pending_count()
                self.queue(path, game)
                if self.pending_count() > before:
                    queued += 1
                else:
                    already += 1
            return {"found": found, "queued": queued,
                    "already": already, "skipped": skipped}
        finally:
            self._scan_busy = False

    def iter_local_clips(self, recording_root):
        """Yield ``(path, game)`` for video files under the recording root.

        Ordered by game folder then filename so Sync now drains in folder order.
        """
        root = (recording_root or "").strip()
        if not root or not os.path.isdir(root):
            return
        try:
            games = sorted(
                (g for g in os.listdir(root)
                 if os.path.isdir(os.path.join(root, g))),
                key=lambda s: s.lower())
        except OSError:
            return
        for game in games:
            folder = os.path.join(root, game)
            try:
                names = sorted(
                    (n for n in os.listdir(folder)
                     if n.lower().endswith(_VIDEO_EXTS)
                     and os.path.isfile(os.path.join(folder, n))),
                    key=lambda s: s.lower())
            except OSError:
                continue
            for name in names:
                yield os.path.join(folder, name), game

    def _dest_present(self, path, game):
        """True when a same-sized file already sits at the NAS destination."""
        dest = os.path.join(
            self.root,
            _game_folder_for(path, game, self.recording_root),
            os.path.basename(path))
        try:
            if not os.path.isfile(dest):
                return False
            return os.path.getsize(path) == os.path.getsize(dest)
        except OSError:
            return False

    # ---- persistence ----
    def _load_queue(self):
        try:
            with open(self._queue_file, "r", encoding="utf-8") as f:
                items = json.load(f)
            with self._lock:
                # Drop entries whose source has since vanished (already handled).
                self._queue = [i for i in items if i.get("path") and os.path.exists(i["path"])]
                self._save_queue()
        except (OSError, ValueError):
            pass

    def _save_queue(self):
        try:
            with open(self._queue_file, "w", encoding="utf-8") as f:
                json.dump(self._queue, f, indent=2)
        except OSError:
            pass

    def _load_state(self):
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._last_scan_at = float(data.get("last_scan_at") or 0)
            self._last_success_at = float(data.get("last_success_at") or 0)
            self._last_message = str(data.get("last_message") or "")
        except (OSError, ValueError, TypeError):
            pass

    def _save_state(self):
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "last_scan_at": self._last_scan_at,
                    "last_success_at": self._last_success_at,
                    "last_message": self._last_message,
                }, f, indent=2)
        except OSError:
            pass

    def _mark_scan(self):
        self._last_scan_at = time.time()
        self._save_state()

    def _mark_success(self):
        self._last_success_at = time.time()
        self._save_state()

    def _notify(self):
        if self._on_state:
            with self._lock:
                pending = len(self._queue)
                reach = self._reachability
            try:
                # Prefer the two-arg form; older callers that only take pending
                # still work via TypeError fallback.
                self._on_state(pending, reach)
            except TypeError:
                try:
                    self._on_state(pending)
                except Exception:
                    pass
            except Exception:
                pass

    def _set_reachability(self, code):
        with self._lock:
            changed = self._reachability != code
            self._reachability = code
        return changed

    def _note_root_state(self, up):
        """Track isdir flips so a Tailscale/NAS return wakes the backoff."""
        prev = self._last_root_up
        self._last_root_up = up
        return prev is False and up is True

    def _auto_scan_due(self):
        hours = self.interval_hours
        if hours <= 0:
            return False
        if self._last_scan_at <= 0:
            return True
        return (time.time() - self._last_scan_at) >= hours * 3600

    def _maybe_auto_scan(self, reason="schedule"):
        """When the NAS path is up and the cadence is due, enqueue the backlog."""
        if not self.enabled or self._scan_busy or not self._auto_scan_due():
            return
        if not os.path.isdir(self.root):
            return
        recording_root = self.recording_root
        if not recording_root or not os.path.isdir(recording_root):
            self._mark_scan()  # don't hammer every idle tick when misconfigured
            return
        self._log("[Offload] Auto sync (%s)…" % reason)
        result = self.enqueue_missing(recording_root)
        self._mark_scan()
        if result["queued"]:
            self._last_message = "Auto: queued %d clip%s." % (
                result["queued"], "" if result["queued"] == 1 else "s")
            self._log("[Offload] %s" % self._last_message)
        else:
            self._last_message = "Auto: nothing new to offload."
        self._save_state()
        self._notify()

    # ---- worker ----
    def _run(self):
        while not self._stop:
            item = None
            with self._lock:
                if self._queue:
                    item = self._queue[0]
            if item is None:
                # Idle with an empty queue: still watch for a root coming back
                # so Settings can flip from unreachable -> up without an enqueue,
                # and run the daily backlog scan when Tailscale/NAS is online.
                if self.enabled:
                    up = os.path.isdir(self.root)
                    code = ts.diagnose(self.root) if self.root else "off"
                    recovered = self._note_root_state(up)
                    if self._set_reachability(code) or recovered:
                        self._notify()
                    if up:
                        self._maybe_auto_scan(
                            reason="nas-back" if recovered else "schedule")
                    self._wake.wait(timeout=_IDLE_PROBE_S)
                else:
                    self._wake.wait()
                self._wake.clear()
                continue
            ok = self._process(item)
            if ok:
                with self._lock:
                    if self._queue and self._queue[0] is item:
                        self._queue.pop(0)
                    self._save_queue()
                self._mark_success()
                self._notify()
            else:
                # Leave it at the head of the queue and back off before retrying;
                # the NAS is probably offline or full. Interruptible, so a fresh
                # enqueue (or stop) wakes us immediately rather than waiting out
                # the whole backoff - and short enough that a NAS coming back is
                # picked up promptly. While waiting, re-check reachability so a
                # Tailscale reconnect short-circuits the sleep.
                deadline = time.monotonic() + _RETRY_BACKOFF
                while not self._stop and time.monotonic() < deadline:
                    if self._wake.wait(timeout=1.0):
                        self._wake.clear()
                        break
                    if self.enabled and os.path.isdir(self.root):
                        # Path returned - retry now rather than finishing backoff.
                        code = ts.diagnose(self.root)
                        self._set_reachability(code)
                        recovered = self._note_root_state(True)
                        self._notify()
                        if recovered:
                            self._maybe_auto_scan(reason="nas-back")
                        break

    def _log_unreachable(self, code):
        now = time.monotonic()
        if now - self._last_unreachable_log < _UNREACHABLE_LOG_INTERVAL:
            return
        self._last_unreachable_log = now
        clause = ts.diagnose_label(code)
        extra = f" ({clause})" if clause else ""
        self._log(f"[Offload] NAS unreachable at {self.root}{extra} - "
                  f"keeping local, will retry.")

    def _process(self, item):
        src = item["path"]
        if not os.path.exists(src):
            self._log(f"[Offload] Source gone, skipping: {src}")
            return True  # nothing to do; drop it
        root = self.root
        up = bool(root) and os.path.isdir(root)
        code = ts.diagnose(root) if root else "off"
        changed = self._set_reachability(code)
        recovered = self._note_root_state(up)
        if changed or recovered:
            self._notify()
        if not up:
            # NAS not mounted/reachable right now - keep the file, retry later.
            self._log_unreachable(code)
            return False
        dest_dir = os.path.join(
            root, _game_folder_for(src, item.get("game"), self.recording_root))
        dest = os.path.join(dest_dir, os.path.basename(src))
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except OSError as exc:
            self._log(f"[Offload] Can't create {dest_dir}: {exc}")
            return False

        # Already safely there from a previous run? Verify, then finish.
        if os.path.exists(dest) and self._same_file(src, dest):
            self._log(f"[Offload] Already on NAS, verified: {os.path.basename(src)}")
            return self._finalize(src, dest)

        part = dest + ".part"
        self._cleanup(part)
        try:
            self._transfer_to_part(src, part, dest_dir)
        except (OSError, RuntimeError) as exc:
            self._log(f"[Offload] Copy failed ({os.path.basename(src)}): {exc}")
            self._cleanup(part)
            return False

        src_hash = self._hash(src)
        dest_hash = self._hash(part)
        if not src_hash or src_hash != dest_hash:
            self._log(f"[Offload] CHECKSUM MISMATCH for {os.path.basename(src)} - "
                      "kept local, will retry.")
            self._cleanup(part)
            return False
        try:
            os.replace(part, dest)  # atomic rename over any stale dest
        except OSError as exc:
            self._log(f"[Offload] Rename failed ({os.path.basename(src)}): {exc}")
            self._cleanup(part)
            return False
        engine = "TeraCopy" if tc.available(
            self._config.get("teracopy_path")) else "built-in"
        self._log(f"[Offload] Verified on NAS via {engine}: "
                  f"{os.path.basename(src)} -> {dest_dir}")
        return self._finalize(src, dest)

    def _finalize(self, src, dest):
        """Copy is verified present on the NAS. In move mode, and only now, the
        local original may be removed."""
        if self.mode == "move":
            try:
                os.remove(src)
                self._log(f"[Offload] Local copy removed (moved to NAS): "
                          f"{os.path.basename(src)}")
            except OSError as exc:
                # The NAS copy is good; just couldn't delete local. Not fatal.
                self._log(f"[Offload] NAS copy OK but couldn't remove local "
                          f"{os.path.basename(src)}: {exc}")
        return True

    # ---- io helpers ----
    def _transfer_to_part(self, src, part, dest_dir):
        """Bulk-copy ``src`` onto ``part``. Prefer TeraCopy; fall back to SHA stream.

        TeraCopy's CLI writes into a folder under the source basename, so we
        stage into a temp subdir, then rename into the ``.part`` sidecar.
        """
        configured = self._config.get("teracopy_path") or ""
        if tc.available(configured):
            stage = os.path.join(
                dest_dir, ".nebula-tc-%s" % os.getpid())
            try:
                if os.path.isdir(stage):
                    shutil.rmtree(stage, ignore_errors=True)
                os.makedirs(stage, exist_ok=True)
                staged = tc.copy_into(
                    src, stage, configured=configured, log=self._log)
                os.replace(staged, part)
                return
            except (OSError, RuntimeError) as exc:
                self._log("[Offload] TeraCopy unavailable for this file "
                          "(%s) — using built-in copy." % exc)
                self._cleanup(part)
                try:
                    shutil.rmtree(stage, ignore_errors=True)
                except Exception:
                    pass
            finally:
                try:
                    if os.path.isdir(stage) and not os.listdir(stage):
                        os.rmdir(stage)
                except OSError:
                    pass
        self._copy_hashing(src, part)

    def _copy_hashing(self, src, dst):
        h = hashlib.sha256()
        with open(src, "rb") as fin, open(dst, "wb") as fout:
            while True:
                chunk = fin.read(_CHUNK)
                if not chunk:
                    break
                h.update(chunk)
                fout.write(chunk)
            fout.flush()
            os.fsync(fout.fileno())
        shutil.copystat(src, dst, follow_symlinks=False)
        return h.hexdigest()

    def _hash(self, path):
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(_CHUNK), b""):
                    h.update(chunk)
        except OSError:
            return None
        return h.hexdigest()

    def _same_file(self, a, b):
        try:
            if os.path.getsize(a) != os.path.getsize(b):
                return False
        except OSError:
            return False
        return self._hash(a) == self._hash(b)

    def _cleanup(self, path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def pending_count(self):
        with self._lock:
            return len(self._queue)

