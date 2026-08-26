"""Palette contract checker: row kinds vs palette_run dispatch vs targets.

    python tools/palette_contract_check.py          # human report
    python tools/palette_contract_check.py --json

Why this exists
---------------
The command palette is a string-typed dispatcher built at runtime: rows in
``Api._palette_rows`` carry ``(kind, arg)`` tuples and ``Api.palette_run``
hand-matches ``kind`` against string branches, calling host/self methods by
name. Nothing type-checks any of it - a renamed ``_save_replay`` or a row
added with a misspelled kind surfaces only when Anthony runs that exact row
in the UI.

What it checks (all static AST, no imports of app modules):
  1. ROW-KIND   - every literal ("kind", ...) in a palette_mod.Row(...) call
     inside _palette_rows has a matching branch in palette_run.
  2. DEAD-BRANCH- a palette_run branch no row can produce (informational -
     some are defensive).
  3. TARGETS    - methods referenced inside each dispatch branch exist on
     their receiver class (self -> spike/app.py classes, host ->
     NebulaHost in spike/host.py).

Exit 1 on ROW-KIND/TARGETS failures.
"""
import argparse
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.join(ROOT, "spike", "app.py")
HOST_PATH = os.path.join(ROOT, "spike", "host.py")


def _parse(path):
    with open(path, encoding="utf-8") as f:
        return ast.parse(f.read())


def _class_methods(tree):
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            out[node.name] = {
                n.name for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return out


def row_kinds(tree):
    """Literal kind strings from palette_mod.Row(...) calls, with sites."""
    kinds = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "Row"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Tuple) and arg.elts \
                    and isinstance(arg.elts[0], ast.Constant):
                k = arg.elts[0].value
                site = "%s:%d" % (os.path.basename(APP_PATH), node.lineno)
                kinds.setdefault(k, set()).add(site)
    return {k: sorted(v) for k, v in kinds.items()}


def dispatch_branches(tree):
    """{kind: {"site": lineno, "attrs": {recv_name: [attr, ...]}}} for each
    `kind == "K"` comparison branch inside palette_run."""
    branches = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef)
                and node.name == "palette_run"):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.If):
                continue
            # The test may be `kind == "K"` or a conjunction like
            # `kind == "K" and host` - collect every == comparison in it.
            tests = [sub.test]
            if isinstance(sub.test, ast.BoolOp):
                tests = list(sub.test.values)
            kind_val = None
            for t in tests:
                if isinstance(t, ast.Compare) and len(t.ops) == 1 \
                        and isinstance(t.ops[0], ast.Eq) \
                        and isinstance(t.left, ast.Name) \
                        and t.left.id == "kind" \
                        and isinstance(t.comparators[0], ast.Constant):
                    kind_val = t.comparators[0].value
                    break
            if kind_val is None:
                continue
            info = branches.setdefault(
                kind_val, {"site": sub.lineno, "attrs": {}})
            for n in ast.walk(sub):
                if isinstance(n, ast.Attribute) \
                        and isinstance(n.value, ast.Name):
                    info["attrs"].setdefault(n.value.id, set()).add(n.attr)
    return {k: {"site": v["site"],
                "attrs": {r: sorted(a) for r, a in v["attrs"].items()}}
            for k, v in branches.items()}


def run():
    problems, info = [], []
    app_tree = _parse(APP_PATH)
    host_tree = _parse(HOST_PATH)

    api_methods = set()
    for cname, methods in _class_methods(app_tree).items():
        if "api" in cname.lower():
            api_methods |= methods
    host_methods = _class_methods(host_tree).get("NebulaHost", set())

    rows = row_kinds(app_tree)
    dispatch = dispatch_branches(app_tree)

    for kind, sites in sorted(rows.items()):
        if kind not in dispatch:
            problems.append(
                "ROW-KIND: rows offer %r (%s) but palette_run has no "
                "'%s' branch" % (kind, ", ".join(sites), kind))

    for kind in sorted(dispatch):
        if kind not in rows:
            info.append("DEAD-BRANCH: palette_run handles %r but no row "
                        "offers it (line %d)" % (kind, dispatch[kind]["site"]))
        for recv, attrs in dispatch[kind]["attrs"].items():
            pool = api_methods if recv == "self" else (
                host_methods if recv == "host" else None)
            if pool is None:
                continue
            for attr in attrs:
                if attr not in pool and not attr.startswith("_"):
                    problems.append(
                        "TARGETS: %s.%s (branch %r, line %d) is not a "
                        "method of its receiver" % (recv, attr, kind,
                                                    dispatch[kind]["site"]))

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
            print("[PASS] palette contract holds (%d row kinds, %d branches)"
                  % (len(row_kinds(_parse(APP_PATH))),
                     len(dispatch_branches(_parse(APP_PATH)))))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
