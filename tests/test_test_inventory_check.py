"""Test-inventory checker: docstring coverage + CLAUDE.md ghost paths.

    python tests/test_test_inventory_check.py

The suite is self-inventoried via run_tests.py, so prose lists can't go
stale-complete - but every test/tool must carry a module docstring and
CLAUDE.md must not name test files that don't exist. A UTF-8 BOM is
tolerated exactly like the interpreter tolerates it (it has slipped into
committed source once already), not misread as a syntax error.
"""
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import test_inventory_check as tic

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def make_repo(files=None):
    tmp = tempfile.mkdtemp(prefix="tic-fixture-")
    tests = os.path.join(tmp, "tests")
    tools = os.path.join(tmp, "tools")
    os.makedirs(tests)
    os.makedirs(tools)
    open(os.path.join(tmp, "CLAUDE.md"), "w", encoding="utf-8").write("")
    open(os.path.join(tests, "__init__.py"), "w").write("")
    for rel, src in (files or {}).items():
        p = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        mode = "wb" if isinstance(src, bytes) else "w"
        f = open(p, mode) if isinstance(src, bytes) else open(
            p, "w", encoding="utf-8")
        f.write(src)
        f.close()
    return tmp


def run_in(tmp):
    with mock.patch.object(tic, "ROOT", tmp), \
         mock.patch.object(tic, "TESTS", os.path.join(tmp, "tests")), \
         mock.patch.object(tic, "TOOLS", os.path.join(tmp, "tools")), \
         mock.patch.object(tic, "CLAUDE_MD",
                           os.path.join(tmp, "CLAUDE.md")):
        return tic.run()


# 1. Docstring everywhere passes.
tmp = make_repo({
    "tests/test_ok.py": '"""Pins X."""\nassert True\n',
    "tools/checker.py": '"""Checks Y."""\nimport os\n',
})
probs = run_in(tmp)
shutil.rmtree(tmp)
check("documented files pass", probs == [], probs)

# 2. A missing docstring is NO-DOCSTRING.
tmp = make_repo({"tests/test_bare.py": "assert True\n"})
probs = run_in(tmp)
shutil.rmtree(tmp)
check("undocumented file flagged",
      any("NO-DOCSTRING" in p and "test_bare" in p for p in probs), probs)

# 3. Tools are held to the same rule.
tmp = make_repo({"tools/bare_checker.py": "import os\n"})
probs = run_in(tmp)
shutil.rmtree(tmp)
check("undocumented tool flagged",
      any("bare_checker" in p for p in probs), probs)

# 4. A BOM'd file parses fine (not a syntax error).
tmp = make_repo()
bom_path = os.path.join(tmp, "tests", "test_bom.py")
with open(bom_path, "wb") as f:
    f.write(b'\xef\xbb\xbf"""Bommed docstring."""\nassert True\n')
probs = run_in(tmp)
shutil.rmtree(tmp)
check("BOM tolerated like the interpreter does", probs == [], probs)

# 5. CLAUDE.md naming a nonexistent test is a GHOST.
tmp = make_repo({
    "tests/test_real.py": '"""Real."""\n',
    "CLAUDE.md": "Run `python tests/test_ghosty.py` for nothing.\n",
})
probs = run_in(tmp)
shutil.rmtree(tmp)
check("ghost doc path detected",
      any("GHOST" in p and "test_ghosty" in p for p in probs), probs)

# 6. Integration: real repo fully documented, no ghosts.
real_probs = tic.run()
check("REAL REPO: inventory documented, no ghosts", not real_probs,
      real_probs)

failed = sum(1 for _, ok, _ in results if not ok)
for name, ok, detail in results:
    print("%-5s %-50s %s" % ("PASS" if ok else "FAIL", name, detail))
print("\n%d/%d passed" % (len(results) - failed, len(results)))
sys.exit(1 if failed else 0)
