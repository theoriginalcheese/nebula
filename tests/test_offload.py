"""Tests for the NAS offloader - the safety-critical path.

The one invariant that must never break: a local recording is NOT deleted until
a byte-verified copy exists on the destination. These tests use temp dirs as a
stand-in NAS, including simulating the NAS being offline and a corrupt copy.

    python tests/test_offload.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import paths as paths_module
from obsauto.offload import Offloader

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def make_clip(path, size=1_500_000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(os.urandom(size))


def wait_until(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


def run():
    work = tempfile.mkdtemp(prefix="nebula-offload-test-")
    original_app_dir = paths_module.APP_DIR

    local = os.path.join(work, "local")
    nas = os.path.join(work, "nas")
    os.makedirs(local)
    os.makedirs(nas)

    logs = []
    _seq = [0]

    def new_offloader(cfg):
        # Each offloader gets its own APP_DIR so their persisted queues don't
        # bleed into each other. The offloader reads APP_DIR at construction
        # (`from .paths import APP_DIR`), so patch it right before.
        _seq[0] += 1
        app_dir = os.path.join(work, f"appdir{_seq[0]}")
        os.makedirs(app_dir, exist_ok=True)
        paths_module.APP_DIR = app_dir
        return Offloader(cfg, on_log=logs.append), app_dir

    # ---- move mode: copy, verify, delete local ----
    off, _ = new_offloader({"nas_offload_root": nas, "nas_offload_mode": "move"})
    off.start()

    clip = os.path.join(local, "Zenless Zone Zero", "clip1.mkv")
    make_clip(clip)
    src_bytes = open(clip, "rb").read()
    off.queue(clip, "Zenless Zone Zero")

    dest = os.path.join(nas, "Zenless Zone Zero", "clip1.mkv")
    wait_until(lambda: os.path.exists(dest) and not os.path.exists(clip))
    check("move: file arrived on NAS", os.path.exists(dest), dest)
    check("move: local deleted only after copy", not os.path.exists(clip))
    check("move: bytes identical", os.path.exists(dest) and open(dest, "rb").read() == src_bytes)
    check("move: no .part left behind", not os.path.exists(dest + ".part"))
    check("move: queue drained", off.pending_count() == 0, off.pending_count())
    off.stop()

    # ---- copy mode: keep both ----
    off2, _ = new_offloader({"nas_offload_root": nas, "nas_offload_mode": "copy"})
    off2.start()
    clip2 = os.path.join(local, "Halo", "clip2.mkv")
    make_clip(clip2)
    off2.queue(clip2, "Halo")
    dest2 = os.path.join(nas, "Halo", "clip2.mkv")
    wait_until(lambda: os.path.exists(dest2))
    check("copy: file on NAS", os.path.exists(dest2))
    check("copy: local ALSO kept", os.path.exists(clip2))
    off2.stop()

    # ---- NAS offline: local must be untouched, item retained + persisted ----
    missing_nas = os.path.join(work, "nas-that-isnt-mounted")
    logs.clear()
    off3, app_dir3 = new_offloader({"nas_offload_root": missing_nas, "nas_offload_mode": "move"})
    # Collapse the rate-limit so a second failure within the test still
    # proves we only log once until the interval elapses.
    off3._last_unreachable_log = 0.0
    off3.start()
    clip3 = os.path.join(local, "Doom", "clip3.mkv")
    make_clip(clip3)
    off3.queue(clip3, "Doom")
    time.sleep(1.2)
    check("offline NAS: local untouched", os.path.exists(clip3))
    check("offline NAS: item still queued", off3.pending_count() == 1, off3.pending_count())
    check("offline NAS: queue persisted",
          os.path.exists(os.path.join(app_dir3, "offload_queue.json")))
    unreachable_logs = [m for m in logs if "NAS unreachable" in m]
    check("offline NAS: rate-limited unreachable log",
          len(unreachable_logs) == 1, len(unreachable_logs))
    check("offline NAS: reachability code set",
          off3.reachability() in (
              "nas_down", "nas_down_tailscale_down",
              "nas_down_tailscale_missing", "nas_down_peer_offline"),
          off3.reachability())
    # A second attempt inside the interval must not spam another log line.
    before = len(unreachable_logs)
    off3._process({"path": clip3, "game": "Doom"})
    unreachable_logs = [m for m in logs if "NAS unreachable" in m]
    check("offline NAS: second failure stays rate-limited",
          len(unreachable_logs) == before, len(unreachable_logs))
    off3.stop()

    # ---- restart persistence: a new offloader on the same APP_DIR, now with a
    # reachable NAS, finishes the job left over from the offline run ----
    paths_module.APP_DIR = app_dir3
    off3b = Offloader({"nas_offload_root": nas, "nas_offload_mode": "move"},
                      on_log=logs.append)
    off3b.start()
    dest3 = os.path.join(nas, "Doom", "clip3.mkv")
    wait_until(lambda: os.path.exists(dest3) and not os.path.exists(clip3))
    check("restart: queued clip finished after NAS returned", os.path.exists(dest3))
    check("restart: local removed after verified copy", not os.path.exists(clip3))
    off3b.stop()

    # ---- corrupt destination copy: mismatch must NOT delete local ----
    off4, _ = new_offloader({"nas_offload_root": nas, "nas_offload_mode": "move"})
    real_hash = off4._hash
    clip4 = os.path.join(local, "Portal", "clip4.mkv")
    make_clip(clip4)
    dest4 = os.path.join(nas, "Portal", "clip4.mkv")

    def poisoned_hash(path):
        # Real hash for the source, deliberately wrong for the copied .part -
        # i.e. the bytes that landed on the NAS don't match what we sent.
        if path.endswith(".part"):
            return "0" * 64
        return real_hash(path)

    off4._hash = poisoned_hash
    off4.start()
    off4.queue(clip4, "Portal")
    time.sleep(1.5)
    check("corrupt copy: local NOT deleted", os.path.exists(clip4))
    check("corrupt copy: bad dest not published", not os.path.exists(dest4))
    check("corrupt copy: item still queued", off4.pending_count() == 1, off4.pending_count())
    off4.stop()

    # ---- backlog scan / sync_now ----
    logs.clear()
    rec = os.path.join(work, "recordings")
    os.makedirs(os.path.join(rec, "ScanGame"), exist_ok=True)
    clip_a = os.path.join(rec, "ScanGame", "old.mkv")
    clip_b = os.path.join(rec, "ScanGame", "fresh.mkv")
    make_clip(clip_a, size=200_000)
    make_clip(clip_b, size=200_000)
    # Make old.mkv look finished; fresh.mkv look mid-write.
    os.utime(clip_a, (time.time() - 3600, time.time() - 3600))
    os.utime(clip_b, (time.time(), time.time()))

    off5, _ = new_offloader({
        "nas_offload_root": nas,
        "nas_offload_mode": "copy",
        "recording_root": rec,
        "nas_offload_interval_hours": 24,
    })
    # Don't start the worker yet — exercise enqueue directly.
    result = off5.enqueue_missing(rec)
    check("scan: found both clips", result["found"] == 2, result)
    check("scan: queued the old clip", result["queued"] == 1, result)
    check("scan: skipped the fresh clip", result["skipped"] == 1, result)
    check("scan: pending has old only",
          off5.pending_paths() == {clip_a}, off5.pending_paths())

    # Dest already present with same size → already.
    dest_a = os.path.join(nas, "ScanGame", "old.mkv")
    os.makedirs(os.path.dirname(dest_a), exist_ok=True)
    open(dest_a, "wb").write(open(clip_a, "rb").read())
    off5b, _ = new_offloader({
        "nas_offload_root": nas,
        "nas_offload_mode": "copy",
        "recording_root": rec,
    })
    result2 = off5b.enqueue_missing(rec)
    check("scan: already on NAS skipped", result2["queued"] == 0
          and result2["already"] >= 1, result2)

    # sync_now when NAS missing.
    off6, _ = new_offloader({
        "nas_offload_root": missing_nas,
        "nas_offload_mode": "copy",
        "recording_root": rec,
    })
    bad = off6.sync_now(rec)
    check("sync_now: fails when NAS down", bad["ok"] is False, bad)
    check("sync_now: message explains", "unreachable" in (bad.get("message") or "").lower(),
          bad.get("message"))

    # sync_now happy path.
    off7, _ = new_offloader({
        "nas_offload_root": nas,
        "nas_offload_mode": "copy",
        "recording_root": rec,
        "nas_offload_interval_hours": 24,
    })
    # New clip not on NAS, old enough.
    clip_c = os.path.join(rec, "ScanGame", "need.mkv")
    make_clip(clip_c, size=120_000)
    os.utime(clip_c, (time.time() - 3600, time.time() - 3600))
    good = off7.sync_now(rec)
    check("sync_now: ok when NAS up", good["ok"] is True, good)
    check("sync_now: queued something", good.get("queued", 0) >= 1, good)
    check("sync_now: status shows last message",
          bool(off7.status_snapshot().get("message")), off7.status_snapshot())
    check("auto due after never scanned", off7._auto_scan_due() is False)  # just scanned
    off7._last_scan_at = time.time() - 25 * 3600
    check("auto due after 25h", off7._auto_scan_due() is True)
    off7._config["nas_offload_interval_hours"] = 0
    check("auto off when interval 0", off7._auto_scan_due() is False)

    # NAS folders must mirror the local game folder name (not a re-sanitised
    # display name), and Sync scans in game-folder order.
    from obsauto.offload import _game_folder_for, _sanitize
    from obsauto.monitor import sanitize_folder_name

    check("sanitize matches monitor",
          _sanitize("Foo:Bar?") == sanitize_folder_name("Foo:Bar?"))

    fold_root = os.path.join(work, "fold-local")
    os.makedirs(os.path.join(fold_root, "Real Folder"), exist_ok=True)
    fold_clip = os.path.join(fold_root, "Real Folder", "x.mkv")
    make_clip(fold_clip, size=80_000)
    check("game folder from path",
          _game_folder_for(fold_clip, "Other Name", fold_root) == "Real Folder")
    check("game folder fallback",
          _game_folder_for(fold_clip, "Other:Name", "") == sanitize_folder_name("Other:Name"))

    off8, _ = new_offloader({
        "nas_offload_root": nas,
        "nas_offload_mode": "copy",
        "recording_root": fold_root,
    })
    off8.start()
    off8.queue(fold_clip, "Wrong Display Name")
    dest_fold = os.path.join(nas, "Real Folder", "x.mkv")
    wait_until(lambda: os.path.exists(dest_fold))
    check("queue uses disk folder on NAS", os.path.exists(dest_fold), dest_fold)
    check("queue did not invent display folder",
          not os.path.exists(os.path.join(nas, "Wrong Display Name", "x.mkv")))
    off8.stop()

    multi = os.path.join(work, "multi-rec")
    for g, names in (("Beta", ("b.mkv", "a.mkv")), ("Alpha", ("z.mkv",))):
        for n in names:
            make_clip(os.path.join(multi, g, n), size=40_000)
    ordered = list(Offloader(
        {"nas_offload_root": nas, "recording_root": multi},
        on_log=logs.append).iter_local_clips(multi))
    check("scan order by game then file",
          [os.path.basename(p) for p, _ in ordered] == ["z.mkv", "a.mkv", "b.mkv"]
          and [g for _, g in ordered] == ["Alpha", "Beta", "Beta"],
          ordered)

    # Bare drive letter must become a real root, not a cwd-relative "Z:Game".
    bare = Offloader({"nas_offload_root": "Z:"}, on_log=logs.append)
    check("bare drive root normalised",
          bare.root.lower() in ("z:\\", "z:/") or bare.root.endswith(("\\", "/")),
          repr(bare.root))
    check("bare drive joins with sep",
          "\\" in os.path.join(bare.root, "Game") or "/" in os.path.join(bare.root, "Game"),
          os.path.join(bare.root, "Game"))

    # ---- auto LAN / remote path pick (no Tailscale CLI required) ----
    lan_dir = os.path.join(work, "lan-root")
    remote_dir = os.path.join(work, "remote-root")
    os.makedirs(lan_dir)
    os.makedirs(remote_dir)
    from obsauto import tailscale as ts_mod
    real_home = ts_mod.home_lan_preferred
    try:
        ts_mod.home_lan_preferred = lambda root, peer="nas": True
        off_auto, _ = new_offloader({
            "nas_offload_root": "",
            "nas_offload_auto_lan": True,
            "nas_offload_root_lan": lan_dir,
            "nas_offload_root_remote": remote_dir,
        })
        check("auto: picks LAN when home", off_auto.root == os.path.normpath(lan_dir),
              off_auto.root)
        check("auto: path_mode lan", off_auto.path_mode().startswith("lan"),
              off_auto.path_mode())

        ts_mod.home_lan_preferred = lambda root, peer="nas": False
        off_auto.refresh()
        check("auto: picks remote when away",
              off_auto.root == os.path.normpath(remote_dir), off_auto.root)
        check("auto: path_mode remote", off_auto.path_mode().startswith("remote"),
              off_auto.path_mode())

        real_cur = ts_mod.peer_cur_addr
        ts_mod.peer_cur_addr = lambda host, st=None: None
        off_fb, _ = new_offloader({
            "nas_offload_root": "",
            "nas_offload_auto_lan": True,
            "nas_offload_root_lan": lan_dir,
            "nas_offload_root_remote": os.path.join(work, "missing-remote"),
        })
        check("auto: LAN when Tailscale remote is missing",
              off_fb.root == os.path.normpath(lan_dir), off_fb.root)
        ts_mod.peer_cur_addr = real_cur

        off_manual, _ = new_offloader({
            "nas_offload_root": nas,
            "nas_offload_auto_lan": False,
            "nas_offload_root_lan": lan_dir,
            "nas_offload_root_remote": remote_dir,
        })
        check("auto off: desktop uses manual root",
              off_manual.root == os.path.normpath(nas), off_manual.root)
        check("auto off: path_mode manual", off_manual.path_mode() == "manual")
    finally:
        ts_mod.home_lan_preferred = real_home

    paths_module.APP_DIR = original_app_dir


run()
passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<42} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
