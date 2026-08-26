"""Log-tag linter: fixtures per verdict class + real repo.

    python tests/test_log_tags_check.py

The `[Area]` prefix is what operators and agents grep obsauto.log by.
Fixtures pin BAD-TAG (malformed shape), CASE-COLLISION ([Sync] vs [sync]),
and DYNAMIC (runtime-built tags reported for review, not failed); the
final check runs against the real repo.
"""
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import log_tags_check as ltc

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


GOOD = "x._log('[Sync] GitHub fetch failed.')\n"


def make_repo(files):
    tmp = tempfile.mkdtemp(prefix="ltc-fixture-")
    obs = os.path.join(tmp, "obsauto")
    os.makedirs(obs)
    open(os.path.join(obs, "__init__.py"), "w").write("")
    for rel, src in files.items():
        open(os.path.join(tmp, *rel.split("/")), "w",
             encoding="utf-8").write(src)
    return tmp


def run_in(tmp):
    with mock.patch.object(ltc, "ROOT", tmp), \
         mock.patch.object(ltc, "SCANNED", ("obsauto",)):
        return ltc.run()


# 1. Well-formed tags pass.
tmp = make_repo({"obsauto/a.py": GOOD})
probs, _ = run_in(tmp)
shutil.rmtree(tmp)
check("well-formed tags pass", probs == [], probs)

# 2. Lowercase / malformed shape fails.
tmp = make_repo({"obsauto/a.py": "x._log('[sync] oops')\n"})
probs, _ = run_in(tmp)
shutil.rmtree(tmp)
check("bad tag shape detected",
      any(p.startswith("BAD-TAG") and "[sync]" in p for p in probs), probs)

# 3. Case collision across files fails.
tmp = make_repo({
    "obsauto/a.py": GOOD,
    "obsauto/b.py": "y._log('[SYNC] other')\n",
})
probs, _ = run_in(tmp)
shutil.rmtree(tmp)
check("case collision detected",
      any(p.startswith("CASE-COLLISION") for p in probs), probs)

# 4. Runtime-built tags are DYNAMIC info, not failures.
tmp = make_repo({"obsauto/a.py": "z._log(f'[{area}] message')\n"})
probs, info = run_in(tmp)
shutil.rmtree(tmp)
check("dynamic tag surfaces as info",
      probs == [] and any(i.startswith("DYNAMIC:") for i in info),
      (probs, info))

# 5. Integration: the real repo's tags are all clean right now.
real_probs, _ = ltc.run()
check("REAL REPO: log tags clean", not real_probs, real_probs)

failed = sum(1 for _, ok, _ in results if not ok)
for name, ok, detail in results:
    print("%-5s %-42s %s" % ("PASS" if ok else "FAIL", name, detail))
print("\n%d/%d passed" % (len(results) - failed, len(results)))
sys.exit(1 if failed else 0)
