"""Requirements drift: third-party imports in app code vs requirements.txt.

    python tools/requirements_check.py          # human report
    python tools/requirements_check.py --json

Two drift directions, both real failure modes here:

  MISSING   - code imports a third-party distribution that
              requirements.txt does not declare. In dev this "works" until
              a fresh checkout or the packaged build; in frozen builds it
              is exactly how silent feature loss happens (see the spec's
              win32ui note).
  UNUSED    - requirements.txt declares a distribution no module imports.
              Sometimes deliberate (transitive or data-file needs), so
              each declared-but-unimported entry needs a reason to stay.

Import-name -> distribution-name mapping handles the classic mismatches
(websocket-client imports as `websocket`, pywin32 as win32*, Pillow as
PIL, pywebview as webview). Stdlib is excluded via sys.stdlib_module_names.

Exit 1 on MISSING only; UNUSED prints with its reason.
"""
import argparse
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCANNED = ("obsauto", "spike")
SKIP_FILES = {"gui.py", "theme_art.py"}  # legacy Tk shell, audited separately
ENTRYPOINTS = ("main.py",)

# import name -> distribution name in requirements.txt
ALIASES = {
    "websocket": "websocket-client",
    "win32api": "pywin32", "win32con": "pywin32",
    "win32gui": "pywin32", "win32ui": "pywin32", "pythoncom": "pywin32",
    "win32process": "pywin32", "win32file": "pywin32",
    "win32com": "pywin32",
    "PIL": "Pillow",
    "webview": "pywebview",
}

# Import names that are not distributions at all: .NET namespaces reached
# through pythonnet's CLR bridge, and the repo's own packages when imported
# absolutely from spike/.
NON_DISTRIBUTIONS = {"System", "obsauto", "spike", "tools"}

# Distributions kept on purpose though no scanned import references them,
# with the reason an agent (or Anthony) should see when this fires.
KNOWN_KEEP = {
    "customtkinter": "legacy gui.py + its test suite; retires with "
                     "the gui.py retirement plan",
}


def _is_stdlib(top):
    return top in getattr(sys, "stdlib_module_names", ()) or top in (
        "ctypes",)  # belt and braces for older interpreters


def imported_dists():
    """Third-party top-level import names across scanned app code."""
    found = {}  # import-name -> first site
    for d in SCANNED:
        for n in sorted(os.listdir(os.path.join(ROOT, d))):
            if not n.endswith(".py") or n in SKIP_FILES:
                continue
            path = os.path.join(ROOT, d, n)
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.level == 0:
                        names = [node.module.split(".")[0]]
                for name in names:
                    if name in NON_DISTRIBUTIONS:
                        continue
                    if name in ALIASES:
                        key = ALIASES[name]
                    elif _is_stdlib(name):
                        continue
                    else:
                        key = name
                    # local intra-package modules are not distributions
                    if any(os.path.isfile(os.path.join(ROOT, pkg,
                                                       name + ".py"))
                           for pkg in SCANNED):
                        continue
                    found.setdefault(key, "%s/%s:%d"
                                     % (d, n, node.lineno))
    for n in ENTRYPOINTS:
        path = os.path.join(ROOT, n)
        if os.path.isfile(path):
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module \
                        and node.module.split(".")[0] == "spike":
                    found.setdefault("spike(self)", "-")
    return found


def declared_dists():
    out = {}
    path = os.path.join(ROOT, "requirements.txt")
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            name = re.split(r"[=<>~!;]", ln, 1)[0].strip()
            if name:
                out[name.lower()] = True
    return list(out)


def run():
    problems, notes = [], []
    imported = {k: v for k, v in imported_dists().items()
                if k != "spike(self)"}
    declared = [d.lower() for d in declared_dists()]

    for dist, site in sorted(imported.items()):
        if dist.lower() not in declared:
            problems.append(
                "MISSING: code imports '%s' (%s) but requirements.txt "
                "does not declare it" % (dist, site))

    for dist in declared:
        if dist not in {k.lower() for k in imported}:
            reason = KNOWN_KEEP.get(dist)
            if reason:
                notes.append("UNUSED-KEPT: %s - %s" % (dist, reason))
            else:
                problems.append(
                    "UNUSED: requirements.txt declares '%s' but no scanned "
                    "module imports it - declare a reason or drop it"
                    % dist)
    return problems, notes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    problems, notes = run()
    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems,
                          "notes": notes}, indent=2))
    else:
        for p in problems:
            print("[FAIL] " + p)
        for n in notes:
            print("[NOTE] " + n)
        if not problems:
            print("[PASS] requirements match imports "
                  "(%d declared, %d imported)"
                  % (len(declared_dists()), len(imported_dists()) - 1))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
