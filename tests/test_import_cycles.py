"""Import-cycle detector: fixture packages with known cycles + real repo.

    python tests/test_import_cycles.py

Cycles are latent init-order bugs - they work until someone moves an
import or grows module side effects. Fixtures pin detection of a direct
two-module cycle and non-detection of clean one-way deps; the final check
asserts the real obsauto/ + spike/ graph is cycle-free right now.
"""
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import import_cycles as ic

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def make_repo(files):
    tmp = tempfile.mkdtemp(prefix="icyc-fixture-")
    for rel, src in files.items():
        p = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(src)
    return tmp


# 1. Direct two-module cycle is found.
tmp = make_repo({
    "obsauto/a.py": "from . import b\n\ndef fa():\n    return b.fb()\n",
    "obsauto/b.py": "from . import a\n\ndef fb():\n    return 1\n",
})
with mock.patch.object(ic, "ROOT", tmp):
    cycles = ic.find_cycles(ic.build_graph())
shutil.rmtree(tmp)
check("two-module cycle detected",
      any(set(c) == {"obsauto/a", "obsauto/b"} for c in cycles), cycles)

# 2. One-way dependency is not a cycle.
tmp = make_repo({
    "obsauto/a.py": "from . import b\n\ndef fa():\n    return b.fb()\n",
    "obsauto/b.py": "def fb():\n    return 1\n",
})
with mock.patch.object(ic, "ROOT", tmp):
    cycles = ic.find_cycles(ic.build_graph())
shutil.rmtree(tmp)
check("one-way dep not flagged", not cycles, cycles)

# 3. Deferred (function-level) imports still count.
tmp = make_repo({
    "obsauto/a.py": "def fa():\n    from . import b\n    return b.fb()\n",
    "obsauto/b.py": "def fb():\n    from . import a\n    return 1\n",
})
with mock.patch.object(ic, "ROOT", tmp):
    cycles = ic.find_cycles(ic.build_graph())
shutil.rmtree(tmp)
check("deferred imports still detected as cycle",
      any(set(c) == {"obsauto/a", "obsauto/b"} for c in cycles), cycles)

# 4. External stdlib/third-party imports are ignored.
tmp = make_repo({
    "obsauto/a.py": "import json\nimport requests\n\ndef fa():\n"
                    "    return json.dumps({})\n",
})
with mock.patch.object(ic, "ROOT", tmp), \
     mock.patch.object(ic, "PACKAGES", ("obsauto",)):
    cycles = ic.find_cycles(ic.build_graph())
shutil.rmtree(tmp)
check("external imports ignored", not cycles, cycles)

# 5. Integration: the real packages are cycle-free right now.
real_cycles = ic.find_cycles(ic.build_graph())
check("REAL REPO: no import cycles", not real_cycles, real_cycles)

failed = sum(1 for _, ok, _ in results if not ok)
for name, ok, detail in results:
    print("%-5s %-48s %s" % ("PASS" if ok else "FAIL", name, detail))
print("\n%d/%d passed" % (len(results) - failed, len(results)))
sys.exit(1 if failed else 0)
