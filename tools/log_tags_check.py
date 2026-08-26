"""Log-tag linter: every _log("[Area] ...") tag is well-formed and unique.

    python tools/log_tags_check.py          # human report
    python tools/log_tags_check.py --json

The `[Area]` prefix is the unit operators and agents grep obsauto.log by
(see CLAUDE.md's logging conventions). Two drift classes:

  BAD-TAG - a tag that is not `[A-Z][A-Za-z]+` shaped: a lowercase tag,
            digits, or missing closing bracket breaks greppability and
            usually means someone typed the prefix by hand.
  CASE-COLLISION - two tags differing only by case ("[Sync]" vs "[sync]")
            split one subsystem's history across two greps.

f-strings with dynamic tags (`_log(f"[{area}] ...")`) cannot be verified
statically and are reported as DYNAMIC for manual review rather than
silently skipped.

Exit 1 on BAD-TAG / CASE-COLLISION.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCANNED = ("obsauto", "spike")
SKIP_FILES = {"gui.py"}  # legacy shell, audited separately

TAG_RE = re.compile(r"_log\(\s*f?['\"]\[([^\[\]]+)\]")
DYNAMIC_TAG_RE = re.compile(r"_log\(\s*f?['\"]\[")


def run():
    problems, info = [], []
    tags = {}
    for d in SCANNED:
        pkg_dir = os.path.join(ROOT, d)
        if not os.path.isdir(pkg_dir):
            continue
        for n in sorted(os.listdir(pkg_dir)):
            if not n.endswith(".py") or n in SKIP_FILES:
                continue
            path = os.path.join(pkg_dir, n)
            try:
                open(path, encoding="utf-8").close()  # readable sanity
            except OSError:
                problems.append("UNREADABLE: %s/%s" % (d, n))
                continue
            text = open(path, encoding="utf-8").read()
            for m in TAG_RE.finditer(text):
                tag = m.group(1)
                if "{" in tag:
                    continue  # runtime-built; DYNAMIC below reports it
                site = "%s/%s:%d" % (d, n, text[:m.start()].count("\n") + 1)
                tags.setdefault(tag, []).append(site)
            for m in DYNAMIC_TAG_RE.finditer(text):
                line_no = text[:m.start()].count("\n") + 1
                line = text.splitlines()[line_no - 1].strip()
                if "{" in line.split("]")[0]:
                    info.append("DYNAMIC: %s/%s:%d builds its tag at "
                                "runtime - verify manually"
                                % (d, n, line_no))

    for tag in sorted(tags):
        if not re.fullmatch(r"[A-Z][A-Za-z]+", tag):
            problems.append(
                "BAD-TAG: [%s] (%s) - expected [Word] shaped like [Sync]"
                % (tag, ", ".join(tags[tag][:3])))

    seen = {}
    for tag in sorted(tags, key=str.lower):
        low = tag.lower()
        if low in seen and seen[low] != tag:
            problems.append(
                "CASE-COLLISION: [%s] vs [%s] differ only by case - one "
                "subsystem's history splits across two greps"
                % (seen[low], tag))
        seen[low] = tag
    return problems, info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    problems, info = run()
    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems,
                          "info": info}, indent=2))
    else:
        for p in problems:
            print("[FAIL] " + p)
        for i in info:
            print("[INFO] " + i)
        if not problems:
            print("[PASS] all log tags well-formed and case-unique")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
