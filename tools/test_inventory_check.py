"""Test-suite self-documentation check: docstrings + no ghost doc paths.

    python tools/test_inventory_check.py          # human report
    python tools/test_inventory_check.py --json

The suite is its own inventory (tools/run_tests.py picks up every
tests/test_*.py), so prose lists can never be complete - but two things
must hold:

  1. Every test file and contract tool starts with a module docstring.
     An agent triaging a failure reads the docstring first; without one it
     must reverse-engineer intent from assertions. (Docstrings predate this
     check repo-wide; this makes the convention load-bearing.)
  2. Any tests/<file>.py path named in CLAUDE.md exists on disk - the same
     ghost rule the module-map checker applies to architecture docs.

Exit 1 on any violation.
"""
import argparse
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
TOOLS = os.path.join(ROOT, "tools")
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")


def _first_node_doc(path):
    try:
        # utf-8-sig: tolerate a BOM the way the interpreter does, so a
        # stray BOM is not misreported as a syntax error here.
        tree = ast.parse(open(path, encoding="utf-8-sig").read())
    except SyntaxError:
        return None, "SYNTAX ERROR"
    return ast.get_docstring(tree), None


def run():
    problems = []

    for d in (TESTS, TOOLS):
        for n in sorted(os.listdir(d)):
            if not n.endswith(".py") or n.startswith("_"):
                continue
            if n == "__init__.py":
                continue
            doc, err = _first_node_doc(os.path.join(d, n))
            if err:
                problems.append("%s/%s: %s" % (os.path.basename(d), n, err))
            elif not doc:
                problems.append(
                    "NO-DOCSTRING: %s/%s - every test/tool documents "
                    "what it pins in its module docstring" %
                    (os.path.basename(d), n))

    text = open(CLAUDE_MD, encoding="utf-8").read()
    for m in sorted(set(re.findall(r"tests/(test_[\w]+\.py)", text))):
        if not os.path.isfile(os.path.join(TESTS, m)):
            problems.append(
                "GHOST: CLAUDE.md references tests/%s which does not exist"
                % m)
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    problems = run()
    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems},
                         indent=2))
    else:
        for p in problems:
            print("[FAIL] " + p)
        if not problems:
            print("[PASS] all test files and tools carry docstrings; "
                  "CLAUDE.md has no ghost test paths")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
