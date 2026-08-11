"""sessionStart - open every session already knowing two things it cannot read.

1. Which checkout this is. nebula-identity.mdc spends 1.4KB of every turn asking
   the agent to run tools/nebula_identity.py; running it here makes the
   exe-vs-source mix-up structurally impossible instead of merely discouraged.
2. Whether the gate is currently green.

Deliberately says nothing about how the hooks work - that is static, lives in
AGENTS.md, and Cursor loads it for free. Only facts that change go here.

Self-test: python session-brief.py --selftest
"""

from __future__ import annotations

import os
import sys

from _common import disabled, emit, project_dir, python_exe, run


def identity(root: str) -> str:
    script = os.path.join(root, "tools", "nebula_identity.py")
    if not os.path.isfile(script):
        return ""
    code, out = run([python_exe(), script], cwd=root, timeout=20)
    if code != 0 or not out:
        return ""
    # The tool prints the banner, then a "fields:" dump. The banner is the part
    # worth spending context on.
    return out.split("fields:", 1)[0].strip()


def gate_line(root: str) -> str:
    """One line on where the Definition-of-done gate stands right now."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import gate  # noqa: PLC0415 - deferred so a gate bug cannot break the brief

        failures = gate.run_gate(root)
    except Exception as exc:  # noqa: BLE001
        return f"Gate status: could not be determined ({type(exc).__name__})."
    if not failures:
        return "Gate status: clean (ruff + token lint) as of session start."
    names = ", ".join(name for name, _ in failures)
    return (
        f"Gate status: FAILING at session start - {names}. "
        "These predate your turn; fix them only if they are in scope, and say so either way."
    )


def context(root: str) -> str:
    parts = []
    banner = identity(root)
    if banner:
        parts.append(
            "Nebula checkout identity for this session "
            f"(tools/nebula_identity.py):\n\n{banner}\n\n"
            "Judge UI only against this checkout. Never treat the frozen exe's "
            "directory as source truth."
        )
    parts.append(gate_line(root))
    return "\n\n".join(parts)


def main() -> int:
    root = project_dir()

    if "--selftest" in sys.argv:
        text = context(root)
        if not text.strip():
            print("FAIL: produced no context")
            return 1
        print(text)
        print("\nok")
        return 0

    if disabled():
        return emit()

    text = context(root)
    return emit({"additional_context": text} if text.strip() else None)


if __name__ == "__main__":
    raise SystemExit(main())
