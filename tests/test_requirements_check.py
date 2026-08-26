"""Requirements drift checker: fixture repos + real repo.

    python tests/test_requirements_check.py

Both drift directions have bitten packaged Python apps here: undeclared
imports work on the dev machine and vanish in fresh checkouts / frozen
builds; stale declarations linger with nobody knowing why. Fixtures cover
MISSING, UNUSED (with and without a keep-reason), alias mapping
(websocket-client imports as `websocket`), and stdlib exclusion; the final
check runs against the real repo.
"""
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import requirements_check as rc

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


REQ = "websocket-client\nrequests\n"

APP_OK = ("import json\n"
          "import websocket\n"
          "import requests\n"
          "\n"
          "def go():\n"
          "    return requests.get\n")


def make_repo(req=REQ, app=APP_OK):
    tmp = tempfile.mkdtemp(prefix="reqc-fixture-")
    obs = os.path.join(tmp, "obsauto")
    os.makedirs(obs)
    open(os.path.join(tmp, "requirements.txt"), "w",
         encoding="utf-8").write(req)
    open(os.path.join(obs, "app.py"), "w", encoding="utf-8").write(app)
    return tmp


def run_in(tmp):
    with mock.patch.object(rc, "ROOT", tmp), \
         mock.patch.object(rc, "SCANNED", ("obsauto",)), \
         mock.patch.object(rc, "ENTRYPOINTS", ()):
        return rc.run()


# 1. Clean: aliases map, stdlib ignored.
tmp = make_repo()
probs, notes = run_in(tmp)
check("clean fixture passes", probs == [], probs)
shutil.rmtree(tmp)

# 2. Undeclared third-party import is MISSING.
tmp = make_repo(app=APP_OK + "import flask\n")
probs, _ = run_in(tmp)
shutil.rmtree(tmp)
check("undeclared import detected",
      any("MISSING" in p and "flask" in p for p in probs), probs)

# 3. Declared-but-unimported without a reason is UNUSED (hard).
tmp = make_repo(req=REQ + "some-orphan\n")
probs, _ = run_in(tmp)
shutil.rmtree(tmp)
check("unused declaration is a failure",
      any("UNUSED" in p and "some-orphan" in p for p in probs), probs)

# 4. Unused-with-reason is a note, not a failure.
tmp = make_repo(req=REQ + "customtkinter\n")
probs, notes = run_in(tmp)
shutil.rmtree(tmp)
check("reasoned unused passes with note",
      probs == [] and any("customtkinter" in n for n in notes),
      (probs, notes))

# 5. Real repo: requirements match imports.
real_probs, _ = rc.run()
check("REAL REPO: requirements match imports", not real_probs, real_probs)

failed = sum(1 for _, ok, _ in results if not ok)
for name, ok, detail in results:
    print("%-5s %-45s %s" % ("PASS" if ok else "FAIL", name, detail))
print("\n%d/%d passed" % (len(results) - failed, len(results)))
sys.exit(1 if failed else 0)
