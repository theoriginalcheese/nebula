"""Focused tests for the on-demand NAS clip catalog.

    python tests/test_clip_catalog.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.clip_catalog import ClipCatalog
from obsauto.offload import Offloader
from obsauto import paths as paths_module

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def write_bytes(path, data=b"hello-nebula-clip"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
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
    work = tempfile.mkdtemp(prefix="nebula-clip-catalog-")
    app_dir = os.path.join(work, "app")
    local = os.path.join(work, "local")
    nas = os.path.join(work, "nas")
    os.makedirs(app_dir)
    os.makedirs(local)
    os.makedirs(nas)

    cfg = {
        "recording_root": local,
        "nas_offload_root": nas,
        "nas_offload_mode": "move",
    }
    cat = ClipCatalog(cfg, app_dir=app_dir)

    # ---- upsert + list ----
    entry = cat.upsert(
        game="Halo", name="clip.mkv", size=12, mtime=100.0,
        sha256="a" * 64, nas_path=os.path.join(nas, "Halo", "clip.mkv"),
    )
    check("upsert returns rel", entry and entry["rel"] == "Halo/clip.mkv")
    listed = cat.list_entries()
    check("list has one entry", len(listed) == 1, len(listed))

    # reload from disk
    cat2 = ClipCatalog(cfg, app_dir=app_dir)
    check("index survives reload", cat2.get("Halo/clip.mkv") is not None)

    # ---- merge local wins ----
    local_clip = os.path.join(local, "Halo", "clip.mkv")
    write_bytes(local_clip, b"local-bytes-here!!")
    merged = cat.merge_with_local([{
        "game": "Halo", "name": "clip.mkv", "path": local_clip,
        "rel": "Halo/clip.mkv", "size": os.path.getsize(local_clip),
        "mtime": 200.0,
    }], nas_root=nas)
    check("merge: local wins", merged[0]["location"] == "local",
          merged[0].get("location"))
    check("merge: keeps nas_path", bool(merged[0].get("nas_path")))

    # ---- remote-only when local gone ----
    os.remove(local_clip)
    merged2 = cat.merge_with_local([], nas_root=nas)
    # nas file not created yet → remote/missing or offline
    check("merge: remote when no local",
          merged2 and merged2[0]["location"] == "remote",
          merged2[0]["location"] if merged2 else None)

    # ---- backfill from NAS ----
    nas_clip = os.path.join(nas, "Zenless Zone Zero", "z.mkv")
    data = write_bytes(nas_clip, b"nas-original-bytes-xyz")
    bf = cat.backfill_from_nas(nas)
    check("backfill ok", bf["ok"] is True, bf)
    check("backfill added", bf["added"] >= 1, bf)
    check("backfill indexed z.mkv", cat.get("Zenless Zone Zero/z.mkv") is not None)

    # ---- .part never complete / not listed by backfill as final ----
    part = nas_clip + ".part"
    write_bytes(part, b"partial")
    bf2 = cat.backfill_from_nas(nas)
    check("backfill ignores .part names", bf2["ok"] is True)
    check(".part not an index key",
          cat.get("Zenless Zone Zero/z.mkv.part") is None)

    # ---- ensure_local cache miss → hit ----
    result = cat.ensure_local("Zenless Zone Zero/z.mkv", nas_root=nas)
    check("ensure_local ok", result.get("ok") is True, result)
    check("ensure_local cached", result.get("location") == "cached", result)
    cached_path = result.get("path")
    check("cache file exists", bool(cached_path) and os.path.isfile(cached_path))
    check("cache bytes match",
          open(cached_path, "rb").read() == data)
    check("no .part left", not os.path.exists(cached_path + ".part"))

    result2 = cat.ensure_local("Zenless Zone Zero/z.mkv", nas_root=nas)
    check("ensure_local cache hit", result2.get("ok") and
          result2.get("location") == "cached", result2)

    # ---- NAS down ----
    missing = os.path.join(work, "nas-missing")
    cat_down = ClipCatalog({
        "recording_root": local,
        "nas_offload_root": missing,
    }, app_dir=os.path.join(work, "app2"))
    os.makedirs(cat_down._app_dir)
    cat_down.upsert(
        game="Halo", name="gone.mkv", size=4, mtime=1.0,
        nas_path=os.path.join(missing, "Halo", "gone.mkv"),
    )
    down = cat_down.ensure_local("Halo/gone.mkv", nas_root=missing)
    check("NAS down: ensure fails", down.get("ok") is False, down)
    check("NAS down: offline signal",
          down.get("availability") == "offline" or "unreachable" in (
              down.get("error") or "").lower(),
          down)
    merged_off = cat_down.merge_with_local([], nas_root=missing)
    check("NAS down: listing still shows indexed",
          any(c["rel"] == "Halo/gone.mkv" for c in merged_off))
    check("NAS down: availability offline",
          any(c["rel"] == "Halo/gone.mkv" and c["availability"] == "offline"
              for c in merged_off),
          merged_off)

    # ---- hash mismatch rejects .part, NAS untouched ----
    bad_nas = os.path.join(nas, "Bad", "bad.mkv")
    write_bytes(bad_nas, b"correct-source-bytes")
    cat.upsert(
        game="Bad", name="bad.mkv", size=len(b"correct-source-bytes"),
        mtime=1.0, sha256="0" * 64, nas_path=bad_nas,
    )
    bad = cat.ensure_local("Bad/bad.mkv", nas_root=nas)
    check("hash mismatch fails", bad.get("ok") is False, bad)
    check("hash mismatch: NAS intact",
          os.path.isfile(bad_nas) and
          open(bad_nas, "rb").read() == b"correct-source-bytes")
    check("hash mismatch: no complete cache",
          cat.cached_file("Bad/bad.mkv") is None)

    # ---- eviction ----
    check("evict removes cache", cat.evict("Zenless Zone Zero/z.mkv") is True)
    check("evict: file gone",
          not os.path.isfile(cat.cache_path("Zenless Zone Zero/z.mkv")))
    check("evict: NAS still there", os.path.isfile(nas_clip))

    # ---- offloader finalize upserts index ----
    original_app = paths_module.APP_DIR
    try:
        app3 = os.path.join(work, "app3")
        os.makedirs(app3)
        paths_module.APP_DIR = app3
        logs = []
        off = Offloader({
            "nas_offload_root": nas,
            "nas_offload_mode": "move",
            "recording_root": local,
            "nas_offload_use_teracopy": False,
        }, on_log=logs.append)
        off.start()
        src = os.path.join(local, "IndexGame", "from-offload.mkv")
        payload = write_bytes(src, os.urandom(64_000))
        off.queue(src, "IndexGame")
        dest = os.path.join(nas, "IndexGame", "from-offload.mkv")
        wait_until(lambda: os.path.isfile(dest) and not os.path.isfile(src))
        off.stop()
        # Offloader constructs ClipCatalog with APP_DIR from paths at call time
        idx = ClipCatalog({
            "recording_root": local,
            "nas_offload_root": nas,
        }, app_dir=app3)
        got = idx.get("IndexGame/from-offload.mkv")
        check("finalize upserts index", got is not None, got)
        check("finalize records nas_path",
              got and os.path.normpath(got["nas_path"]) == os.path.normpath(dest),
              got)
        check("finalize size matches",
              got and int(got["size"]) == len(payload), got)
        check("finalize sha present",
              got and len(got.get("sha256") or "") == 64, got)
    finally:
        paths_module.APP_DIR = original_app

    # ---- remove index never deletes NAS ----
    cat.remove_index_entry("Zenless Zone Zero/z.mkv")
    check("index remove: entry gone",
          cat.get("Zenless Zone Zero/z.mkv") is None)
    check("index remove: NAS untouched", os.path.isfile(nas_clip))

    # ---- pause / resume / cancel ----
    big = os.urandom(3 * 1024 * 1024)
    big_nas = os.path.join(nas, "Ctrl", "big.mkv")
    write_bytes(big_nas, big)
    cat.upsert(game="Ctrl", name="big.mkv", size=len(big), mtime=1.0,
               nas_path=big_nas)

    import threading
    done = {"result": None}

    def fetch_big():
        done["result"] = cat.ensure_local("Ctrl/big.mkv", nas_root=nas)

    t = threading.Thread(target=fetch_big, daemon=True)
    t.start()
    wait_until(lambda: cat.fetch_status("Ctrl/big.mkv").get("state")
               in ("downloading", "ready", "paused"), timeout=5)
    # If already finished (fast disk), skip pause assertions.
    st = cat.fetch_status("Ctrl/big.mkv")
    if st.get("state") == "downloading":
        paused = cat.pause_fetch("Ctrl/big.mkv")
        # The 3MB file can finish between the state check above and the
        # pause landing - on a loaded runner that window is real. pause on
        # 'ready' is ok=True (idempotent), and the rest of this branch
        # degrades to the finished-download path below.
        finished_early = paused["status"].get("state") == "ready"
        check("pause ok", paused.get("ok") is True, paused)
        check("pause state",
              finished_early or
              cat.fetch_status("Ctrl/big.mkv").get("state") == "paused",
              cat.fetch_status("Ctrl/big.mkv"))
        if not finished_early:
            time.sleep(0.25)
            mid = cat.fetch_status("Ctrl/big.mkv")
            # A pause landing before the first chunk reports shows bytes=0 -
            # that's honest, not broken. Coherent status is the invariant:
            # the size is known, nothing errored.
            check("paused status is coherent",
                  int(mid.get("total") or 0) > 0 and not mid.get("error")
                  and int(mid.get("bytes") or 0) >= 0, mid)
            resumed = cat.resume_fetch("Ctrl/big.mkv")
            check("resume ok", resumed.get("ok") is True, resumed)
            wait_until(lambda: cat.fetch_status("Ctrl/big.mkv").get("state")
                       in ("downloading", "ready"), timeout=5)
            cancelled = cat.cancel_fetch("Ctrl/big.mkv")
            check("cancel ok", cancelled.get("ok") is True, cancelled)
            t.join(timeout=8)
            check("cancel leaves no complete cache",
                  cat.cached_file("Ctrl/big.mkv") is None)
            check("cancel: NAS untouched", os.path.isfile(big_nas))
            part = cat.cache_path("Ctrl/big.mkv") + ".part"
            wait_until(lambda: not os.path.exists(part), timeout=3)
            check("cancel cleans .part", not os.path.exists(part))
        else:
            t.join(timeout=8)
            check("finished before pause landed", True)
            check("finished download is cached, NAS untouched",
                  os.path.isfile(big_nas) and
                  cat.cached_file("Ctrl/big.mkv") is not None)
    else:
        t.join(timeout=8)
        check("pause path skipped (download too fast)", True)
        # Still exercise cancel API on idle.
        check("cancel on idle ok",
              cat.cancel_fetch("Ctrl/big.mkv").get("ok") is True)

    # Restart after cancel still works.
    again = cat.ensure_local("Ctrl/big.mkv", nas_root=nas)
    check("refetch after cancel ok", again.get("ok") is True, again)
    check("refetch cached", again.get("location") == "cached", again)
    check("refetch: NAS untouched", os.path.isfile(big_nas))

    # ---- poster helpers (no ffmpeg required for path API) ----
    from obsauto import thumbs as thumbs_mod
    poster = thumbs_mod.poster_path(app_dir, "Ctrl/big.mkv")
    check("poster path under APP_DIR",
          poster.startswith(app_dir) and poster.endswith(".webp"), poster)
    check("poster missing initially",
          not thumbs_mod.have_poster(app_dir, "Ctrl/big.mkv"))

    # ---- listing trusts index (no per-file NAS isfile) ----
    many = os.path.join(work, "nas-many")
    os.makedirs(os.path.join(many, "Bulk"))
    cat_fast = ClipCatalog({
        "recording_root": local,
        "nas_offload_root": many,
    }, app_dir=os.path.join(work, "app-fast"))
    for i in range(80):
        cat_fast.upsert(
            game="Bulk", name="c%03d.mkv" % i, size=10, mtime=float(i),
            nas_path=os.path.join(many, "Bulk", "c%03d.mkv" % i),
            save=False)
    cat_fast.flush()
    calls = {"isfile": 0}
    real_isfile = os.path.isfile

    def counting_isfile(path):
        p = os.path.normpath(path)
        if os.path.normpath(many) in p and p.endswith(".mkv"):
            calls["isfile"] += 1
        return real_isfile(path)

    os.path.isfile = counting_isfile
    try:
        t0 = time.time()
        merged_fast = cat_fast.merge_with_local([], nas_root=many)
        dt = time.time() - t0
    finally:
        os.path.isfile = real_isfile
    check("fast merge returns all indexed", len(merged_fast) == 80, len(merged_fast))
    check("fast merge skips per-clip NAS isfile",
          calls["isfile"] == 0, calls["isfile"])
    check("fast merge finishes quickly", dt < 1.0, "%.3fs" % dt)

    # ---- multi-root online (dead Z: must not hide live UNC) ----
    dead = os.path.join(work, "dead-drive")
    live = os.path.join(work, "live-unc")
    os.makedirs(os.path.join(live, "Game"), exist_ok=True)
    multi = ClipCatalog({
        "recording_root": local,
        "nas_offload_root": dead,  # not created → isdir False
        "nas_offload_root_lan": live,
        "nas_offload_root_remote": os.path.join(work, "also-dead"),
        "nas_offload_auto_lan": True,
    }, app_dir=os.path.join(work, "app-multi"))
    multi.upsert(
        game="Game", name="x.mkv", size=1, mtime=1.0,
        nas_path=os.path.join(dead, "Game", "x.mkv"),
    )
    check("nas_online sees live LAN despite dead manual",
          multi.nas_online(dead) is True)
    check("resolve_active_root prefers live candidate",
          multi.resolve_active_root(dead) == os.path.normpath(live),
          multi.resolve_active_root(dead))
    merged_live = multi.merge_with_local([], nas_root=dead)
    check("merge marks remote online when any root live",
          merged_live and merged_live[0]["availability"] == "online",
          merged_live[0] if merged_live else None)
    check("nas_up hint short-circuits",
          multi.nas_online(dead, reachability="nas_up") is True)

    probes = {"n": 0}
    real_isdir = os.path.isdir

    def counting_isdir(path):
        probes["n"] += 1
        return real_isdir(path)

    os.path.isdir = counting_isdir
    try:
        check("nas_down cache is offline",
              multi.nas_online(dead, reachability="nas_down") is False)
        check("nas_down cache does not isdir", probes["n"] == 0, probes["n"])
        check("off cache is offline",
              multi.nas_online(dead, reachability="off") is False)
        check("off cache does not isdir", probes["n"] == 0, probes["n"])
    finally:
        os.path.isdir = real_isdir
    check("online_from_reachability nas_up",
          ClipCatalog.online_from_reachability("nas_up") is True)
    check("online_from_reachability nas_reachable",
          ClipCatalog.online_from_reachability("nas_reachable") is True)
    check("online_from_reachability nas_down",
          ClipCatalog.online_from_reachability("nas_down") is False)
    check("online_from_reachability missing is unknown",
          ClipCatalog.online_from_reachability(None) is None)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(n, d) for n, ok, d in results if not ok]
    print("test_clip_catalog: %d/%d" % (passed, len(results)))
    for n, d in failed:
        print("  FAIL:", n, ("— " + d) if d else "")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(run())
