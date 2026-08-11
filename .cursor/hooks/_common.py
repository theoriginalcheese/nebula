"""Shared plumbing for Nebula's Cursor hooks.

Hooks are spawned processes: JSON in on stdin, JSON out on stdout.
Everything here fails open - a broken hook must never wedge the agent.
A kill switch lives at .cursor/hooks/DISABLED; create it to no-op the lot.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))


def project_dir() -> str:
    """Repo root. Cursor sets CURSOR_PROJECT_DIR; fall back to walking up."""
    env = os.environ.get("CURSOR_PROJECT_DIR") or os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        return env
    return os.path.dirname(os.path.dirname(HOOK_DIR))


def disabled() -> bool:
    return os.path.exists(os.path.join(HOOK_DIR, "DISABLED"))


def read_input() -> dict:
    """Parse the hook payload. Malformed input yields {} rather than a crash."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def emit(payload: dict | None = None, code: int = 0) -> int:
    if payload:
        json.dump(payload, sys.stdout)
        sys.stdout.write("\n")
    sys.stdout.flush()
    return code


def run(args: list[str], cwd: str, timeout: int = 60) -> tuple[int, str]:
    """Run a check. Returns (returncode, combined output).

    A missing interpreter or a timeout reports as a soft skip (rc 0) so the
    gate never invents a failure it cannot substantiate.
    """
    # Pin the child's IO to UTF-8; the Windows console default (cp1252) mangles
    # the em-dashes these tools print.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return 0, ""
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def python_exe() -> str:
    return sys.executable or "python"
