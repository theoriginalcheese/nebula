"""The offloader must never replace footage that isn't the clip it's copying,
and its state files must survive a crash mid-write.

Two ways a NAS file used to be destroyed without anyone deleting anything:

* Same basename, different bytes. ``_process`` hashed the *.part* against the
  *source*, found them equal (of course), and ``os.replace``'d over whatever
  already sat at ``dest``. A recovered clip, a manual rename, or OBS restarted
  inside the same second was enough. In move mode the local original then went
  too, so both copies of the older recording were gone.
* ``offload_queue.json`` was written with a plain ``open("w")``. Killed
  mid-write, it came back empty - and an empty queue is exactly what the Clips
  pane reads as "nothing is waiting on a verified copy, delete away".

    python tests/test_offload_collision.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import classifier as classifier_mod
from obsauto import paths as paths_module
from obsauto.atomic_json import read_json, write_json_atomic
from obsauto.offload import Offloader

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def make_clip(path, size=300_000, seed=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = os.urandom(size) if seed is None else (seed * (size // len(seed) + 1))[:size]
    with open(path, "wb") as f:
        f.write(data)
    return data


def wait_until(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def run():
    work = tempfile.mkdtemp(prefix="nebula-offload-collision-")
    original_app_dir = paths_module.APP_DIR
    logs = []
    seq = [0]

    def new_offloader(cfg):
        seq[0] += 1
        app_dir = os.path.join(work, "appdir%d" % seq[0])
        os.makedirs(app_dir, exist_ok=True)
        paths_module.APP_DIR = app_dir
        return Offloader(cfg, on_log=logs.append), app_dir

    local = os.path.join(work, "local")
    nas = os.path.join(work, "nas")
    os.makedirs(local)
    os.makedirs(nas)

    try:
        # ---- 1. divergent same-name file on the NAS is kept, not replaced ----
        older = make_clip(os.path.join(nas, "Halo", "2026-01-01 10-00-00.mkv"),
                          seed=b"OLDER-SESSION-")
        src = os.path.join(local, "Halo", "2026-01-01 10-00-00.mkv")
        newer = make_clip(src, seed=b"NEWER-SESSION-")
        check("setup: same name, different bytes", older != newer)

        off, _ = new_offloader({"nas_offload_root": nas, "nas_offload_mode": "move"})
        off.start()
        off.queue(src, "Halo")
        alias = os.path.join(nas, "Halo", "2026-01-01 10-00-00 (2).mkv")
        wait_until(lambda: os.path.exists(alias) and not os.path.exists(src))
        off.stop()

        original = os.path.join(nas, "Halo", "2026-01-01 10-00-00.mkv")
        check("collision: the NAS file that was already there is untouched",
              os.path.exists(original) and open(original, "rb").read() == older)
        check("collision: the new clip landed under an alias",
              os.path.exists(alias), alias)
        check("collision: alias bytes are the new clip",
              os.path.exists(alias) and open(alias, "rb").read() == newer)
        check("collision: local removed only once the alias was verified",
              not os.path.exists(src))
        check("collision: no .part left behind",
              not os.path.exists(alias + ".part") and not os.path.exists(original + ".part"))
        check("collision: user is told both were kept",
              any("different content" in m and "keeping both" in m for m in logs),
              [m for m in logs if "Offload" in m][-3:])

        # ---- 2. a byte-identical copy already there is just finalised ----
        logs.clear()
        src2 = os.path.join(local, "Doom", "clip.mkv")
        data2 = make_clip(src2)
        make_clip(os.path.join(nas, "Doom", "clip.mkv"), seed=data2[:64])
        # make it truly identical
        with open(os.path.join(nas, "Doom", "clip.mkv"), "wb") as f:
            f.write(data2)
        off2, _ = new_offloader({"nas_offload_root": nas, "nas_offload_mode": "copy"})
        off2.start()
        off2.queue(src2, "Doom")
        wait_until(lambda: off2.pending_count() == 0)
        off2.stop()
        check("identical: no alias created for a verified duplicate",
              not os.path.exists(os.path.join(nas, "Doom", "clip (2).mkv")))
        check("identical: reported as already on NAS",
              any("Already on NAS, verified" in m for m in logs), logs[-3:])

        # ---- 3. the scan recognises a clip that lives under an alias ----
        # (otherwise Sync now would re-queue it forever, minting (3), (4)...)
        src3 = os.path.join(local, "Halo", "2026-01-01 10-00-00.mkv")
        make_clip(src3, seed=b"NEWER-SESSION-")   # same bytes as the alias
        off3, _ = new_offloader({"nas_offload_root": nas, "nas_offload_mode": "copy"})
        old = os.path.getmtime(src3) - 600
        os.utime(src3, (old, old))
        check("scan: alias counts as present",
              off3._dest_present(src3, "Halo") is True)
        report = off3.enqueue_missing(local)
        check("scan: aliased clip is not re-queued",
              report["queued"] == 0 and off3.pending_count() == 0, report)
        os.remove(src3)

        # ---- 4. every alias taken by foreign bytes -> keep local, say so ----
        from obsauto import offload as offload_mod
        real_max = offload_mod._MAX_DEST_ALIASES
        offload_mod._MAX_DEST_ALIASES = 2
        try:
            logs.clear()
            src4 = os.path.join(local, "Halo", "2026-01-01 10-00-00.mkv")
            make_clip(src4, seed=b"THIRD-SESSION-")
            off4, _ = new_offloader({"nas_offload_root": nas, "nas_offload_mode": "move"})
            done = off4._process({"path": src4, "game": "Halo"})
            check("exhausted: item is retained for retry", done is False)
            check("exhausted: local kept", os.path.exists(src4))
            check("exhausted: nothing on the NAS was replaced",
                  open(original, "rb").read() == older
                  and open(alias, "rb").read() == newer)
            check("exhausted: explained in the log",
                  any("taken by a different file" in m for m in logs), logs[-2:])
            os.remove(src4)
        finally:
            offload_mod._MAX_DEST_ALIASES = real_max

        # ---- 5. queue + state are written atomically ----
        off5, app_dir5 = new_offloader({
            "nas_offload_root": os.path.join(work, "nas-offline"),
            "nas_offload_mode": "move"})
        src5 = os.path.join(local, "Zelda", "clip5.mkv")
        make_clip(src5, size=1000)
        off5.queue(src5, "Zelda")
        qfile = os.path.join(app_dir5, "offload_queue.json")
        check("atomic: queue persisted", os.path.exists(qfile))
        check("atomic: no queue .tmp left over", not os.path.exists(qfile + ".tmp"))
        off5._mark_scan()
        sfile = os.path.join(app_dir5, "offload_state.json")
        check("atomic: state persisted", os.path.exists(sfile))
        check("atomic: no state .tmp left over", not os.path.exists(sfile + ".tmp"))

        # ---- 6. a corrupt queue is quarantined + logged, never read as empty ----
        with open(qfile, "w", encoding="utf-8") as f:
            f.write('[{"path": "')   # truncated mid-write
        logs.clear()
        off6 = Offloader({"nas_offload_root": nas, "nas_offload_mode": "move"},
                         on_log=logs.append)
        off6._load_queue()
        check("corrupt: moved aside as .corrupt", os.path.exists(qfile + ".corrupt"))
        check("corrupt: logged, not swallowed",
              any("offload queue unreadable" in m for m in logs), logs[-2:])
        check("corrupt: fresh valid queue written in its place",
              os.path.exists(qfile) and json.load(open(qfile, encoding="utf-8")) == [])

        # ---- 7. write_json_atomic / read_json contract ----
        target = os.path.join(work, "state.json")
        write_json_atomic(target, {"a": 1})
        check("helper: writes readable JSON", read_json(target, None) == {"a": 1})
        check("helper: no tmp after success", not os.path.exists(target + ".tmp"))
        check("helper: missing file -> default quietly",
              read_json(os.path.join(work, "nope.json"), "dflt") == "dflt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("{not json")
        msgs = []
        check("helper: corrupt -> default", read_json(target, [], log=msgs.append) == [])
        check("helper: corrupt is quarantined", os.path.exists(target + ".corrupt"))
        check("helper: corrupt is reported", msgs and "unreadable" in msgs[0], msgs)
        write_json_atomic(target, {"b": 2})
        check("helper: next save starts clean", read_json(target, None) == {"b": 2})

        # ---- 8. games.json goes through the same door ----
        gfile = os.path.join(work, "games.json")
        real_data_file = classifier_mod.DATA_FILE
        classifier_mod.DATA_FILE = gfile
        try:
            c = classifier_mod.Classifier.__new__(classifier_mod.Classifier)
            c.log = lambda msg: None
            c.on_saved = lambda data: None
            c._data = {"games": {"halo.exe": {"display_name": "Halo"}},
                       "non_games": {}}
            c._save()
            check("classifier: games.json written",
                  json.load(open(gfile, encoding="utf-8"))["games"]["halo.exe"]["display_name"] == "Halo")
            check("classifier: no games.json.tmp left", not os.path.exists(gfile + ".tmp"))
        finally:
            classifier_mod.DATA_FILE = real_data_file
    finally:
        paths_module.APP_DIR = original_app_dir


run()
passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<58} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
