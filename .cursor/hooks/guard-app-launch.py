"""beforeShellExecution - refuse to launch Nebula or OBS.

Launching Nebula starts a real OBS recording, and killing it orphans one.
Four separate agent files repeat this as prose; this makes it structural.

Escape hatch: set NEBULA_ALLOW_LAUNCH=1 when Anthony has actually asked.
Self-test: python guard-app-launch.py --selftest
"""

from __future__ import annotations

import os
import re
import sys

from _common import disabled, emit, read_input

ALLOW_VAR = "NEBULA_ALLOW_LAUNCH"

# Launching the app proper. Demo/audit tools are deliberately NOT here - the
# UI rules explicitly permit demo_toast.py and friends against a live process.
BLOCKED = [
    (re.compile(r"\bpythonw?(?:\.exe)?\b[^|;&]*\bmain\.py\b", re.I), "Nebula (main.py)"),
    (re.compile(r"\bpythonw?(?:\.exe)?\b[^|;&]*\bspike[/\\]app\.py\b", re.I), "Nebula spike app"),
    (re.compile(r"\bstart\b[^|;&]*\bnebula\b", re.I), "Nebula (start)"),
    (re.compile(r"Nebula[^|;&]*\.exe", re.I), "frozen Nebula.exe"),
    (re.compile(r"\bobs(?:64)?\.exe\b", re.I), "OBS Studio"),
    (re.compile(r"\bStartRecord\b|\bStartRecording\b", re.I), "an OBS recording"),
]

ADVICE = (
    "Blocked by .cursor/hooks/guard-app-launch.py: this would launch {what}, "
    "which starts a real OBS recording (and killing it orphans one).\n"
    "Ask Anthony first. If he has already agreed, re-run with "
    "NEBULA_ALLOW_LAUNCH=1 set, or judge the process that is already running "
    "instead of starting another."
)


def allowed(command: str) -> bool:
    """Has Anthony opted in? Honour both the ambient env and an inline prefix.

    The hook runs as its own process, so `NEBULA_ALLOW_LAUNCH=1 python main.py`
    never reaches our environ - it has to be read off the command string too.
    """
    if os.environ.get(ALLOW_VAR, "").strip() not in ("", "0", "false", "False"):
        return True
    inline = re.search(rf"\b{ALLOW_VAR}\s*=\s*(\S+)", command)
    return bool(inline) and inline.group(1).strip("\"'") not in ("0", "false", "False")


def classify(command: str) -> str | None:
    """Return a human label for what the command would launch, else None."""
    if allowed(command):
        return None
    for pattern, label in BLOCKED:
        if pattern.search(command):
            return label
    return None


def selftest() -> int:
    cases = [
        ("python main.py", "Nebula (main.py)"),
        ("pythonw.exe spike/app.py --dev --show", "Nebula spike app"),
        ('"C:\\Users\\antho\\Nebula\\Nebula (1).exe"', "frozen Nebula.exe"),
        ("obs64.exe --startrecording", "OBS Studio"),
        # Must stay allowed - these are the sanctioned audit paths.
        ("python tools/nebula_identity.py", None),
        ("python tools/demo_toast.py", None),
        ("python -m ruff check .", None),
        ("python tools/lint_tokens.py", None),
        ("git status", None),
        ("grep -rn 'main.py' docs/", None),
        # Explicit opt-in wins.
        ("NEBULA_ALLOW_LAUNCH=1 python main.py", None),
        ("NEBULA_ALLOW_LAUNCH=0 python main.py", "Nebula (main.py)"),
    ]
    failures = 0
    for command, expected in cases:
        actual = classify(command)
        ok = (actual is not None) == (expected is not None)
        if expected is not None:
            ok = ok and actual == expected
        if not ok:
            failures += 1
        print(f"  [{'ok ' if ok else 'FAIL'}] {command!r} -> {actual!r} (want {expected!r})")
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    if disabled():
        return emit()

    data = read_input()
    command = str(data.get("command") or "")
    if not command:
        return emit()

    what = classify(command)
    if what is None:
        return emit()

    return emit(
        {
            "permission": "deny",
            "agent_message": ADVICE.format(what=what),
            "user_message": f"Blocked a command that would launch {what}.",
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
