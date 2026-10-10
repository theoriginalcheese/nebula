"""The admin switch is opt-in. No window, no UAC prompt.

    python tests/test_admin_launch.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.admin_launch import should_elevate
from obsauto.config import DEFAULTS
from obsauto.settings_spec import BY_KEY

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %s %s" % ("PASS" if ok else "FAIL", name, detail))


def test_should_elevate():
    check("off stays a normal process",
          should_elevate(False, False, ["main.py"]) is False)
    check("already admin does not prompt again",
          should_elevate(True, True, ["main.py"]) is False)
    check("the switch on, and not admin, hands off",
          should_elevate(True, False, ["main.py"]) is True)
    check("dev skip",
          should_elevate(True, False, ["main.py", "--dev"]) is False)
    check("allow-multi skip",
          should_elevate(True, False, ["spike/app.py", "--allow-multi"]) is False)
    check("toast demo skip",
          should_elevate(True, False, ["main.py", "--toast-demo"]) is False)
    check("apply-update skip",
          should_elevate(True, False, ["main.py", "--apply-update"]) is False)
    check("show still elevates when the switch is on",
          should_elevate(True, False, ["spike/app.py", "--show"]) is True)


def test_setting_is_declared():
    check("default is off", DEFAULTS.get("run_as_administrator") is False)
    field = BY_KEY.get("run_as_administrator")
    check("settings has the switch", field is not None and field.kind == "bool")
    check("it lives with the hotkey", field is not None and field.group == "hotkey")


if __name__ == "__main__":
    test_should_elevate()
    test_setting_is_declared()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        sys.exit(1)
