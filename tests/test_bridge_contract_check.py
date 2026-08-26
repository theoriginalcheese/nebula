"""JS-bridge contract checker: fixtures per failure class + real repo.

    python tests/test_bridge_contract_check.py

The v4 UI's Python<->JS boundary is invisible to every linter: a renamed Api
method leaves window.pywebview.api.X() calls in spike/web pointing at
nothing, surfacing at runtime only. Fixture cases pin each verdict class
(MISSING, UNCALLED-as-info, DYNAMIC dispatch refusal, parse errors); the
final check runs against the real repo and must be clean.
"""
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import bridge_contract_check as bcc

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


PY_OK = ("class Api:\n"
         "    def snapshot(self):\n"
         "        return {}\n"
         "\n"
         "    def open_clip(self, rel):\n"
         "        return {'ok': True}\n"
         "\n"
         "class ToastApi:\n"
         "    def ready(self):\n"
         "        return True\n")

JS_MAIN = ("const d = await window.pywebview.api.snapshot();\n"
           "await window.pywebview.api.open_clip(rel);\n")
JS_TOAST = ("await window.pywebview.api.ready();\n")


def make_repo(py=PY_OK, js_files=None):
    tmp = tempfile.mkdtemp(prefix="bcc-fixture-")
    spike = os.path.join(tmp, "spike")
    web = os.path.join(spike, "web")
    os.makedirs(web)
    with open(os.path.join(spike, "app.py"), "w", encoding="utf-8") as f:
        f.write(py)
    for name, text in (js_files or {"app.js": JS_MAIN,
                                    "toast.js": JS_TOAST}).items():
        with open(os.path.join(web, name), "w", encoding="utf-8") as f:
            f.write(text)
    return tmp


def run_in(tmp):
    with mock.patch.object(bcc, "ROOT", tmp), \
         mock.patch.object(bcc, "SPIKE", os.path.join(tmp, "spike")), \
         mock.patch.object(bcc, "WEB", os.path.join(tmp, "spike", "web")):
        return bcc.run()


# 1. Clean fixture -> no problems, uncalled reported as info only.
tmp = make_repo()
probs, info = run_in(tmp)
check("clean fixture passes", probs == [], probs)

# 2. A JS call with no backing Api method is MISSING.
tmp = make_repo(js_files={"app.js": JS_MAIN +
                          "window.pywebview.api.ghost(1);\n",
                          "toast.js": JS_TOAST})
probs, _ = run_in(tmp)
import shutil
shutil.rmtree(tmp)
check("missing method detected",
      any(p.startswith("MISSING:") and "ghost" in p for p in probs), probs)

# 3. An exposed-but-uncalled method is info, not a failure.
tmp = make_repo(py=PY_OK.replace(
    "class ToastApi:",
    "    def lonely(self):\n"
    "        return 1\n\n"
    "class ToastApi:"))
probs, info = run_in(tmp)
shutil.rmtree(tmp)
check("clean still passes with an uncalled method", probs == [], probs)
check("uncalled surfaces as info", any(i.startswith("UNCALLED: lonely")
                                       for i in info), info)

# 4. Bracket-indexed dynamic dispatch is refused loudly.
tmp = make_repo(js_files={"app.js": "window.pywebview.api[name]();\n",
                          "toast.js": ""})
probs, _ = run_in(tmp)
shutil.rmtree(tmp)
check("dynamic dispatch refused",
      any(p.startswith("DYNAMIC:") for p in probs), probs)

# 5. Unparsable Python surface is a hard failure, not silence.
tmp = make_repo(py="class Api:\n    def broken(:\n")
probs, _ = run_in(tmp)
shutil.rmtree(tmp)
check("parse error surfaced",
      any(p.startswith("PARSE_ERROR:") for p in probs), probs)

# 6. Integration: the real repo's bridge must hold right now.
real_probs, _ = bcc.run()
check("REAL REPO: JS bridge contract holds", not real_probs, real_probs)

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
