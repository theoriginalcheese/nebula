"""Module-map drift detector: CLAUDE.md's map vs the code on disk.

    python tools/module_map_check.py          # human report
    python tools/module_map_check.py --json   # machine report for agents

Why this exists
---------------
The module map in CLAUDE.md is how an agent orients without reading every
file. It has already drifted twice - once for whole modules (nine obsauto
files existed with no row) and once for a claim about a deleted file that
wasn't deleted. Both were only found by a human reading carefully. This tool
makes that a test failure instead.

What it checks (against the "Architecture (module map)" section):
  1. Every .py under a mapped root (obsauto/, spike/, plus root main.py)
     has a row in the map - or an allowlisted reason.
  2. Every .py path named in the map exists on disk (no ghosts).
  3. Every key symbol in a row's second column resolves in that row's file:
     top-level function/class/constant via AST, and Name.method() pairs are
     checked down to the method. No imports, no side effects.

Exit code 1 on any drift, so CI and run_tests can gate on it.
"""
import argparse
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")

# Roots whose every module must be mapped. Root-level scripts other than
# main.py (leaktest.py etc.) are deliberately out of scope.
MAPPED_ROOTS = ("obsauto", "spike")
ROOT_ENTRYPOINTS = ("main.py",)

# Files exempt from check 1. Reasons are printed when used so stale entries
# get noticed. Keep this short - it is a debt list, not a bin.
ALLOWLIST = {
    "obs_auto_game_folder.py":
        "legacy pre-v4 standalone script still on disk but dead - superseded "
        "by main.py -> spike.app.main; nothing imports it",
}


def map_section(text):
    """Return just the '## Architecture (module map)' section."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+.*module map", ln, re.IGNORECASE):
            start = i
            break
    if start is None:
        return []
    out = []
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        out.append(ln)
    return out


def parse_rows(section_lines):
    """Extract (raw_path_tokens, symbol_tokens) from markdown table rows."""
    rows = []
    for ln in section_lines:
        if not ln.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 3 or set(cells[0]) <= set("- :"):
            continue
        paths = re.findall(r"`([^`]+\.py)`", cells[0])
        syms = re.findall(r"`([^`]+)`", cells[1]) if len(cells) > 1 else []
        rows.append((paths, syms))
    return rows


def resolve_path(token, first_dir):
    """Resolve a map path token against the repo, trying likely roots."""
    token = token.replace("\\", "/")
    cands = [token]
    if not token.startswith(("obsauto/", "spike/", "tests/", "tools/")):
        if first_dir:
            cands.append(first_dir + "/" + token)
        for r in MAPPED_ROOTS:
            cands.append(r + "/" + token)
    for c in cands:
        p = os.path.join(ROOT, *c.split("/"))
        if os.path.isfile(p):
            return c, p
    return None, None


def _stmt_names(stmts, names):
    """Collect def/class/constant names from a statement list, recursing
    into module-level control flow (paths.py assigns APP_DIR inside an if)
    but never into function or class bodies."""
    for node in stmts:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target,
                                                            ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For,
                               ast.While)):
            blocks = list(getattr(node, "body", [])) \
                + list(getattr(node, "orelse", [])) \
                + list(getattr(node, "finalbody", []))
            _stmt_names(blocks, names)


def _top_level_names(tree):
    """Top-level functions, classes and assigned constants of a module."""
    names = set()
    _stmt_names(tree.body, names)
    return names


def _method_names(tree, cls):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            return {n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return set()


def load_module(path_on_disk):
    try:
        with open(path_on_disk, encoding="utf-8") as f:
            return ast.parse(f.read())
    except (OSError, SyntaxError) as exc:
        print("WARN cannot parse %s: %s" % (path_on_disk, exc))
        return None


def check_symbols(rows, problems):
    """Check 2 (ghosts) and 3 (symbols) over parsed rows."""
    for raw_paths, syms in rows:
        resolved, missing = [], []
        first_dir = ""
        m = raw_paths[0].rsplit("/", 1) if raw_paths else None
        if m and len(m) == 2:
            first_dir = m[0]
        for tok in raw_paths:
            rel, disk = resolve_path(tok, first_dir)
            if disk is None:
                missing.append(tok)
            else:
                resolved.append((rel, disk))
        for tok in missing:
            problems.append("GHOST: map names '%s' but it is not on disk"
                            % tok)
        if not syms or syms == ["-"]:
            continue
        trees = []
        for _, disk in resolved:
            t = load_module(disk)
            if t is not None:
                trees.append(t)
        tops = set().union(*[_top_level_names(t) for t in trees]) \
            if trees else set()
        methods = {}
        for t in trees:
            for n in ast.walk(t):
                if isinstance(n, ast.ClassDef):
                    methods.setdefault(
                        n.name,
                        {m.name for m in n.body
                         if isinstance(m, (ast.FunctionDef,
                                           ast.AsyncFunctionDef))})
        for sym in syms:
            sym = sym.strip()
            if "." in sym:
                cls, meth = sym.split(".", 1)
                meth = meth.rstrip("()")
                if cls not in tops:
                    problems.append(
                        "SYMBOL: '%s' - class %r not found in [%s]"
                        % (sym, cls, ", ".join(r for r, _ in resolved)))
                elif meth not in methods.get(cls, set()):
                    problems.append(
                        "SYMBOL: method '%s' missing on %s.%s"
                        % (meth, cls, cls))
            else:
                name = sym.rstrip("()")
                if name.startswith("test_") or name in ("main",):
                    continue  # entry points may live anywhere / be shimmed
                if name not in tops:
                    problems.append(
                        "SYMBOL: '%s' not a top-level name in [%s]"
                        % (name, ", ".join(r for r, _ in resolved)))


def scan_disk():
    """Every module under a mapped root, plus root entrypoints, as repo-rel."""
    found = []
    for r in MAPPED_ROOTS:
        d = os.path.join(ROOT, r)
        for n in sorted(os.listdir(d)):
            if n.endswith(".py") and n != "__init__.py":
                found.append(r + "/" + n)
    for n in ROOT_ENTRYPOINTS:
        if os.path.isfile(os.path.join(ROOT, n)):
            found.append(n)
    return found


def check_coverage(mapped_names, used_allow, problems):
    """Check 1: everything on disk has a row (or an allowlist reason)."""
    for rel in scan_disk():
        base = os.path.basename(rel)
        if rel in mapped_names or base in mapped_names:
            continue
        if base in ALLOWLIST:
            used_allow[base] = ALLOWLIST[base]
            continue
        problems.append(
            "UNMAPPED: %s exists but has no row in the CLAUDE.md module map"
            % rel)


def run():
    problems = []
    used_allow = {}
    with open(CLAUDE_MD, encoding="utf-8") as f:
        text = f.read()
    section = map_section(text)
    if not section:
        problems.append("MAP MISSING: no '## ... module map' heading found")
        return problems, used_allow
    rows = parse_rows(section)
    if not rows:
        problems.append("MAP EMPTY: section exists but no table rows parsed")
        return problems, used_allow
    check_symbols(rows, problems)
    mapped = set()
    for raw_paths, _ in rows:
        for tok in raw_paths:
            mapped.add(tok)
            mapped.add(os.path.basename(tok))
    check_coverage(mapped, used_allow, problems)
    # An allowlist entry whose file vanished should itself be pruned.
    # Allowlisted files may sit at the repo root, outside the mapped roots.
    known = {os.path.basename(p) for p in scan_disk()}
    for n in sorted(os.listdir(ROOT)):
        if n.endswith(".py"):
            known.add(n)
    for gone in sorted(set(ALLOWLIST) - known):
        problems.append(
            "STALE ALLOWLIST: '%s' is allowlisted but no longer on disk - "
            "remove it" % gone)
    return problems, used_allow


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true",
                    help="emit one JSON object instead of text")
    args = ap.parse_args(argv)

    problems, used_allow = run()

    if args.json:
        print(json.dumps({
            "ok": not problems,
            "problems": problems,
            "allowlisted": used_allow,
        }, indent=2))
    else:
        for p in problems:
            print("[FAIL] " + p)
        for k in sorted(used_allow):
            print("[ALLOW] %s - %s" % (k, used_allow[k]))
        if not problems:
            print("[PASS] module map matches the code (%d files scanned)"
                  % len(scan_disk()))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
