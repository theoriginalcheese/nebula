"""JS-bridge contract checker: what spike/web/*.js calls vs what Python exposes.

    python tools/bridge_contract_check.py          # human report
    python tools/bridge_contract_check.py --json   # machine report

Why this exists
---------------
The v4 UI is a WebView whose JS talks to Python through pywebview's js_api.
No linter sees that boundary: renaming an Api method in Python leaves every
`window.pywebview.api.<name>()` call in app.js/toast.js/overlay.js pointing
at a method that no longer exists - and under pywebview that surfaces at
runtime as a JS exception (or a silent undefined), never a test failure.

What it checks:
  1. MISSING  - a JS call to `pywebview.api.X()` where no Api-class method X
     exists on the Python side. Hard failure.
  2. UNCALLED - public methods exposed by an Api class that no JS file calls.
     Informational only: some are invoked via palette actions or pushed JS,
     and dead-exposure is a cleanup hint, not a defect.

Api classes are found by name (`*Api*` classes in spike/*.py); their public
methods (no leading underscore) form the exposed surface. Calls are matched
literally as written - there is no dynamic `api[name]()` dispatch anywhere
in spike/web (this tool fails loudly if one appears, see DYNAMIC check).
"""
import argparse
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPIKE = os.path.join(ROOT, "spike")
WEB = os.path.join(SPIKE, "web")

# window.pywebview.api.name(  /  pywebview.api.name(   (optional chaining too)
CALL_RE = re.compile(
    r"\b(?:window\s*\.\s*)?pywebview\s*\.\s*api\s*\.\s*([A-Za-z_]\w*)\s*\(")
# Any bracket-indexed access would be dynamic dispatch we cannot verify.
DYNAMIC_RE = re.compile(r"pywebview\s*\.\s*api\s*\[")


def exposed_methods():
    """Union of public methods across every *Api* class in spike/*.py."""
    out = {}
    for n in sorted(os.listdir(SPIKE)):
        if not n.endswith(".py"):
            continue
        path = os.path.join(SPIKE, n)
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except (OSError, SyntaxError) as exc:
            out.setdefault("PARSE_ERROR:" + n, set()).add(str(exc))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "api" in node.name.lower():
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef,
                                         ast.AsyncFunctionDef)) \
                            and not item.name.startswith("_"):
                        out.setdefault(item.name, set()).add(
                            "%s:%s" % (n, node.name))
    return {k: sorted(v) for k, v in out.items()}


def js_calls():
    """Every api.<name>( in spike/web/*.js, with first call site per name."""
    calls = {}
    dynamics = []
    if not os.path.isdir(WEB):
        return calls, dynamics
    for n in sorted(os.listdir(WEB)):
        if not n.endswith(".js"):
            continue
        with open(os.path.join(WEB, n), encoding="utf-8") as f:
            text = f.read()
        if DYNAMIC_RE.search(text):
            dynamics.append(n)
        for m in CALL_RE.finditer(text):
            calls.setdefault(m.group(1),
                             "%s:%d" % (n, text[:m.start()].count("\n") + 1))
    return calls, dynamics


def run():
    problems = []
    info = []
    exposed = exposed_methods()
    parse_errors = {k: v for k, v in exposed.items()
                    if k.startswith("PARSE_ERROR")}
    methods = {k: v for k, v in exposed.items()
               if not k.startswith("PARSE_ERROR")}
    for k, v in parse_errors.items():
        problems.append("%s: %s" % (k, "; ".join(v)))

    calls, dynamics = js_calls()
    for n in dynamics:
        problems.append("DYNAMIC: %s indexes pywebview.api[...] - this tool "
                        "cannot verify dynamic dispatch; keep bridge calls "
                        "literal or extend the checker" % n)

    missing = sorted(set(calls) - set(methods))
    for name in missing:
        problems.append("MISSING: %s() called at %s but exposed by no Api "
                        "class in spike/" % (name, calls[name]))

    uncalled = sorted(set(methods) - set(calls))
    for name in uncalled:
        info.append("UNCALLED: %s (%s)" % (name,
                                           ", ".join(methods[name])))
    return problems, info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true",
                    help="emit one JSON object instead of text")
    args = ap.parse_args(argv)

    problems, info = run()
    if args.json:
        print(json.dumps({
            "ok": not problems,
            "problems": problems,
            "uncalled": info,
        }, indent=2))
    else:
        for p in problems:
            print("[FAIL] " + p)
        for i in info:
            print("[INFO] " + i)
        if not problems:
            print("[PASS] JS bridge contract holds "
                  "(%d exposed methods, %d called)"
                  % (len(exposed_methods()), len(js_calls()[0])))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
