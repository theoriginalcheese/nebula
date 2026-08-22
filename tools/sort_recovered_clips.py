"""One-shot sorter for OBS-recovered / unsorted clips (own project).

Uses the local vision LLM to guess the game from keyframes, escalating the
frame count when confidence is low. Moves files into ``<NAS>/<Game>/`` with
OBS-style datetime names and updates ``clip_index.json``.

Default is dry-run (no moves). Sacred footage: ``--apply`` only renames/moves
within the NAS tree; it never deletes without a destination.

Examples::

    python tools/sort_recovered_clips.py --limit 5
    python tools/sort_recovered_clips.py --limit 5 --apply
    python tools/sort_recovered_clips.py --apply --resume --until-empty --keep-loaded

Local LLM: ``http://127.0.0.1:8080`` model ``vision``.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from obsauto import thumbs
from obsauto.classifier import Classifier
from obsauto.clip_catalog import ClipCatalog
from obsauto.config import load_config
from obsauto.monitor import sanitize_folder_name
from obsauto.paths import APP_DIR

LLM_BASE = os.environ.get("NEBULA_LLM_BASE", "http://127.0.0.1:8080")
VISION_MODEL = os.environ.get("NEBULA_VISION_MODEL", "vision")
FRAME_STEPS = (4, 8, 12, 16)
STATE_PATH = os.path.join(APP_DIR, "sort_recovered_state.json")
WORK_DIR = os.path.join(APP_DIR, ".nebula", "sort_frames")
UNSORTABLE = "_Unsortable"
# Clips we will not keep retrying forever (corrupt / no picture).
_EXTRACT_FAIL_RE = re.compile(r"only \d+/\d+ frames extracted", re.I)
_BLACK_RE = re.compile(r"black|no visual|uniform dark", re.I)
_NOT_GAME_RE = re.compile(
    r"not a (?:pc )?game|not (?:a )?recording of a|living room|"
    r"spotify|discord desktop|web browser|youtube",
    re.I,
)


def _log(msg):
    print(msg, flush=True)


def game_labels(classifier, nas_root=""):
    """Unique display names for folder targets (+ Unknown)."""
    names = set()
    snap = classifier.snapshot() or {}
    for meta in (snap.get("games") or {}).values():
        if isinstance(meta, dict):
            dn = (meta.get("display_name") or "").strip()
        else:
            dn = str(meta or "").strip()
        if dn:
            names.add(sanitize_folder_name(dn))
    # Folders already on the NAS (minus recovery / unsortable buckets).
    skip = {
        "obs-recovered", "unsorted", "unknown", UNSORTABLE.lower(),
    }
    if nas_root and os.path.isdir(nas_root):
        try:
            for name in os.listdir(nas_root):
                path = os.path.join(nas_root, name)
                if os.path.isdir(path) and name.lower() not in skip:
                    names.add(sanitize_folder_name(name))
        except OSError:
            pass
    return sorted(names) or ["Unknown"]


def recovered_entries(catalog, nas_root):
    """Catalog hits under OBS-recovered/Unsorted, plus loose files on disk."""
    out = []
    seen = set()
    for e in catalog.list_entries():
        game = (e.get("game") or "").strip()
        if game.lower() not in ("obs-recovered", "unsorted", "unknown"):
            continue
        nas = (e.get("nas_path") or "").strip()
        if not nas and nas_root:
            nas = os.path.join(nas_root, game, e.get("name") or "")
        if not nas or not os.path.isfile(nas):
            alt = os.path.join(nas_root or "", "OBS-recovered", e.get("name") or "")
            if os.path.isfile(alt):
                nas = alt
            else:
                continue
        nas = os.path.normpath(nas)
        key = nas.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({**e, "nas_path": nas})

    folder = os.path.join(nas_root or "", "OBS-recovered")
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith((".mkv", ".mp4", ".mov", ".m4v")):
                continue
            path = os.path.normpath(os.path.join(folder, name))
            if not os.path.isfile(path) or path.lower() in seen:
                continue
            seen.add(path.lower())
            try:
                st = os.stat(path)
                size, mtime = st.st_size, st.st_mtime
            except OSError:
                size, mtime = 0, 0
            out.append({
                "name": name,
                "game": "OBS-recovered",
                "rel": f"OBS-recovered/{name}",
                "nas_path": path,
                "size": size,
                "mtime": mtime,
                "sha256": "",
            })
    out.sort(key=lambda x: x.get("name") or "")
    return out


def extract_n_frames(clip_path, n, dest_dir):
    """Evenly spaced JPEG keyframes → list of paths."""
    exe = thumbs._tool("ffmpeg")
    if not exe or not os.path.isfile(clip_path):
        return []
    duration = thumbs.duration_of(clip_path)
    if not duration or duration <= 0:
        # Still try a few absolute offsets — some recovered files lack tags.
        duration = 30.0
    os.makedirs(dest_dir, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "_", os.path.splitext(os.path.basename(clip_path))[0])
    made = []
    for i in range(n):
        frac = (i + 0.5) / n
        t = max(0.05, min(max(duration - 0.05, 0.1), duration * frac))
        target = os.path.join(dest_dir, f"{stem}_f{n}_{i + 1}.jpg")
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            made.append(target)
            continue
        result = thumbs._run([
            exe, "-y", "-loglevel", "error",
            "-ss", f"{t:.3f}", "-i", clip_path,
            "-frames:v", "1", "-vf", "scale=512:-1",
            "-q:v", "4", target,
        ], timeout=60)
        if result and result.returncode == 0 and os.path.isfile(target):
            made.append(target)
            continue
        # Fallback: decode from start (helps broken timestamps).
        result = thumbs._run([
            exe, "-y", "-loglevel", "error",
            "-i", clip_path,
            "-vf", f"select=eq(n\\,{i * 8}),scale=512:-1",
            "-frames:v", "1", "-q:v", "4", target,
        ], timeout=90)
        if result and result.returncode == 0 and os.path.isfile(target):
            made.append(target)
    return made


def _b64_data_url(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


def ensure_vision_loaded(llm_base, timeout=600):
    """Force llama-swap to load ``vision`` so the UI shows it running."""
    base = llm_base.rstrip("/")
    _log("Warming vision model (so /running + UI show it)…")
    body = {
        "model": VISION_MODEL,
        "messages": [
            {"role": "user", "content": "Reply with exactly: ok"},
        ],
        "temperature": 0,
        "max_tokens": 8,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
    except Exception as exc:
        _log("  vision warm-up failed: %s" % exc)
        return False
    try:
        with urllib.request.urlopen(f"{base}/running", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        running = data.get("running") or []
        ids = [r.get("model") for r in running if isinstance(r, dict)]
        _log("  /running → %s" % (ids or running))
        return VISION_MODEL in ids or any("vision" in str(x).lower() for x in ids)
    except Exception as exc:
        _log("  could not read /running: %s" % exc)
        return True  # request succeeded; UI may still catch up


def vision_classify(frame_paths, labels, timeout=180, llm_base=None,
                    allow_freeform=True):
    """Ask local vision model which game this clip is. Returns dict."""
    base = (llm_base or LLM_BASE).rstrip("/")
    label_blob = ", ".join(labels[:120])
    freeform_rule = (
        "Prefer a label from the list. If the game is clearly identifiable but "
        "NOT in the list, use the common English title (e.g. Starfield, "
        "Helldivers 2, Beat Saber). Use Unknown only if you truly cannot tell."
        if allow_freeform else
        "Pick EXACTLY one label from this list (or Unknown)."
    )
    content = [
        {
            "type": "text",
            "text": (
                "You identify which PC game a recording shows.\n"
                f"{freeform_rule}\n"
                f"Known labels: {label_blob}\n\n"
                "Reply with JSON only, no markdown:\n"
                '{"game":"<label or title>","confidence":0.0,"reason":"<short>"}\n'
                "confidence is 0..1."
            ),
        }
    ]
    for path in frame_paths:
        content.append({
            "type": "image_url",
            "image_url": {"url": _b64_data_url(path)},
        })
    body = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
        "max_tokens": 800,
        # Qwen3 otherwise burns the budget on reasoning_content and leaves
        # message.content empty (finish_reason=length).
        "chat_template_kwargs": {"enable_thinking": False},
    }
    _log("  … calling vision (%d frame(s))…" % len(frame_paths))
    req = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"game": "Unknown", "confidence": 0.0, "reason": f"llm error: {exc}"}
    text = ""
    try:
        msg = payload["choices"][0]["message"] or {}
        text = (msg.get("content") or msg.get("reasoning_content") or "").strip()
    except (KeyError, IndexError, TypeError):
        return {"game": "Unknown", "confidence": 0.0, "reason": "bad llm response"}
    matches = list(re.finditer(r"\{[^{}]*\"game\"[^{}]*\}", text, re.S))
    if matches:
        text = matches[-1].group(0)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return {"game": "Unknown", "confidence": 0.0,
                    "reason": (text or "empty")[:160]}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {"game": "Unknown", "confidence": 0.0, "reason": text[:160]}
    game = sanitize_folder_name(str(data.get("game") or "Unknown"))
    try:
        conf = float(data.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    if game.lower() == "unknown":
        game = "Unknown"
    elif game not in labels:
        low = {x.lower(): x for x in labels}
        if game.lower() in low:
            game = low[game.lower()]
        elif not allow_freeform:
            game = "Unknown"
        # else keep freeform sanitized title
    return {
        "game": game if game else "Unknown",
        "confidence": conf,
        "reason": str(data.get("reason") or "")[:200],
    }


def classify_with_escalation(clip_path, labels, min_confidence, work_root,
                             llm_base=None, allow_freeform=True):
    last = {"game": "Unknown", "confidence": 0.0, "reason": "", "frames": 0}
    for n in FRAME_STEPS:
        dest = os.path.join(work_root, f"n{n}")
        frames = extract_n_frames(clip_path, n, dest)
        if len(frames) < max(1, n // 2):
            last = {
                "game": "Unknown",
                "confidence": 0.0,
                "reason": f"only {len(frames)}/{n} frames extracted",
                "frames": len(frames),
            }
            continue
        got = vision_classify(
            frames, labels, llm_base=llm_base, allow_freeform=allow_freeform,
        )
        got["frames"] = len(frames)
        last = got
        if got["confidence"] >= min_confidence:
            return got
        _log("  … low confidence (%.2f) with %d frames — escalating"
             % (got["confidence"], n))
    return last


def is_unsortable(got):
    reason = str(got.get("reason") or "")
    if _EXTRACT_FAIL_RE.search(reason):
        return True
    if got.get("frames", 0) == 0:
        return True
    # Model often returns conf=0 for "all black" — still unsortable.
    if _BLACK_RE.search(reason):
        return True
    # High-confidence or clearly-worded "this isn't a game".
    if got.get("game") == "Unknown" and _NOT_GAME_RE.search(reason):
        return True
    return False


def sensible_name(game, src_path, used):
    """OBS-style ``YYYY-MM-DD HH-MM-SS.mkv`` from mtime; avoid collisions."""
    try:
        mtime = os.path.getmtime(src_path)
    except OSError:
        mtime = time.time()
    base = time.strftime("%Y-%m-%d %H-%M-%S", time.localtime(mtime))
    ext = os.path.splitext(src_path)[1] or ".mkv"
    name = base + ext
    i = 2
    key = (game, name.lower())
    while key in used or False:
        name = "%s-%d%s" % (base, i, ext)
        key = (game, name.lower())
        i += 1
    used.add(key)
    return name


def load_state():
    if not os.path.isfile(STATE_PATH):
        return {"done": {}, "skipped": {}}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("done", {})
        data.setdefault("skipped", {})
        return data
    except Exception:
        return {"done": {}, "skipped": {}}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    body = json.dumps(state, indent=2)
    last_exc = None
    for attempt in range(8):
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(body)
            os.replace(tmp, STATE_PATH)
            return
        except OSError as exc:
            last_exc = exc
            time.sleep(0.05 * (attempt + 1))
    alt = STATE_PATH + ".bak"
    try:
        with open(alt, "w", encoding="utf-8") as fh:
            fh.write(body)
        _log("[warn] state locked — wrote %s instead (%s)" % (alt, last_exc))
    except OSError as exc:
        _log("[warn] could not persist state: %s / %s" % (last_exc, exc))


def apply_move(entry, game, new_name, nas_root, catalog, dry_run):
    src = entry["nas_path"]
    dest_dir = os.path.join(nas_root, game)
    dest = os.path.join(dest_dir, new_name)
    old_rel = entry.get("rel") or f"OBS-recovered/{entry.get('name')}"
    new_rel = f"{game}/{new_name}"
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "from": src,
            "to": dest,
            "old_rel": old_rel,
            "new_rel": new_rel,
        }
    os.makedirs(dest_dir, exist_ok=True)
    if os.path.abspath(src) == os.path.abspath(dest):
        return {"ok": True, "skipped": "same path"}
    if os.path.exists(dest):
        return {"ok": False, "error": "dest exists: %s" % dest}
    os.replace(src, dest)  # same volume rename/move
    try:
        st = os.stat(dest)
        size, mtime = st.st_size, st.st_mtime
    except OSError:
        size, mtime = entry.get("size") or 0, entry.get("mtime") or 0
    catalog.remove_index_entry(old_rel)
    catalog.upsert(
        game=game,
        name=new_name,
        size=size,
        mtime=mtime,
        sha256=entry.get("sha256") or "",
        nas_path=dest,
        save=True,
    )
    return {"ok": True, "from": src, "to": dest, "new_rel": new_rel}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=5,
                    help="Max clips this run (ignored if --until-empty)")
    ap.add_argument("--until-empty", action="store_true",
                    help="Process every remaining recoverable clip (no limit)")
    ap.add_argument("--apply", action="store_true",
                    help="Actually move files (default is dry-run)")
    ap.add_argument("--min-confidence", type=float, default=0.55)
    ap.add_argument("--llm-base", default=LLM_BASE)
    ap.add_argument("--resume", action="store_true",
                    help="Skip clips already in sort_recovered_state.json done{} or skipped{}")
    ap.add_argument("--retry-skipped", action="store_true",
                    help="With --resume, re-classify soft skips (Unknown); hard unsortable stay parked")
    ap.add_argument("--keep-loaded", action="store_true", default=True,
                    help="Do not unload vision at end (default: keep loaded)")
    ap.add_argument("--unload", action="store_true",
                    help="Unload vision when the run finishes")
    ap.add_argument("--no-freeform", action="store_true",
                    help="Force labels to the known list only")
    ap.add_argument("--park-unsortable", action="store_true", default=True,
                    help="Move broken/black clips to %s/ (default on)" % UNSORTABLE)
    ap.add_argument("--no-park-unsortable", action="store_true",
                    help="Leave unsortable clips in OBS-recovered")
    args = ap.parse_args(argv)

    llm_base = (args.llm_base or LLM_BASE).rstrip("/")
    dry_run = not args.apply
    allow_freeform = not args.no_freeform
    park_unsortable = args.park_unsortable and not args.no_park_unsortable
    keep_loaded = args.keep_loaded and not args.unload
    cfg = load_config()
    nas_root = (cfg.get("nas_offload_root") or "").strip()
    # Windows: os.path.join("Z:", "Game") → "Z:Game" (cwd on Z:), not "Z:\Game".
    if len(nas_root) == 2 and nas_root[1] == ":":
        nas_root = nas_root + os.sep
    nas_root = os.path.abspath(nas_root) if nas_root else ""
    if not nas_root or not os.path.isdir(nas_root):
        _log("NAS root missing or unreachable: %r" % nas_root)
        return 2

    catalog = ClipCatalog(cfg, on_log=_log, app_dir=APP_DIR)
    sync_folder = (cfg.get("sync_folder") or "").strip()
    if sync_folder:
        if not os.path.isabs(sync_folder):
            sync_folder = os.path.join(os.path.expanduser("~"), sync_folder)
        from obsauto import classifier as classifier_mod
        classifier_mod.DATA_FILE = os.path.join(sync_folder, "games.json")
    classifier = Classifier(on_log=_log)
    labels = game_labels(classifier, nas_root)
    if "Unknown" not in labels:
        labels = list(labels) + ["Unknown"]

    entries = recovered_entries(catalog, nas_root)
    limit = len(entries) if args.until_empty else max(0, args.limit)
    _log("Found %d recoverable clips on NAS under OBS-recovered/Unsorted"
         % len(entries))
    _log("Game labels available: %d | freeform=%s | park_unsortable=%s"
         % (len(labels) - 1, allow_freeform, park_unsortable))
    _log("Mode: %s | limit=%s | min_confidence=%.2f"
         % ("DRY-RUN" if dry_run else "APPLY",
            "until-empty" if args.until_empty else limit,
            args.min_confidence))

    if not dry_run or args.until_empty:
        ensure_vision_loaded(llm_base)

    state = load_state() if args.resume else {"done": {}, "skipped": {}}
    if args.retry_skipped:
        # Drop prior soft-skips so freeform can place Starfield etc.
        # Keep hard extract failures parked unless we re-extract successfully.
        soft = {}
        for rel, got in list(state.get("skipped", {}).items()):
            if is_unsortable(got if isinstance(got, dict) else {}):
                soft[rel] = got
        cleared = len(state.get("skipped", {})) - len(soft)
        state["skipped"] = soft
        _log("Retry skipped: cleared %d soft skip(s); kept %d hard"
             % (cleared, len(soft)))
        save_state(state)

    used_names = set()
    for e in catalog.list_entries():
        used_names.add(((e.get("game") or ""), (e.get("name") or "").lower()))

    done = 0
    for entry in entries:
        if done >= limit:
            break
        rel = entry.get("rel") or entry.get("name")
        if args.resume and rel in state.get("done", {}):
            continue
        if args.resume and rel in state.get("skipped", {}) and not args.retry_skipped:
            # Hard-skipped (unsortable) left in place unless retrying.
            if is_unsortable(state["skipped"][rel]):
                continue
        src = entry["nas_path"]
        _log("")
        _log("[%d/%s] %s" % (
            done + 1,
            "∞" if args.until_empty else str(limit),
            os.path.basename(src),
        ))
        work = os.path.join(WORK_DIR, re.sub(r"[^\w.-]+", "_",
                                             os.path.splitext(os.path.basename(src))[0]))
        got = classify_with_escalation(
            src, labels, args.min_confidence, work,
            llm_base=llm_base, allow_freeform=allow_freeform,
        )
        game = got["game"]
        conf = got["confidence"]
        _log("  → %s (%.2f) frames=%s — %s"
             % (game, conf, got.get("frames"), got.get("reason") or ""))

        if is_unsortable(got) and park_unsortable:
            new_name = sensible_name(UNSORTABLE, src, used_names)
            result = apply_move(
                entry, UNSORTABLE, new_name, nas_root, catalog, dry_run,
            )
            _log("  park unsortable: %s" % result)
            state.setdefault("skipped", {})[rel] = {**got, "parked": UNSORTABLE}
            state.setdefault("done", {})[rel] = {
                "game": UNSORTABLE,
                "confidence": conf,
                "new_name": new_name,
                "result": result,
            }
            save_state(state)
            done += 1
            continue

        if game == "Unknown" or conf < args.min_confidence:
            state.setdefault("skipped", {})[rel] = got
            save_state(state)
            done += 1
            continue

        # Soft skip cleared on successful place.
        state.get("skipped", {}).pop(rel, None)
        new_name = sensible_name(game, src, used_names)
        result = apply_move(entry, game, new_name, nas_root, catalog, dry_run)
        _log("  move: %s" % result)
        state.setdefault("done", {})[rel] = {
            "game": game,
            "confidence": conf,
            "new_name": new_name,
            "result": result,
        }
        save_state(state)
        done += 1

    _log("")
    _log("Finished %d clip(s). State: %s" % (done, STATE_PATH))
    if dry_run:
        _log("Dry-run only — re-run with --apply to move files.")
    if not keep_loaded:
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{llm_base}/api/models/unload",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=30,
            ).read()
            _log("Unloaded local LLM models.")
        except Exception:
            pass
    else:
        _log("Leaving vision loaded (--keep-loaded).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
