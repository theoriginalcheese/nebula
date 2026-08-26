"""Contract gate: run every doc/surface checker in one pass.

    python tools/contract_gate.py          # human report
    python tools/contract_gate.py --json   # rollup for agents/CI

Runs the four string-typed-boundary checkers as subprocesses (same process
isolation the test suite uses, so one checker crashing can't take the gate
down) and fails if any does:

  - module_map_check.py      CLAUDE.md map vs disk
  - bridge_contract_check.py JS pywebview.api calls vs Api methods
  - palette_contract_check.py palette rows vs dispatch branches
  - docs_drift_check.py      README config table vs DEFAULTS
  - import_cycles.py         intra-package dependency cycles

Exit 1 if any checker reports problems.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKERS = (
    "module_map_check.py",
    "bridge_contract_check.py",
    "palette_contract_check.py",
    "docs_drift_check.py",
    "import_cycles.py",
)


def main(argv=None):
    as_json = "--json" in (argv or sys.argv[1:])
    results = []
    failed = False
    for name in CHECKERS:
        path = os.path.join(ROOT, "tools", name)
        proc = subprocess.run(
            [sys.executable, path, "--json"],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120)
        try:
            payload = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            payload = {"ok": False,
                       "problems": ["checker produced no JSON: %s"
                                    % (proc.stderr or "")[-200:]]}
        ok = proc.returncode == 0 and payload.get("ok", False)
        failed = failed or not ok
        results.append({"checker": name, "ok": ok,
                        "problems": payload.get("problems", [])})

    if as_json:
        print(json.dumps({"ok": not failed, "results": results}, indent=2))
    else:
        for r in results:
            print("%-4s %s" % ("PASS" if r["ok"] else "FAIL", r["checker"]))
            for p in r["problems"]:
                print("       %s" % p)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
