"""Import-budget tripwire for the main.py entry chain.

    python tests/test_import_budget.py

2026-08-26 deferred gamesync's `requests` (53 ms) and hotkey's `keyboard`
(29 ms) imports off the startup path: 265 ms / 457 modules -> 175 ms / 350.
This test pins the *structural* win so it cannot silently rot. It
deliberately avoids wall-clock assertions - CI runners and desktops differ
too much for a fixed millisecond budget to be honest - and instead asserts
the two things that actually regressed last time:

  1. the entry chain stays under a module-count ceiling;
  2. known-heavy subtrees (requests/urllib3, keyboard) stay out of the
     import path until first use.

A wall-time figure is printed for local information only, never asserted.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODULE_CEILING = 420      # was 457 pre-deferral; 350 as of the fix
BANNED_SUBTREES = ("requests", "urllib3", "keyboard")

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


env = dict(os.environ, PYTHONUTF8="1")
proc = subprocess.run(
    [sys.executable, "-X", "importtime", "-c",
     "from spike.app import main"],
    cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    errors="replace", env=env, timeout=120)

modules = []
total_self_us = 0
for ln in (proc.stderr or "").splitlines():
    if not ln.startswith("import time:"):
        continue
    parts = [p.strip() for p in ln[len("import time:"):].split("|")]
    try:
        total_self_us += int(parts[0])
        modules.append(parts[2].strip() if len(parts) > 2 else "?")
    except (ValueError, IndexError):
        continue

check("entry chain imported cleanly", proc.returncode == 0,
      (proc.stderr or "")[-300:])
check("module count under ceiling (%d <= %d)"
      % (len(modules), MODULE_CEILING),
      len(modules) <= MODULE_CEILING,
      "top offenders: %s" % ", ".join(
          sorted({m.split(".")[0] for m in modules}))[:400])

tops = {m.split(".")[0] for m in modules}
for banned in BANNED_SUBTREES:
    check("heavy subtree '%s' not imported at startup" % banned,
          banned not in tops, "found in: %s" % sorted(tops)[:20])

print("info: %d modules, ~%.0f ms self-time on this machine "
      "(informational only - machines differ)" % (len(modules),
                                                  total_self_us / 1000))

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
