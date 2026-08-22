"""Reorganise Z:\\ game recordings under Z:\\OBS Recordings\\ (same-volume).

Idempotent. Default is dry-run; pass --apply to execute moves + config wiring.

Sacred footage: only os.replace / same-volume MoveFile within Z:. Never
copy-delete. Never delete a source without a successful move. Skip clobber
when dest already exists (merge files into existing game folders instead).

After apply:
  - config.json nas_offload_root -> Z:\\OBS Recordings
  - clip_index.json absolute nas_path prefixes rewritten
  - .nebula -> Z:\\OBS Recordings\\.nebula (NasGameSync)
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_VOLUME = "Z:\\"
DEFAULT_PARENT = "OBS Recordings"
MEDIA_EXTS = {".mkv", ".mp4", ".mov", ".m4v", ".flv", ".ts"}

# Explicit non-recording top-level dirs (Anthony confirmed 2026-08-21).
LEAVE_AT_ROOT = {
    "backups",
    "crucial2tb-rescue-2026-07-18",
    "dad 4tb",
    "isos",
    "omnicloud-minio",
    "strix laptop acronis backup",
    "101olymp",
    "incoming",  # VHDX dump, not Nebula recordings
}

SYSTEM_JUNK = {
    "$recycle.bin",
    "system volume information",
    "lost+found",
    ".trash",
    "recycle.bin",
}

# Always relocate these even if empty / no media sample.
FORCE_MOVE = {
    "obs-recovered",
    "_unsortable",
    "obs",
    ".nebula",
}


def _norm_vol(path: str) -> str:
    path = (path or "").strip()
    if len(path) == 2 and path[1] == ":":
        path = path + os.sep
    return os.path.normpath(path)


def _same_volume(a: str, b: str) -> bool:
    a_drive = os.path.splitdrive(os.path.abspath(a))[0].upper()
    b_drive = os.path.splitdrive(os.path.abspath(b))[0].upper()
    return bool(a_drive) and a_drive == b_drive


def _is_media(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in MEDIA_EXTS


def _dir_has_media(path: str, sample: int = 64) -> bool:
    """True if the directory (non-recursive) contains a media file."""
    try:
        with os.scandir(path) as it:
            n = 0
            for ent in it:
                if ent.is_file(follow_symlinks=False) and _is_media(ent.name):
                    return True
                n += 1
                if n >= sample:
                    break
    except OSError:
        return False
    return False


def _should_leave(name: str) -> bool:
    key = name.lower()
    if key in LEAVE_AT_ROOT or key in SYSTEM_JUNK:
        return True
    if name.startswith("$"):
        return True
    return False


def _should_move_dir(name: str, path: str, parent_name: str) -> bool:
    if name == parent_name:
        return False
    if _should_leave(name):
        return False
    if name.lower() in FORCE_MOVE:
        return True
    if _dir_has_media(path):
        return True
    return False


def plan_moves(volume: str, parent_name: str) -> list[tuple[str, str, str]]:
    """Return list of (kind, src, dest) planned operations."""
    volume = _norm_vol(volume)
    parent = os.path.join(volume, parent_name)
    plans: list[tuple[str, str, str]] = []

    try:
        entries = list(os.scandir(volume))
    except OSError as exc:
        raise SystemExit("Cannot list %s: %s" % (volume, exc)) from exc

    for ent in entries:
        if not ent.is_dir(follow_symlinks=False):
            # Leave loose root files alone unless they are recordings — rare.
            if ent.is_file(follow_symlinks=False) and _is_media(ent.name):
                dest = os.path.join(parent, "_Unsortable", ent.name)
                plans.append(("file", ent.path, dest))
            continue
        if not _should_move_dir(ent.name, ent.path, parent_name):
            continue
        dest = os.path.join(parent, ent.name)
        plans.append(("dir", ent.path, dest))

    return plans


def _unique_dest(path: str) -> str:
    """If path exists, append .migrated-N before extension (files) or name (dirs)."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while True:
        candidate = "%s.migrated-%d%s" % (base, n, ext)
        if not os.path.exists(candidate):
            return candidate
        n += 1


def move_merge(src: str, dest: str, apply: bool) -> dict:
    """Same-volume move; if dest exists, merge children without clobber."""
    result = {
        "src": src,
        "dest": dest,
        "ok": False,
        "action": "",
        "skipped": [],
        "moved_files": 0,
        "error": "",
    }
    if not _same_volume(src, dest):
        result["error"] = "refusing cross-volume move"
        return result
    if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dest)):
        result["ok"] = True
        result["action"] = "already-at-dest"
        return result

    if not os.path.exists(src):
        # Idempotent: already moved on a prior run.
        if os.path.exists(dest):
            result["ok"] = True
            result["action"] = "src-gone-dest-present"
            return result
        result["error"] = "src missing"
        return result

    if not os.path.exists(dest):
        result["action"] = "replace"
        if apply:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                os.replace(src, dest)
            except OSError as exc:
                # SMB/NAS often denies whole-dir rename (WinError 5) even when
                # per-file same-volume moves succeed — fall back to merge.
                winerr = getattr(exc, "winerror", None)
                if winerr == 5 or exc.errno in (13, 1):
                    os.makedirs(dest, exist_ok=True)
                    return move_merge(src, dest, apply=True)
                raise
        result["ok"] = True
        return result

    # Dest exists: merge.
    if os.path.isfile(src) and os.path.isfile(dest):
        result["action"] = "skip-clobber-file"
        result["skipped"].append(os.path.basename(src))
        result["ok"] = True
        return result

    if os.path.isdir(src) and os.path.isdir(dest):
        result["action"] = "merge-into-existing"
        try:
            children = list(os.scandir(src))
        except OSError as exc:
            result["error"] = str(exc)
            return result
        for child in children:
            child_dest = os.path.join(dest, child.name)
            if os.path.exists(child_dest):
                if child.is_file(follow_symlinks=False) and os.path.isfile(child_dest):
                    result["skipped"].append(child.name)
                    continue
                if child.is_dir(follow_symlinks=False) and os.path.isdir(child_dest):
                    # Recurse merge one level (game folders are flat media).
                    nested = move_merge(child.path, child_dest, apply)
                    result["moved_files"] += nested.get("moved_files", 0)
                    result["skipped"].extend(nested.get("skipped", []))
                    if not nested.get("ok"):
                        result["error"] = nested.get("error") or "nested merge failed"
                        return result
                    continue
                # Type mismatch — park under unique name rather than delete.
                alt = _unique_dest(child_dest)
                if apply:
                    os.replace(child.path, alt)
                result["moved_files"] += 1
                continue
            if apply:
                os.replace(child.path, child_dest)
            result["moved_files"] += 1
        # Remove empty src after merge.
        if apply:
            try:
                os.rmdir(src)
            except OSError:
                # Non-empty leftovers (skipped clobbers) — leave them.
                pass
        result["ok"] = True
        return result

    result["error"] = "src/dest type mismatch"
    return result


def park_recovered_leftovers(volume: str, parent: str, apply: bool) -> list[dict]:
    """Park soft-skipped leftovers in OBS-recovered → _Unsortable (same volume).

    Checks both ``Z:\\OBS-recovered`` and ``Z:\\OBS Recordings\\OBS-recovered``
    so the step stays useful after the parent folder already exists. Never delete.
    """
    volume = _norm_vol(volume)
    parent = os.path.normpath(parent)
    src_dirs = [
        os.path.join(volume, "OBS-recovered"),
        os.path.join(parent, "OBS-recovered"),
    ]
    # Prefer parking beside the post-migration tree when parent exists.
    dest_dir = (
        os.path.join(parent, "_Unsortable")
        if os.path.isdir(parent)
        else os.path.join(volume, "_Unsortable")
    )
    results = []
    files = []
    for src_dir in src_dirs:
        if not os.path.isdir(src_dir):
            continue
        try:
            for e in os.scandir(src_dir):
                if e.is_file(follow_symlinks=False) and _is_media(e.name):
                    files.append(e)
        except OSError as exc:
            results.append({"error": str(exc), "src_dir": src_dir})
    if not files:
        return results
    if apply:
        os.makedirs(dest_dir, exist_ok=True)
    used = set()
    if os.path.isdir(dest_dir):
        try:
            used = {n.lower() for n in os.listdir(dest_dir)}
        except OSError:
            used = set()
    for ent in files:
        name = ent.name
        base, ext = os.path.splitext(name)
        dest_name = name
        n = 2
        while dest_name.lower() in used:
            dest_name = "%s-%d%s" % (base, n, ext)
            n += 1
        used.add(dest_name.lower())
        dest = os.path.join(dest_dir, dest_name)
        row = {"from": ent.path, "to": dest, "ok": False}
        if not apply:
            row["ok"] = True
            row["dry_run"] = True
            results.append(row)
            continue
        try:
            os.replace(ent.path, dest)
            row["ok"] = True
        except OSError as exc:
            row["error"] = str(exc)
        results.append(row)
    return results


def ensure_empty_inbox(parent: str, apply: bool) -> str:
    inbox = os.path.join(parent, "OBS-recovered")
    if apply:
        os.makedirs(inbox, exist_ok=True)
    return inbox


def rewrite_clip_index(index_path: str, old_root: str, new_root: str, apply: bool) -> dict:
    """Rewrite absolute nas_path prefixes; leave rel (game/name) unchanged.

    Also repairs leave-at-root folders wrongly prefixed under OBS Recordings
    (e.g. 101OLYMP stays at ``Z:\\101OLYMP\\``).
    """
    stats = {
        "path": index_path,
        "rewritten": 0,
        "repaired_leave": 0,
        "unchanged": 0,
        "missing": False,
    }
    if not os.path.isfile(index_path):
        stats["missing"] = True
        return stats

    with open(index_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    old_root_n = os.path.normpath(old_root)
    new_root_n = os.path.normpath(new_root)
    old_prefixes = [
        old_root_n,
        old_root_n.rstrip("\\/") + "\\",
        "Z:",
        "Z:\\",
        "Z:/",
    ]
    new_marker = os.path.normcase(new_root_n)
    vol = _norm_vol(old_root)

    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        stats["error"] = "unexpected clip_index shape"
        return stats

    leave_tops = {n.lower() for n in LEAVE_AT_ROOT} | {n.lower() for n in SYSTEM_JUNK}

    for ent in entries:
        if not isinstance(ent, dict):
            continue
        nas = ent.get("nas_path") or ""
        if not nas:
            stats["unchanged"] += 1
            continue
        nas_n = os.path.normpath(nas)
        nas_case = os.path.normcase(nas_n)

        # Already under new root — repair leave-at-root misfires, else keep.
        if nas_case.startswith(new_marker + os.sep) or nas_case == new_marker:
            rel = nas_n[len(new_root_n):].lstrip("\\/") if nas_case != new_marker else ""
            top = (rel.split("\\")[0].split("/")[0] if rel else "").lower()
            if top in leave_tops:
                fixed = os.path.normpath(os.path.join(vol, rel))
                if os.path.normcase(fixed) != nas_case:
                    ent["nas_path"] = fixed
                    stats["repaired_leave"] += 1
                    continue
            stats["unchanged"] += 1
            continue

        rewritten = None
        for pref in sorted(set(old_prefixes), key=len, reverse=True):
            pref_n = os.path.normpath(pref)
            if len(pref_n) == 2 and pref_n[1] == ":":
                drive = pref_n + os.sep
                if nas_case.startswith(os.path.normcase(drive)):
                    rel = nas_n[len(drive):].lstrip("\\/")
                    top = (rel.split("\\")[0].split("/")[0] if rel else "").lower()
                    if top in leave_tops:
                        rewritten = None
                        break
                    if rel.lower().startswith(DEFAULT_PARENT.lower() + os.sep.lower()) or rel.lower().startswith(
                        DEFAULT_PARENT.lower() + "/"
                    ):
                        rewritten = os.path.join("Z:\\", rel)
                    else:
                        rewritten = os.path.join(new_root_n, rel)
                    break
            pref_full = pref_n if pref_n.endswith(os.sep) else pref_n + os.sep
            if nas_case.startswith(os.path.normcase(pref_full)):
                rel = nas_n[len(pref_full):]
                top = (rel.split("\\")[0].split("/")[0] if rel else "").lower()
                if top in leave_tops:
                    rewritten = None
                    break
                rewritten = os.path.join(new_root_n, rel)
                break
            if nas_case == os.path.normcase(pref_n):
                rewritten = new_root_n
                break
        if rewritten and os.path.normcase(os.path.normpath(rewritten)) != nas_case:
            ent["nas_path"] = rewritten
            stats["rewritten"] += 1
        else:
            stats["unchanged"] += 1

    if apply and (stats["rewritten"] or stats["repaired_leave"]):
        _atomic_json_write(index_path, data)
    return stats


def _atomic_json_write(path: str, data, retries: int = 8) -> None:
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".clip_index_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        last_err = None
        for i in range(retries):
            try:
                os.replace(tmp, path)
                return
            except OSError as exc:
                last_err = exc
                # WinError 32 sharing violation
                if getattr(exc, "winerror", None) == 32 or exc.errno in (13, 11):
                    time.sleep(0.25 * (i + 1))
                    continue
                raise
        raise last_err  # type: ignore[misc]
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def update_config(config_path: str, new_root: str, apply: bool) -> dict:
    stats = {"path": config_path, "old": None, "new": new_root, "missing": False}
    if not os.path.isfile(config_path):
        stats["missing"] = True
        return stats
    with open(config_path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    stats["old"] = cfg.get("nas_offload_root")
    if stats["old"] == new_root:
        stats["action"] = "already-set"
        return stats
    cfg["nas_offload_root"] = new_root
    if apply:
        _atomic_json_write(config_path, cfg)
    stats["action"] = "updated"
    return stats


def remaining_at_root(volume: str, parent_name: str) -> list[str]:
    volume = _norm_vol(volume)
    out = []
    for ent in os.scandir(volume):
        if ent.name == parent_name:
            continue
        out.append(ent.name + ("/" if ent.is_dir(follow_symlinks=False) else ""))
    return sorted(out, key=str.lower)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--volume", default=DEFAULT_VOLUME, help="NAS volume root (default Z:\\)")
    ap.add_argument("--parent", default=DEFAULT_PARENT, help="New parent folder name")
    ap.add_argument("--apply", action="store_true", help="Execute moves (default: dry-run)")
    ap.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    ap.add_argument("--dist-config", default=os.path.join(ROOT, "dist", "config.json"))
    ap.add_argument("--clip-index", default=os.path.join(ROOT, "clip_index.json"))
    ap.add_argument("--skip-config", action="store_true")
    ap.add_argument("--skip-index", action="store_true")
    args = ap.parse_args(argv)

    volume = _norm_vol(args.volume)
    parent = os.path.join(volume, args.parent)
    new_root = parent
    mode = "APPLY" if args.apply else "DRY-RUN"

    print("=== migrate_nas_obs_recordings (%s) ===" % mode)
    print("volume: %s" % volume)
    print("parent: %s" % parent)
    print("leave-at-root: %s" % ", ".join(sorted(LEAVE_AT_ROOT)))

    if not os.path.isdir(volume):
        print("ERROR: volume unreachable: %r" % volume)
        return 2

    # Park soft-skipped leftovers before relocating game folders.
    parked = park_recovered_leftovers(volume, parent, apply=False)
    if parked:
        print("OBS-recovered leftovers to park -> _Unsortable: %d" % len(parked))
        for row in parked[:20]:
            print("  park %s -> %s" % (row.get("from"), row.get("to")))
        if len(parked) > 20:
            print("  ... +%d more" % (len(parked) - 20))
        if args.apply:
            parked = park_recovered_leftovers(volume, parent, apply=True)
            bad = [r for r in parked if not r.get("ok")]
            print("parked ok=%d fail=%d" % (len(parked) - len(bad), len(bad)))
            for r in bad:
                print("  PARK FAIL: %s" % r)

    plans = plan_moves(volume, args.parent)
    print("planned moves: %d" % len(plans))
    for kind, src, dest in plans:
        print("  [%s] %s  ->  %s" % (kind, src, dest))

    if args.apply:
        os.makedirs(parent, exist_ok=True)

    moved_ok = 0
    errors = []
    for kind, src, dest in plans:
        res = move_merge(src, dest, apply=args.apply)
        status = "ok" if res["ok"] else "FAIL"
        print("  %s %s action=%s moved_files=%s skipped=%d %s"
              % (status, kind, res.get("action"), res.get("moved_files"),
                 len(res.get("skipped") or []), res.get("error") or ""))
        if res["ok"]:
            moved_ok += 1
        else:
            errors.append(res)

    inbox = ensure_empty_inbox(parent, apply=args.apply)
    print("empty inbox: %s" % inbox)

    # Prefer relocating .nebula if somehow left behind.
    nebula_src = os.path.join(volume, ".nebula")
    nebula_dst = os.path.join(parent, ".nebula")
    if os.path.isdir(nebula_src) and not os.path.isdir(nebula_dst):
        print("NOTE: .nebula still at volume root — including in plan above if listed")
    print(".nebula expected at: %s (exists=%s)"
          % (nebula_dst, os.path.isdir(nebula_dst) or (not args.apply and any(
              s.endswith(os.sep + ".nebula") or s.endswith("\\.nebula") for _, s, _ in plans
          ))))

    cfg_stats = None
    if not args.skip_config:
        cfg_stats = update_config(args.config, new_root, apply=args.apply)
        print("config: %s" % cfg_stats)
        if os.path.isfile(args.dist_config):
            dist_stats = update_config(args.dist_config, new_root, apply=args.apply)
            print("dist-config: %s" % dist_stats)
        else:
            print("dist-config: absent (skip)")

    idx_stats = None
    if not args.skip_index:
        idx_stats = rewrite_clip_index(
            args.clip_index, old_root=volume, new_root=new_root, apply=args.apply
        )
        print("clip_index: %s" % idx_stats)

    rem = remaining_at_root(volume, args.parent)
    print("remaining at %s root (%d): %s"
          % (volume, len(rem), ", ".join(rem[:40]) + (" ..." if len(rem) > 40 else "")))
    print("summary: planned=%d ok=%d errors=%d mode=%s"
          % (len(plans), moved_ok, len(errors), mode))
    if errors:
        for e in errors:
            print("ERROR detail: %s" % e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
