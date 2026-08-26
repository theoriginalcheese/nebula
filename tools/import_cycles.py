"""Import-cycle detector for the obsauto/ and spike/ packages.

    python tools/import_cycles.py          # human report
    python tools/import_cycles.py --json   # machine report

Why this exists
---------------
Import cycles are latent init-order bugs: they work until someone moves an
import to module level or a module grows side effects, then they surface as
partially-initialised imports that no test names directly. This parses each
package's modules with AST (no imports executed) and reports any cycle in
the intra-package dependency graph.

`from . import X`, `from .mod import name`, `import package.mod` and
function-level deferred imports are all counted - a cycle is a cycle even
if both edges are lazy.

Exit 1 if any cycle exists.
"""
import argparse
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGES = ("obsauto", "spike")


def module_imports(path, package):
    """Set of sibling module names this file imports (any level)."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except SyntaxError:
        return set()
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if len(parts) >= 2 and parts[0] == package:
                    mods.add(parts[1])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module:      # from .x import y
                mods.add(node.module.split(".")[0])
            elif node.level and not node.module:  # from . import x
                for alias in node.names:
                    mods.add(alias.name)
            elif node.module and "." not in node.module:
                # absolute intra-package import (spike.host etc.)
                for pkg in PACKAGES:
                    if node.module == pkg or node.module.startswith(
                            pkg + "."):
                        rest = node.module.split(".", 1)
                        if len(rest) == 2:
                            mods.add(rest[1].split(".")[0])
                        break
    mods.discard(os.path.splitext(os.path.basename(path))[0])
    return {m for m in mods
            if os.path.isfile(os.path.join(ROOT, package, m + ".py"))}


def build_graph():
    graph = {}
    for pkg in PACKAGES:
        pkg_dir = os.path.join(ROOT, pkg)
        if not os.path.isdir(pkg_dir):
            continue  # fixture repos may only exercise some packages
        for n in sorted(os.listdir(pkg_dir)):
            if n.endswith(".py") and n != "__init__.py":
                graph[pkg + "/" + n[:-3]] = module_imports(
                    os.path.join(pkg_dir, n), pkg)
    return graph


def find_cycles(graph):
    """Small cycles only (<=4 nodes): anything longer is architecture,
    not drift, and would drown the signal."""
    cycles = set()
    def dfs(node, path, visited_in_path):
        for nxt in sorted(graph.get(node, ())):
            nxt_full = None
            for cand in graph:
                if cand.split("/")[1] == nxt and (
                        cand.split("/")[0] == node.split("/")[0]):
                    nxt_full = cand
                    break
            if nxt_full is None:
                continue
            if nxt_full == path[0] and len(path) >= 2:
                key = tuple(sorted(set(path)))
                cycles.add(key)
            elif nxt_full not in visited_in_path and len(path) < 4:
                dfs(nxt_full, path + [nxt_full],
                    visited_in_path | {nxt_full})
    for start in sorted(graph):
        dfs(start, [start], {start})
    return [list(c) for c in sorted(cycles)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    cycles = find_cycles(build_graph())
    problems = ["CYCLE: " + " -> ".join(c + [c[0]]) for c in cycles]
    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems},
                         indent=2))
    else:
        for p in problems:
            print("[FAIL] " + p)
        if not problems:
            print("[PASS] no import cycles across %d modules (%s)"
                  % (len(build_graph()), ", ".join(PACKAGES)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
