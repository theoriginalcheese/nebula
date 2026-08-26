"""Palette contract checker: fixtures per failure class + real repo.

    python tests/test_palette_contract_check.py

The palette is a string-typed dispatcher: rows carry ("kind", arg) and
palette_run hand-matches branches calling host/self methods by name. A
renamed method or a misspelled kind surfaces only when that exact row runs
in the UI. Fixtures pin each verdict class; the final check runs against
the real repo and must be clean.
"""
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import palette_contract_check as pcc

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


APP_OK = (
    "import palette as palette_mod\n"
    "class Api:\n"
    "    def _palette_rows(self):\n"
    "        rows = []\n"
    "        add = rows.append\n"
    "        add(palette_mod.Row('Actions', 'Go', ('goto', pane)))\n"
    "        add(palette_mod.Row('Actions', 'Ping', ('ping', 'x')))\n"
    "        return rows\n"
    "\n"
    "    def reveal_config(self):\n"
    "        pass\n"
    "\n"
    "    def palette_run(self, action):\n"
    "        kind, arg = action[0], action[1]\n"
    "        if kind == 'goto':\n"
    "            self._goto_pane = arg\n"
    "            return {'ok': True}\n"
    "        if kind == 'ping' and self:\n"
    "            self.reveal_config()\n"
    "            return {'ok': True}\n"
    "        return {'ok': False, 'error': 'unknown action %r' % kind}\n")

HOST_OK = ("class NebulaHost:\n"
           "    def show_mini(self):\n"
           "        pass\n")


def make_repo(app=APP_OK, host=HOST_OK):
    tmp = tempfile.mkdtemp(prefix="palcc-fixture-")
    spike = os.path.join(tmp, "spike")
    os.makedirs(spike)
    open(os.path.join(spike, "app.py"), "w", encoding="utf-8").write(app)
    open(os.path.join(spike, "host.py"), "w", encoding="utf-8").write(host)
    return tmp


def run_in(tmp):
    with mock.patch.object(pcc, "ROOT", tmp), \
         mock.patch.object(pcc, "APP_PATH",
                           os.path.join(tmp, "spike", "app.py")), \
         mock.patch.object(pcc, "HOST_PATH",
                           os.path.join(tmp, "spike", "host.py")):
        return pcc.run()


# 1. Clean fixture.
tmp = make_repo()
probs, info = run_in(tmp)
check("clean fixture passes", probs == [], probs)
shutil.rmtree(tmp)

# 2. A row whose kind has no dispatch branch is ROW-KIND.
tmp = make_repo(app=APP_OK.replace(
    "('ping', 'x')", "('pang', 'x')"))
probs, _ = run_in(tmp)
shutil.rmtree(tmp)
check("unhandled row kind detected",
      any(p.startswith("ROW-KIND") and "'pang'" in p for p in probs), probs)

# 3. A dispatch branch no row offers is DEAD-BRANCH info.
tmp = make_repo(app=APP_OK.replace(
    "        return {'ok': False, 'error': 'unknown action %r' % kind}",
    "        if kind == 'lonely':\n"
    "            return {'ok': True}\n"
    "        return {'ok': False, 'error': 'unknown action %r' % kind}"))
probs, info = run_in(tmp)
shutil.rmtree(tmp)
check("dead branch passes with info",
      probs == [] and any("'lonely'" in i and i.startswith("DEAD-BRANCH:")
                          for i in info),
      (probs, info))

# 4. A branch calling a method its receiver lacks is TARGETS.
tmp = make_repo(app=APP_OK.replace("self.reveal_config()",
                                   "self.vanish_config()"))
probs, _ = run_in(tmp)
shutil.rmtree(tmp)
check("missing target method detected",
      any(p.startswith("TARGETS") and "vanish_config" in p for p in probs),
      probs)

# 5. host.-receiver methods resolve against NebulaHost.
tmp5 = make_repo(host=HOST_OK.replace("def show_mini", "def gone_mini"))
app_host = APP_OK.replace(
    "        if kind == 'goto':",
    "        if kind == 'overlay' and self._host:\n"
    "            host.show_mini()\n"
    "            return {'ok': True}\n"
    "        if kind == 'goto':")
with open(os.path.join(tmp5, "spike", "app.py"), "w",
          encoding="utf-8") as f:
    f.write(app_host)
with mock.patch.object(pcc, "ROOT", tmp5), \
     mock.patch.object(pcc, "APP_PATH",
                       os.path.join(tmp5, "spike", "app.py")), \
     mock.patch.object(pcc, "HOST_PATH",
                       os.path.join(tmp5, "spike", "host.py")):
    probs2, _ = pcc.run()
shutil.rmtree(tmp5)
check("host receiver checked against NebulaHost",
      any(p.startswith("TARGETS") and "show_mini" in p for p in probs2),
      probs2)

# 6. Integration: real repo contract holds right now.
real_probs, _ = pcc.run()
check("REAL REPO: palette contract holds", not real_probs, real_probs)

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
