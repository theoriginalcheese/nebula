"""Manual delete in the v4 Clips pane: no verified second copy, no delete.

The pane used to gate only on "is this clip still in the offload queue?".
That is a weaker question than it sounds: a clip that was recorded while
offloading was off was never queued, and a queue file that came back empty
after a bad shutdown also says "nothing pending". Either way the local file
was the only copy, and one confirm dialog later it was gone - hard-deleted,
not recycled.

Now, with offloading on, the local copy goes only when the indexed NAS copy
answers and is the same size; and the file goes to the Recycle Bin wherever
one exists. A hard delete is used only when the NAS copy is proven, and never
for the only copy of anything.

    python tests/test_delete_gate.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import recycle
from obsauto.clip_catalog import ClipCatalog
from spike import app as app_mod
from spike.app import Api

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-60s %s" % ("PASS" if ok else "FAIL", name, detail))


class FakeOffloader:
    def __init__(self, enabled=True, pending=()):
        self.enabled = enabled
        self._pending = set(pending)
        self.root = ""

    def pending_paths(self):
        return set(self._pending)


class Recycled:
    """Stand-in for the shell: records what would have gone to the bin."""

    def __init__(self, available=True):
        self.available = available
        self.sent = []

    def recyclable(self, path):
        return self.available

    def to_recycle_bin(self, path):
        self.sent.append(path)
        os.remove(path)
        return True


def _api(work, offloader, nas_path_for_clip=""):
    rec_root = os.path.join(work, "rec")
    clip_path = os.path.join(rec_root, "Halo", "clip.mkv")
    os.makedirs(os.path.dirname(clip_path), exist_ok=True)
    with open(clip_path, "wb") as f:
        f.write(b"x" * 4096)

    api = Api.__new__(Api)
    api.cfg = {"recording_root": rec_root, "nas_offload_root": ""}
    api._host = None
    api._clips_error = None
    api._clips_root = rec_root
    api._clips_backfill_busy = False
    api._clip_durations = {}
    api._thumb_data_cache = {}
    api._clips_scanned_at = 0.0
    api._clips_cache = [{
        "game": "Halo", "name": "clip.mkv", "path": os.path.normpath(clip_path),
        "rel": "Halo/clip.mkv", "size": 4096, "mtime": 1.0,
        "location": "local", "availability": "online",
        "nas_path": nas_path_for_clip,
    }]
    api._clip_catalog = ClipCatalog(api.cfg, app_dir=work)
    api._clip_catalog.resolve_nas_path = lambda rel, root=None: None
    api._seed_clips_from_index = lambda: None
    api._ensure_clips_scan = lambda force=False: None
    api._offloader = lambda: offloader
    api._api_log = lambda m: None
    return api, clip_path


def run():
    real_recyclable = recycle.recyclable
    real_to_bin = recycle.to_recycle_bin
    real_purge = app_mod.thumbs.purge
    app_mod.thumbs.purge = lambda root, path: None
    try:
        # ---- offload on, clip never queued, no NAS copy -> refused ----------
        work = tempfile.mkdtemp(prefix="nebula-delgate-")
        bin_ = Recycled()
        recycle.recyclable, recycle.to_recycle_bin = bin_.recyclable, bin_.to_recycle_bin
        api, clip = _api(work, FakeOffloader(enabled=True))
        res = api.delete_clip(clip, confirm=True)
        check("offload on + no NAS record: refused",
              res.get("refused") is True and not res.get("ok"), res)
        check("  ...and says why",
              "no NAS copy is recorded" in res.get("message", ""), res.get("message"))
        check("  ...local file untouched", os.path.exists(clip))
        check("  ...nothing recycled either", bin_.sent == [])

        # ---- offload on, NAS copy recorded but not reachable -> refused -------
        work = tempfile.mkdtemp(prefix="nebula-delgate-")
        api, clip = _api(work, FakeOffloader(enabled=True),
                         nas_path_for_clip=os.path.join(work, "nas-gone", "Halo", "clip.mkv"))
        res = api.delete_clip(clip, confirm=True)
        check("offload on + NAS copy missing: refused", res.get("refused") is True, res)
        check("  ...names the NAS as the problem",
              "isn't reachable" in res.get("message", ""), res.get("message"))
        check("  ...local file untouched", os.path.exists(clip))

        # ---- offload on, NAS copy present but a different size -> refused -----
        work = tempfile.mkdtemp(prefix="nebula-delgate-")
        nas_clip = os.path.join(work, "nas", "Halo", "clip.mkv")
        os.makedirs(os.path.dirname(nas_clip))
        with open(nas_clip, "wb") as f:
            f.write(b"x" * 100)    # a stub, not the recording
        api, clip = _api(work, FakeOffloader(enabled=True), nas_path_for_clip=nas_clip)
        res = api.delete_clip(clip, confirm=True)
        check("offload on + NAS copy wrong size: refused", res.get("refused") is True, res)
        check("  ...says the sizes differ",
              "different size" in res.get("message", ""), res.get("message"))
        check("  ...local file untouched", os.path.exists(clip))

        # ---- offload on, verified NAS copy -> allowed, via Recycle Bin --------
        work = tempfile.mkdtemp(prefix="nebula-delgate-")
        nas_clip = os.path.join(work, "nas", "Halo", "clip.mkv")
        os.makedirs(os.path.dirname(nas_clip))
        with open(nas_clip, "wb") as f:
            f.write(b"x" * 4096)
        bin_ = Recycled()
        recycle.recyclable, recycle.to_recycle_bin = bin_.recyclable, bin_.to_recycle_bin
        api, clip = _api(work, FakeOffloader(enabled=True), nas_path_for_clip=nas_clip)
        ask = api.delete_clip(clip, confirm=False)
        check("verified copy: asks first", ask.get("need_confirm") is True, ask)
        check("  ...confirm text says Recycle Bin",
              "Recycle Bin" in ask.get("message", "") and ask.get("via") == "recycle", ask)
        res = api.delete_clip(clip, confirm=True)
        check("verified copy: delete goes ahead", res.get("ok") is True, res)
        check("  ...through the Recycle Bin", bin_.sent == [os.path.normpath(clip)], bin_.sent)
        check("  ...local file gone", not os.path.exists(clip))
        check("  ...NAS copy untouched", os.path.exists(nas_clip))
        check("  ...index still knows the NAS copy",
              (api._clip_catalog.get("Halo/clip.mkv") or {}).get("nas_path") == nas_clip,
              api._clip_catalog.get("Halo/clip.mkv"))

        # ---- verified NAS copy, volume has no bin -> hard delete is allowed ---
        work = tempfile.mkdtemp(prefix="nebula-delgate-")
        nas_clip = os.path.join(work, "nas", "Halo", "clip.mkv")
        os.makedirs(os.path.dirname(nas_clip))
        with open(nas_clip, "wb") as f:
            f.write(b"x" * 4096)
        bin_ = Recycled(available=False)
        recycle.recyclable, recycle.to_recycle_bin = bin_.recyclable, bin_.to_recycle_bin
        api, clip = _api(work, FakeOffloader(enabled=True), nas_path_for_clip=nas_clip)
        ask = api.delete_clip(clip, confirm=False)
        check("verified copy, no bin: confirm says hard delete + verified",
              ask.get("via") == "remove" and "verified" in ask.get("message", ""), ask)
        res = api.delete_clip(clip, confirm=True)
        check("verified copy, no bin: allowed", res.get("ok") is True and res.get("via") == "remove", res)
        check("  ...local file gone", not os.path.exists(clip))

        # ---- offload off, bin available -> recycled without NAS proof ---------
        work = tempfile.mkdtemp(prefix="nebula-delgate-")
        bin_ = Recycled()
        recycle.recyclable, recycle.to_recycle_bin = bin_.recyclable, bin_.to_recycle_bin
        api, clip = _api(work, FakeOffloader(enabled=False))
        res = api.delete_clip(clip, confirm=True)
        check("offload off: recycle is allowed", res.get("ok") is True and res.get("via") == "recycle", res)
        check("  ...went to the bin", bin_.sent == [os.path.normpath(clip)], bin_.sent)

        # ---- offload off, no bin, no NAS copy -> the only copy is never destroyed
        work = tempfile.mkdtemp(prefix="nebula-delgate-")
        bin_ = Recycled(available=False)
        recycle.recyclable, recycle.to_recycle_bin = bin_.recyclable, bin_.to_recycle_bin
        api, clip = _api(work, FakeOffloader(enabled=False))
        res = api.delete_clip(clip, confirm=True)
        check("offload off + no bin + no NAS: refused", res.get("refused") is True, res)
        check("  ...explains the only-copy rule",
              "only copy" in res.get("message", ""), res.get("message"))
        check("  ...local file untouched", os.path.exists(clip))

        # ---- still-queued clip keeps the original refusal ---------------------
        work = tempfile.mkdtemp(prefix="nebula-delgate-")
        bin_ = Recycled()
        recycle.recyclable, recycle.to_recycle_bin = bin_.recyclable, bin_.to_recycle_bin
        api, clip = _api(work, FakeOffloader(enabled=True, pending=[os.path.normpath(clip_path_of(work))]))
        res = api.delete_clip(clip, confirm=True)
        check("queued clip: refused as before",
              res.get("refused") is True and "verified yet" in res.get("message", ""), res)
        check("  ...local file untouched", os.path.exists(clip))
    finally:
        recycle.recyclable = real_recyclable
        recycle.to_recycle_bin = real_to_bin
        app_mod.thumbs.purge = real_purge


def clip_path_of(work):
    return os.path.join(work, "rec", "Halo", "clip.mkv")


if __name__ == "__main__":
    run()
    print("\n%s (%d checks, %d failed)" % (
        "ALL PASS" if not FAIL else "FAILURES PRESENT", len(PASS) + len(FAIL), len(FAIL)))
    sys.exit(1 if FAIL else 0)
