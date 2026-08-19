"""On-demand open path (no Tk / no WebView).

    python tests/test_clips_ondemand.py
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.clip_catalog import ClipCatalog

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def run():
    work = tempfile.mkdtemp(prefix="nebula-ondemand-")
    app_dir = os.path.join(work, "app")
    local = os.path.join(work, "local")
    nas = os.path.join(work, "nas")
    os.makedirs(app_dir)
    os.makedirs(local)
    os.makedirs(os.path.join(nas, "Game"))

    nas_file = os.path.join(nas, "Game", "playme.mkv")
    with open(nas_file, "wb") as f:
        f.write(b"playable-bytes-12345")

    cfg = {
        "recording_root": local,  # empty local root — Anthony's pain case
        "nas_offload_root": nas,
    }
    cat = ClipCatalog(cfg, app_dir=app_dir)
    bf = cat.backfill_from_nas(nas)
    check("empty local: backfill finds NAS clip", bf["ok"] and bf["added"] >= 1, bf)

    merged = cat.merge_with_local([], nas_root=nas)
    check("empty local: list shows remote",
          len(merged) == 1 and merged[0]["location"] == "remote", merged)
    check("empty local: availability online when NAS up",
          merged[0]["availability"] == "online", merged[0])

    opened = []

    def fake_startfile(path):
        opened.append(path)

    # Simulate spike Api.open_clip happy path without constructing Api
    # (Api.__init__ touches real config / classifier).
    result = cat.ensure_local("Game/playme.mkv", nas_root=nas)
    check("open path: ensure_local ok", result.get("ok") is True, result)
    if result.get("ok"):
        fake_startfile(result["path"])
    check("open path: startfile received cache path",
          opened and opened[0] == result.get("path"), opened)
    check("open path: cache under APP_DIR",
          opened and opened[0].startswith(app_dir), opened)
    check("open path: recording_root still empty of videos",
          not any(
              n.lower().endswith(".mkv")
              for r, _d, files in os.walk(local)
              for n in files
          ))

    # Local presence short-circuits fetch
    local_file = os.path.join(local, "Game", "local.mkv")
    os.makedirs(os.path.dirname(local_file), exist_ok=True)
    with open(local_file, "wb") as f:
        f.write(b"already-here")
    cat.upsert(game="Game", name="local.mkv", size=12, mtime=1.0,
               nas_path=os.path.join(nas, "Game", "local.mkv"))
    hit = cat.ensure_local("Game/local.mkv", nas_root=nas)
    check("local wins over NAS", hit.get("location") == "local", hit)
    check("local path returned", hit.get("path") == local_file, hit)

    # Stale .part is not treated as ready
    rel = "Game/playme.mkv"
    cache = cat.cache_path(rel)
    cat.evict(rel)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache + ".part", "wb") as f:
        f.write(b"half")
    check(".part not a cached_file", cat.cached_file(rel) is None)
    again = cat.ensure_local(rel, nas_root=nas)
    check("ensure recovers from stale .part", again.get("ok") is True, again)
    check("stale .part cleaned", not os.path.exists(cache + ".part"))

    # Avoid importing spike.app (pulls webview); assert the API surface in source.
    spike_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "spike", "app.py")
    src = open(spike_path, "r", encoding="utf-8").read()
    tree = ast.parse(src)
    api = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "Api")
    methods = {n.name for n in api.body if isinstance(n, (ast.FunctionDef,
                                                          ast.AsyncFunctionDef))}
    check("spike exports open_clip", "open_clip" in methods)
    check("spike exports clip_fetch_status", "clip_fetch_status" in methods)
    check("spike exports pause_clip_fetch", "pause_clip_fetch" in methods)
    check("spike exports resume_clip_fetch", "resume_clip_fetch" in methods)
    check("spike exports cancel_clip_fetch", "cancel_clip_fetch" in methods)
    check("spike imports ClipCatalog", "from obsauto.clip_catalog import ClipCatalog" in src)
    check("index seed never probes NAS on boot thread",
          "nas_up=False" in src and "nas_root=\"\"" in src)
    check("open uses subprocess_open not startfile",
          "subprocess_open(" in src and "os.startfile(" not in src)

    js_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "spike", "web", "app.js")
    js = open(js_path, "r", encoding="utf-8").read()
    check("no hard tick download timeout", "ticks > 600" not in js)
    check("no 'Download timed out' wall-clock alert",
          "Download timed out" not in js)
    check("stall-based fetch watchdog present", "STALL_MS" in js)
    check("stall message mentions progress",
          "no progress for 5 minutes" in js)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(n, d) for n, ok, d in results if not ok]
    print("test_clips_ondemand: %d/%d" % (passed, len(results)))
    for n, d in failed:
        print("  FAIL:", n, ("— " + d) if d else "")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(run())
