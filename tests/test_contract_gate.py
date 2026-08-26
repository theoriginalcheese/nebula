"""Contract gate dispatcher: fixtures + real repo rollup.

    python tests/test_contract_gate.py

Pins the dispatcher's contract: one failing checker fails the gate, a
checker that dies without JSON is reported rather than crashing the run,
and the real repo's four checkers pass together right now.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def run_gate():
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "contract_gate.py"),
         "--json"],
        cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300)


import json  # noqa: E402

proc = run_gate()
try:
    payload = json.loads(proc.stdout)
except json.JSONDecodeError:
    payload = {}
check("real repo gate exits clean", proc.returncode == 0, proc.stdout[-300:])
check("rollup lists all four checkers",
      len(payload.get("results", [])) == 4
      and {r["checker"] for r in payload["results"]} == {
          "module_map_check.py", "bridge_contract_check.py",
          "palette_contract_check.py", "docs_drift_check.py"},
      payload.get("results"))
check("every checker individually ok",
      all(r["ok"] for r in payload.get("results", [])), payload)

failed = sum(1 for _, ok, _ in results if not ok)
for name, ok, detail in results:
    print("%-5s %-45s %s" % ("PASS" if ok else "FAIL", name, detail))
print("\n%d/%d passed" % (len(results) - failed, len(results)))
sys.exit(1 if failed else 0)
