"""Module-map drift detector: logic on fixtures + the real repo must pass.

    python tests/test_module_map_check.py

Fixture cases cover each failure class the detector reports (unmapped file,
ghost path, renamed symbol, missing class/method, allowlist use, stale
allowlist entry). One integration check then runs the detector against the
real CLAUDE.md + tree - which is what makes future drift fail CI instead of
waiting for a human to notice.
"""
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import module_map_check as mm

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


MAP_TMPL = """# Fake project

## Architecture (module map)

| File | Key symbols | Role |
|------|-------------|------|
| `pkg/a.py` | `Alpha`, `helper()`, `LIMIT` | first |
| `pkg/b.py` | `Beta.go()` | second |

## Next heading
"""

A_SRC = ("LIMIT = 5\n"
         "\n"
         "class Alpha:\n"
         "    def go(self):\n"
         "        return 1\n"
         "\n"
         "def helper():\n"
         "    return 2\n")


def make_repo(files=None, map_text=MAP_TMPL):
    tmp = tempfile.mkdtemp(prefix="mmc-fixture-")
    os.makedirs(os.path.join(tmp, "pkg"))
    with open(os.path.join(tmp, "CLAUDE.md"), "w", encoding="utf-8") as f:
        f.write(map_text)
    for rel, src in (files or {"pkg/a.py": A_SRC,
                               "pkg/b.py": "class Beta:\n"
                                           "    def go(self):\n"
                                           "        return 3\n"}).items():
        p = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(src)
    return tmp


def run_in(tmp):
    with mock.patch.object(mm, "ROOT", tmp), \
         mock.patch.object(mm, "CLAUDE_MD", os.path.join(tmp, "CLAUDE.md")), \
         mock.patch.object(mm, "ALLOWLIST", {}):
        # MAPPED_ROOTS is relative names, so point it at the fixture's pkg/.
        with mock.patch.object(mm, "MAPPED_ROOTS", ("pkg",)):
            return mm.run()


def problems_of(tmp):
    return run_in(tmp)[0]


# 1. Clean fixture -> no problems.
tmp = make_repo()
check("clean fixture passes", problems_of(tmp) == [], problems_of(tmp))

# 2. A file on disk with no row is UNMAPPED.
with open(os.path.join(tmp, "pkg", "c.py"), "w", encoding="utf-8") as f:
    f.write("X = 1\n")
probs = problems_of(tmp)
shutil.rmtree(tmp)
check("unmapped file detected",
      any(p.startswith("UNMAPPED: pkg/c.py") for p in probs), probs)

# 3. A map path that does not exist is a GHOST.
tmp = make_repo(map_text=MAP_TMPL.replace("`pkg/b.py`", "`pkg/gone.py`"))
probs = problems_of(tmp)
shutil.rmtree(tmp)
check("ghost path detected",
      any(p.startswith("GHOST:") and "gone.py" in p for p in probs), probs)

# 4. A renamed symbol fails.
tmp = make_repo(files={"pkg/a.py": A_SRC.replace("def helper", "def helper2"),
                       "pkg/b.py": "class Beta:\n    def go(self):\n"
                                   "        return 3\n"})
probs = problems_of(tmp)
shutil.rmtree(tmp)
check("renamed function detected",
      any("'helper'" in p and "SYMBOL" in p for p in probs), probs)

# 5. Missing method on a mapped class fails.
tmp = make_repo(files={"pkg/b.py": "class Beta:\n    def fly(self):\n"
                                   "        return 9\n"})
probs = problems_of(tmp)
shutil.rmtree(tmp)
check("missing method detected",
      any("method 'go'" in p for p in probs), probs)

# 6. Missing class fails.
tmp = make_repo(files={"pkg/b.py": ""})
probs = problems_of(tmp)
shutil.rmtree(tmp)
check("missing class detected",
      any("'Beta' not found" in p for p in probs), probs)

# 7. Constants satisfy symbol claims.
tmp = make_repo()
probs = problems_of(tmp)
shutil.rmtree(tmp)
check("constant LIMIT resolves",
      not any("LIMIT" in p for p in probs), probs)

# 8. Allowlist silences UNMAPPED and reports its reason.
tmp = make_repo(files={"pkg/a.py": A_SRC, "pkg/b.py": "Y = 2\n"})
os.remove(os.path.join(tmp, "pkg", "b.py"))
with open(os.path.join(tmp, "pkg", "legacy.py"), "w", encoding="utf-8") as f:
    f.write("# dead\n")
with mock.patch.object(mm, "ALLOWLIST",
                       {"legacy.py": "kept on purpose"}), \
     mock.patch.object(mm, "ROOT", tmp), \
     mock.patch.object(mm, "CLAUDE_MD", os.path.join(tmp, "CLAUDE.md")), \
     mock.patch.object(mm, "MAPPED_ROOTS", ("pkg",)):
    probs, used = mm.run()
shutil.rmtree(tmp)
check("allowlisted file not a problem",
      not any("legacy.py" in p for p in probs), probs)
check("allowlist reason surfaced",
      used.get("legacy.py") == "kept on purpose", used)

# 9. An allowlist entry whose file vanished is itself flagged.
tmp = make_repo(files={"pkg/b.py": "Y = 2\n"})
os.remove(os.path.join(tmp, "pkg", "b.py"))
with mock.patch.object(mm, "ALLOWLIST", {"vanished.py": "old"}, ), \
     mock.patch.object(mm, "ROOT", tmp), \
     mock.patch.object(mm, "CLAUDE_MD", os.path.join(tmp, "CLAUDE.md")), \
     mock.patch.object(mm, "MAPPED_ROOTS", ("pkg",)):
    probs, _ = mm.run()
shutil.rmtree(tmp)
check("stale allowlist entry detected",
      any("STALE ALLOWLIST" in p and "vanished.py" in p for p in probs),
      probs)

# 10. Integration: the real repo's map must match reality right now.
real_probs, _used = mm.run()
check("REAL REPO: CLAUDE.md module map matches disk", not real_probs,
      real_probs)

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
