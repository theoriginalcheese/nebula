"""Mirror .claude/skills/ into .cursor/skills/ so both harnesses see them.

Claude Code reads `.claude/skills/`; Cursor reads `.cursor/skills/`. Neither
reads the other, so nebula-ui and nebula-polish - the design contract and the
polish checklist - were invisible to Cursor, which is the harness doing the
toast work.

`.claude/skills/` is the source of truth. `.cursor/skills/` is generated, and
the copies are kept byte-identical: two editable copies of a design contract is
exactly the drift this repo warns about elsewhere.

    python tools/sync_skills.py            # report drift
    python tools/sync_skills.py --apply    # copy source -> generated
"""

from __future__ import annotations

import filecmp
import hashlib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, ".claude", "skills")
DST = os.path.join(ROOT, ".cursor", "skills")
MANIFEST = os.path.join(DST, ".sync-manifest.json")


def digest(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()[:16]


def walk(base: str) -> dict[str, str]:
    """Relative path -> digest, for every file under base."""
    out = {}
    for root, _dirs, files in os.walk(base):
        for name in files:
            if name == ".sync-manifest.json":
                continue
            full = os.path.join(root, name)
            out[os.path.relpath(full, base).replace(os.sep, "/")] = digest(full)
    return out


def drift() -> tuple[list[str], list[str], list[str]]:
    """Returns (missing in .cursor, differing, extra in .cursor)."""
    if not os.path.isdir(SRC):
        return [], [], []
    source = walk(SRC)
    generated = walk(DST) if os.path.isdir(DST) else {}
    missing = sorted(k for k in source if k not in generated)
    differing = sorted(k for k in source if k in generated and source[k] != generated[k])
    extra = sorted(k for k in generated if k not in source)
    return missing, differing, extra


def apply() -> int:
    os.makedirs(DST, exist_ok=True)
    source = walk(SRC)
    copied = 0
    for rel in source:
        src, dst = os.path.join(SRC, rel), os.path.join(DST, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst) or not filecmp.cmp(src, dst, shallow=False):
            shutil.copy2(src, dst)
            copied += 1
    for rel in walk(DST):
        if rel not in source:
            os.remove(os.path.join(DST, rel))
            print(f"  removed stale {rel}")
    with open(MANIFEST, "w", encoding="utf-8") as handle:
        json.dump(
            {"generated_from": ".claude/skills", "files": source},
            handle,
            indent=2,
            sort_keys=True,
        )
    print(f"synced {len(source)} file(s), {copied} changed -> .cursor/skills/")
    return 0


def main(argv: list[str]) -> int:
    if not os.path.isdir(SRC):
        print(f"no source skills at {SRC}")
        return 0

    missing, differing, extra = drift()
    if "--apply" in argv:
        return apply()

    if not (missing or differing or extra):
        print(f"skills in sync ({len(walk(SRC))} file(s))")
        return 0

    print("skills OUT OF SYNC between .claude/skills and .cursor/skills:")
    for rel in missing:
        print(f"  missing in .cursor/  {rel}")
    for rel in differing:
        print(f"  differs              {rel}")
    for rel in extra:
        print(f"  stale in .cursor/    {rel}")
    print("\n  fix: python tools/sync_skills.py --apply")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
