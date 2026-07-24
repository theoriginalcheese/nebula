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
- Copies to a `.part` sidecar and renames on success, so a half-copied file is
  never mistaken for a complete one.
- Verifies with SHA-256 over the whole file (source hash computed during the
  copy's single read pass; destination read back and hashed). Slower than a size
  check, but this is idle-time background work and the data is irreplaceable.

Config keys (absent/blank = feature off, a pure no-op):
  nas_offload_root  destination base dir, e.g. "Z:/OBS Recordings" or a UNC path
  nas_offload_mode  "move" (delete local after verify) or "copy" (keep both)
"""

import hashlib
import json
import os
import shutil
import threading
import time

_CHUNK = 4 * 1024 * 1024  # 4 MiB


def _sanitize(name):
    # Mirror monitor.sanitize_folder_name well enough for a per-game subdir.
    keep = "".join(c if c.isalnum() or c in " -_.'()[]" else "_" for c in name)
    return keep.strip().rstrip(".") or "Unsorted"


class Offloader:
    def __init__(self, config, on_log=None):
        self._config = config
        self._log = on_log or (lambda msg: None)
        from .paths import APP_DIR
        self._queue_file = os.path.join(APP_DIR, "offload_queue.json")
        self._queue = []            # list of {"path":..., "game":...}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._worker = None
        self._on_state = None       # optional callback(pending:int, last:str)

    # ---- config (re-read each item so a live config edit is picked up) ----
    @property
    def root(self):
        return (self._config.get("nas_offload_root") or "").strip()

    @property
    def mode(self):
        return (self._config.get("nas_offload_mode") or "copy").strip().lower()

    @property
    def enabled(self):
        return bool(self.root)

    def start(self, on_state=None):
        self._on_state = on_state
        self._load_queue()
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
        if self._queue:
            self._log(f"[Offload] {len(self._queue)} clip(s) queued for the NAS.")
            self._wake.set()

    def stop(self):
        self._stop = True
        self._wake.set()

    # ---- public: enqueue a finished clip ----
    def queue(self, path, game):
        if not self.enabled or not path:
            return
        with self._lock:
            if any(item["path"] == path for item in self._queue):
                return
            self._queue.append({"path": path, "game": game or "Unsorted"})
            self._save_queue()
        self._log(f"[Offload] Queued {os.path.basename(path)} for the NAS.")
        self._notify()
        self._wake.set()

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

    def _notify(self):
        if self._on_state:
            with self._lock:
                pending = len(self._queue)
            try:
                self._on_state(pending)
            except Exception:
                pass

    # ---- worker ----
    def _run(self):
        while not self._stop:
            item = None
            with self._lock:
                if self._queue:
                    item = self._queue[0]
            if item is None:
                self._wake.wait()
                self._wake.clear()
                continue
            ok = self._process(item)
            if ok:
                with self._lock:
                    if self._queue and self._queue[0] is item:
                        self._queue.pop(0)
                    self._save_queue()
                self._notify()
            else:
                # Leave it at the head of the queue and back off before retrying;
                # the NAS is probably offline or full.
                time.sleep(30)

    def _process(self, item):
        src = item["path"]
        if not os.path.exists(src):
            self._log(f"[Offload] Source gone, skipping: {src}")
            return True  # nothing to do; drop it
        if not os.path.isdir(self.root):
            # NAS not mounted/reachable right now - keep the file, retry later.
            return False
        dest_dir = os.path.join(self.root, _sanitize(item["game"]))
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
        try:
            src_hash = self._copy_hashing(src, part)
        except OSError as exc:
            self._log(f"[Offload] Copy failed ({os.path.basename(src)}): {exc}")
            self._cleanup(part)
            return False

        dest_hash = self._hash(part)
        if src_hash != dest_hash:
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
        self._log(f"[Offload] Verified on NAS: {os.path.basename(src)} "
                  f"-> {dest_dir}")
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
