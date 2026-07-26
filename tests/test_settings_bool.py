"""Settings bool + path/secret field kinds parse cleanly (no GUI).

    python3 tests/test_settings_bool.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import settings_spec
from obsauto.config import DEFAULTS

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


check("launch_obs default True", DEFAULTS.get("launch_obs_with_nebula") is True)
check("start_minimised default True", DEFAULTS.get("start_minimised_to_tray") is True)

launch = settings_spec.BY_KEY["launch_obs_with_nebula"]
check("launch field is bool", launch.kind == "bool")
val, err = settings_spec.parse(launch, "1")
check("parse bool on", val is True and err is None, (val, err))
val, err = settings_spec.parse(launch, "0")
check("parse bool off", val is False and err is None, (val, err))
val, err = settings_spec.parse(launch, True)
check("parse native True", val is True and err is None)

check("render bool", settings_spec.render(launch, True) == "1")
check("render bool off", settings_spec.render(launch, False) == "0")

# Every DEFAULTS key still has a field (settings pane contract).
missing = sorted(k for k in DEFAULTS if k not in settings_spec.BY_KEY)
check("every DEFAULTS key has a Field", not missing, missing)

orphan = sorted(k for k in settings_spec.BY_KEY if k not in DEFAULTS)
check("every Field key is in DEFAULTS", not orphan, orphan)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<46} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
