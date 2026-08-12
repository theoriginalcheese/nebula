"""Keep a Claude Design project mirrored into the repo, cheaply.

The split this exists to enforce:

    Claude Design   you design there. No plan usage.
    Claude Code     pulls changed files into the repo. Mechanical, seconds.
    Cursor          implements from the repo. Where the bulk spend belongs.

DesignSync is a Claude-only MCP, so the pull step cannot run from here or from
Cursor. What this does is make that step *mechanical*: `plan` prints the exact
tool calls to make, so the Claude session spends no reasoning working out what
changed - it just executes a list. Everything after the pull is local, and Cursor
never needs Claude Design at all.

Mirrors live at `design/ui-v3/_ds/<name>-<projectId>/`, a convention that already
existed here - the directory name carries the project id.

    python tools/design_sync.py status
    python tools/design_sync.py plan            # paste-able call list for Claude
    python tools/design_sync.py brief           # Cursor handoff for what changed
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRRORS = os.path.join(ROOT, "design", "ui-v3", "_ds")
MANIFEST = ".sync-manifest.json"
BRIEF = os.path.join(ROOT, ".cursor", "handoff", "specs")

# get_file refuses anything larger. Per-component files are far below it; a
# monolithic mockup is not, which is why the 347KB .dc.html cannot come through
# this path and is committed instead.
CAP = 256 * 1024


def digest(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def mirrors() -> list[tuple[str, str, str]]:
    """(directory, project name, projectId) for every local mirror."""
    out = []
    if not os.path.isdir(MIRRORS):
        return out
    for name in sorted(os.listdir(MIRRORS)):
        path = os.path.join(MIRRORS, name)
        if not os.path.isdir(path):
            continue
        # <name>-<uuid>
        m = re.match(r"^(.*)-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                     r"[0-9a-f]{4}-[0-9a-f]{12})$", name)
        if m:
            out.append((path, m.group(1), m.group(2)))
    return out


def local_files(root: str) -> dict[str, str]:
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name == MANIFEST:
                continue
            full = os.path.join(dirpath, name)
            out[os.path.relpath(full, root).replace(os.sep, "/")] = digest(full)
    return out


def manifest_of(root: str) -> dict:
    try:
        with open(os.path.join(root, MANIFEST), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def cmd_status(_args) -> int:
    found = mirrors()
    if not found:
        print(f"no mirrors under {os.path.relpath(MIRRORS, ROOT)}")
        return 0
    for root, name, pid in found:
        man = manifest_of(root)
        have = local_files(root)
        pulled = man.get("pulledAt")
        remote = man.get("remoteFiles")
        print(f"\n{name}  ({pid})")
        print(f"  local files : {len(have)}")
        if isinstance(remote, list):
            missing = sorted(set(remote) - set(have))
            print(f"  remote files: {len(remote)}")
            if missing:
                print(f"  NOT MIRRORED: {len(missing)}")
                for rel in missing[:8]:
                    print(f"      {rel}")
                if len(missing) > 8:
                    print(f"      ... and {len(missing) - 8} more")
        elif isinstance(remote, int):
            print(f"  remote files: {remote}")
            if remote > len(have):
                print(f"  NOT MIRRORED: {remote - len(have)} "
                      f"(run `design_sync.py plan` for the pull list)")
        else:
            print("  remote files: unknown - never pulled through this tool")
        print(f"  last pull   : {pulled or 'never'}")
        drift = [rel for rel, d in have.items() if man.get("files", {}).get(rel) not in (None, d)]
        if drift:
            print(f"  EDITED LOCALLY SINCE PULL: {', '.join(drift[:6])}")
    return 0


def cmd_plan(args) -> int:
    found = [m for m in mirrors() if not args.project or args.project in (m[1], m[2])]
    if not found:
        print("no matching mirror")
        return 1
    for root, name, pid in found:
        have = local_files(root)
        rel_root = os.path.relpath(root, ROOT).replace(os.sep, "/")
        print(f"# {name}  ->  {rel_root}\n")
        print("Run these, then re-run `python tools/design_sync.py status`.\n")
        print("1. List what the project holds:\n")
        print(f'   DesignSync  method=list_files  projectId={pid}\n')
        print("2. For each path NOT already mirrored, or whose content you expect to")
        print("   have changed, read it and write it to the mirror:\n")
        print(f'   DesignSync  method=get_file  projectId={pid}  path=<path>')
        print(f"   -> save to {rel_root}/<path>\n")
        print(f"   Already mirrored ({len(have)}): {', '.join(sorted(have)) or 'none'}\n")
        print("3. Record the pull so the next diff is cheap:\n")
        print(f"   python tools/design_sync.py record --project {name} \\")
        print("       --remote <total-file-count>\n")
        print(f"Anything larger than {CAP // 1024} KiB is refused by get_file - a")
        print("monolithic mockup has to be committed by hand instead.\n")
    return 0


def cmd_record(args) -> int:
    found = [m for m in mirrors() if not args.project or args.project in (m[1], m[2])]
    if not found:
        print("no matching mirror")
        return 1
    for root, name, _pid in found:
        have = local_files(root)
        payload = {
            "pulledAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "remoteFiles": args.remote,
            "files": have,
        }
        with open(os.path.join(root, MANIFEST), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        print(f"recorded {len(have)} file(s) for {name}")
    return 0


def cmd_brief(args) -> int:
    """Turn 'the design changed' into a spec Cursor can act on."""
    found = [m for m in mirrors() if not args.project or args.project in (m[1], m[2])]
    if not found:
        print("no matching mirror")
        return 1
    root, name, pid = found[0]
    man = manifest_of(root)
    have = local_files(root)
    changed = sorted(rel for rel, d in have.items()
                     if man.get("files", {}).get(rel) not in (None, d))
    added = sorted(set(have) - set(man.get("files", {})))
    rel_root = os.path.relpath(root, ROOT).replace(os.sep, "/")

    lines = [
        f"# Design sync — {name}",
        "",
        f"Source: Claude Design project `{pid}`, mirrored at `{rel_root}/`.",
        "",
        "## What moved",
        "",
    ]
    if not (changed or added):
        lines.append("Nothing since the last recorded pull.")
    for rel in added:
        lines.append(f"- **new** `{rel}`")
    for rel in changed:
        lines.append(f"- **changed** `{rel}`")
    lines += [
        "",
        "## What outranks it",
        "",
        "`design/ui-v3/BUILD-SPEC.md` > the frames > everything else, and",
        "`obsauto/design_v3.py` is that contract as code. **This mirror is the house",
        "system, not the v3 contract** — v3 overrides it wholesale. Take a token from",
        "here only if BUILD-SPEC.md is silent, and say so in the report.",
        "",
        "## Definition of done",
        "",
        "```bash",
        "python tools/agent.py gate!",
        "```",
        "",
        "Do not launch Nebula or OBS. No fabricated values.",
    ]
    text = "\n".join(lines) + "\n"

    if args.write:
        os.makedirs(BRIEF, exist_ok=True)
        path = os.path.join(BRIEF, f"design-{name.lower()}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {os.path.relpath(path, ROOT)}")
        print("\nsend it to Cursor with:")
        print(f"  python tools/delegate.py send --title 'design: {name}' "
              f"--spec {os.path.relpath(path, ROOT)}")
        return 0
    print(text)
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("status", help="what is mirrored and what drifted")
    p = sub.add_parser("plan", help="the exact DesignSync calls to make in Claude")
    p.add_argument("--project")
    p = sub.add_parser("record", help="record a completed pull")
    p.add_argument("--project")
    p.add_argument("--remote", type=int, default=None)
    p = sub.add_parser("brief", help="Cursor handoff for what changed")
    p.add_argument("--project")
    p.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)

    return {
        "status": cmd_status, "plan": cmd_plan,
        "record": cmd_record, "brief": cmd_brief,
    }.get(a.cmd, lambda _a: (ap.print_help() or 1))(a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
