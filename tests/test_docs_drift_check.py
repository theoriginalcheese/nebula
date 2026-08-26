"""Docs drift check: README config table vs config.DEFAULTS fixtures + real.

    python tests/test_docs_drift_check.py

The README's settings table is curated, not exhaustive - so the only honest
automated check is one-directional: a key documented in the table must
exist in DEFAULTS (no ghosts). Fixture cases cover ghost detection,
slash-combined rows, and non-key backticks being ignored; the final check
runs against the real repo and must be clean.
"""
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import docs_drift_check as ddc

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


CONFIG_OK = ("DEFAULTS = {\n"
             "    'obs_host': 'localhost',\n"
             "    'obs_port': 4455,\n"
             "    'nas_offload_mode': 'copy',\n"
             "}\n")

README_OK = (
    "| Key | Default | What it does |\n"
    "|-----|---------|--------------|\n"
    "| `obs_host` / `obs_port` | `localhost` / `4455` | conn |\n"
    "| `nas_offload_mode` | `copy` | mode |\n"
    "\n"
    "Some prose with `random_inline` code.\n")


def make_repo(readme=README_OK, config=CONFIG_OK):
    tmp = tempfile.mkdtemp(prefix="ddc-fixture-")
    obs = os.path.join(tmp, "obsauto")
    os.makedirs(obs)
    open(os.path.join(tmp, "README.md"), "w", encoding="utf-8").write(readme)
    open(os.path.join(obs, "config.py"), "w", encoding="utf-8").write(config)
    return tmp


def run_in(tmp):
    with mock.patch.object(ddc, "ROOT", tmp), \
         mock.patch.object(ddc, "README",
                           os.path.join(tmp, "README.md")), \
         mock.patch.object(ddc, "CONFIG_PY",
                           os.path.join(tmp, "obsauto", "config.py")):
        return ddc.run()


# 1. Clean fixture: combined slash rows split, prose ignored.
tmp = make_repo()
probs = run_in(tmp)
check("clean fixture passes", probs == [], probs)
shutil.rmtree(tmp)

# 2. A documented key missing from DEFAULTS is a GHOST.
tmp = make_repo(readme=README_OK.replace(
    "`nas_offload_mode`", "`nas_offload_mood`"))
probs = run_in(tmp)
shutil.rmtree(tmp)
check("ghost key detected",
      any("nas_offload_mood" in p for p in probs), probs)

# 3. Curated table: DEFAULTS keys absent from README stay fine.
tmp = make_repo(readme=README_OK.split("|-----|---------|")[0] +
                "|-----|---------|--------------|\n"
                "| `obs_host` | `localhost` | conn |\n")
probs = run_in(tmp)
shutil.rmtree(tmp)
check("curation respected (no reverse check)", probs == [], probs)

# 4. Missing DEFAULTS dict is a hard error, not silence.
tmp = make_repo(config="X = 1\n")
try:
    probs = run_in(tmp)
    got = [p for p in probs if "DEFAULTS" in p]
except RuntimeError as exc:
    got = ["raised: %s" % exc]
finally:
    shutil.rmtree(tmp)
check("missing DEFAULTS surfaced", bool(got), got)

# 5. Integration: real repo has no ghost keys right now.
with mock.patch.object(ddc, "ROOT", os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))):
    real = ddc.run()
check("REAL REPO: README config table matches DEFAULTS", not real, real)

failed = 0
for name, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail and not passed else ""))
    if not passed:
        failed += 1
print(f"\n{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
