"""Docs drift check: README's config table vs config.DEFAULTS.

    python tools/docs_drift_check.py          # human report
    python tools/docs_drift_check.py --json

One-directional by design: README's settings table is *curated, not
exhaustive* (its own words), so a DEFAULTS key missing from the table is
fine - but a key documented in the README that no longer exists in
config.py is a ghost that misleads every reader who trusts the docs.
Combined rows ("`obs_host` / `obs_port`") are split on '/'.

Exit 1 on ghosts.
"""
import argparse
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")
CONFIG_PY = os.path.join(ROOT, "obsauto", "config.py")

TABLE_HEADER = re.compile(r"^\|\s*Key\s*\|\s*Default\b", re.IGNORECASE)


def default_keys():
    tree = ast.parse(open(CONFIG_PY, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "DEFAULTS"
                for t in node.targets):
            if isinstance(node.value, ast.Dict):
                return {k.value for k in node.value.keys
                        if isinstance(k, ast.Constant)}
    raise RuntimeError("DEFAULTS dict not found in %s" % CONFIG_PY)


def readme_keys():
    keys = []
    in_table = False
    for ln in open(README, encoding="utf-8"):
        if TABLE_HEADER.match(ln):
            in_table = True
            continue
        if in_table:
            if not ln.lstrip().startswith("|"):
                break  # table ended
            cell = ln.strip().strip("|").split("|")[0].strip()
            for tok in re.findall(r"`([^`]+)`", cell):
                for part in tok.split("/"):
                    part = part.strip()
                    if re.fullmatch(r"[a-z][a-z0-9_]+", part):
                        keys.append((part,
                                     "(key column)"))
    return keys


def run():
    problems = []
    known = default_keys()
    for key, where in readme_keys():
        if key not in known:
            problems.append(
                "GHOST: README documents '%s' (%s) but it is not a key in "
                "config.DEFAULTS" % (key, where))
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
            print("[PASS] README config table has no ghost keys "
                  "(%d documented, %d in DEFAULTS)"
                  % (len(readme_keys()), len(default_keys())))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
