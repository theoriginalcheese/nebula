"""stop / subagentStop - run the cheap half of the Definition of done.

nebula-gate exists because agents claim "done" without evidence. As a rule it
only works when the model remembers to invoke it; as a stop hook it runs by
construction.

Deliberately does NOT shell out to tools/lint_tokens.py. That script's
check_tokens_in_sync() regenerates spike/web/tokens.css in place - a 35s
subprocess with a write side effect, which is not something a stop hook may do
to a live working tree. The read-only checks in that module are imported and
run directly instead, which is both safe and ~35x faster.

Set NEBULA_GATE_FULL=1 to include the token-sync check (slow, writes tokens.css).
Set NEBULA_GATE_TESTS=1 to add the frame-pacing test.
Self-test: python gate.py --selftest
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

from _common import disabled, emit, project_dir, python_exe, read_input, run

# A stop hook that fires on an interrupted turn is just noise.
SKIP_STATUS = {"aborted", "error"}

# gate.py writes its verdict here so record-usage.py can report it at sessionEnd
# without paying for a second run.
STATE = os.path.join(".cursor", "handoff", ".gate-state.json")

FOLLOWUP = (
    "Definition-of-done gate failed before this turn could be called finished.\n\n"
    "{report}\n"
    "Fix what your changes caused, then stop again to re-run the gate. "
    "If a failure is pre-existing and unrelated to this task, say so explicitly "
    "and stop - do not fix it silently, and do not claim the gate passed."
)


def _load_lint_module(root: str):
    """Import tools/lint_tokens.py without running its main()."""
    path = os.path.join(root, "tools", "lint_tokens.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("_nebula_lint_tokens", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def token_lint(root: str) -> tuple[str, str]:
    """Run lint_tokens' read-only checks. Returns (status, report).

    status is "pass", "fail", or "skip". Mirrors its main() minus
    check_tokens_in_sync. This is coupled to that module's internals on purpose,
    so a refactor there surfaces as "skip" - which the gate reports as a failure,
    because a check that could not run is unverified, not passed.
    """
    try:
        mod = _load_lint_module(root)
        if mod is None:
            return "skip", "tools/lint_tokens.py not found"
        web = mod.WEB
        if not os.path.isdir(web):
            return "skip", f"{web} not found"

        mod.problems.clear()
        names = sorted(os.listdir(web))
        for name in (n for n in names if n.endswith(".js")):
            mod.check_script(os.path.join(web, name))
        sheets = [
            os.path.join(web, n)
            for n in names
            if n.endswith(".css") and n != "tokens.css"
        ]
        for path in sheets:
            mod.check_stylesheet(path)
            mod.check_reduced_motion(path)
        mod.check_hidden_attribute(sheets)

        if os.environ.get("NEBULA_GATE_FULL", "").strip() not in ("", "0", "false"):
            mod.check_tokens_in_sync()

        problems = list(mod.problems)
    except Exception as exc:  # noqa: BLE001 - report, never crash the hook
        return "skip", f"{type(exc).__name__}: {exc}"

    if not problems:
        return "pass", ""
    lines = [f"token lint: {len(problems)} problem{'' if len(problems) == 1 else 's'}"]
    for rel, lineno, rule, text, detail in problems[:12]:
        lines.append(f"  {rel}:{lineno}  {rule} - {detail or text}")
    if len(problems) > 12:
        lines.append(f"  ... and {len(problems) - 12} more")
    return "fail", "\n".join(lines)


def skills_drift(root: str) -> str:
    """.claude/skills and .cursor/skills must stay byte-identical.

    Two editable copies of the design contract is the exact drift this repo
    warns about. Cheap: two small files hashed.
    """
    try:
        spec = importlib.util.spec_from_file_location(
            "_nebula_sync_skills", os.path.join(root, "tools", "sync_skills.py")
        )
        if spec is None or spec.loader is None:
            return ""
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        missing, differing, extra = mod.drift()
    except Exception:  # noqa: BLE001 - never break the gate over a helper
        return ""
    if not (missing or differing or extra):
        return ""
    parts = [f"missing in .cursor/: {f}" for f in missing]
    parts += [f"differs: {f}" for f in differing]
    parts += [f"stale in .cursor/: {f}" for f in extra]
    return "\n  ".join(parts) + "\n  fix: python tools/sync_skills.py --apply"


def run_gate(root: str) -> list[tuple[str, str]]:
    """Return [(check name, output)] for the checks that failed."""
    failures = []

    code, out = run([python_exe(), "-m", "ruff", "check", "."], cwd=root, timeout=90)
    if code != 0:
        failures.append(("ruff", "\n".join(out.splitlines()[:20]) or "(no output)"))

    drifted = skills_drift(root)
    if drifted:
        failures.append(("skill sync", "  " + drifted))

    status, text = token_lint(root)
    if status == "fail":
        failures.append(("token lint", text))
    elif status == "skip":
        failures.append(
            ("token lint (UNVERIFIED)", f"{text}\nThe check could not run, so it is not passed.")
        )

    if os.environ.get("NEBULA_GATE_TESTS", "").strip() not in ("", "0", "false"):
        code, out = run([python_exe(), "tests/test_frame_pacing.py"], cwd=root, timeout=180)
        if code != 0:
            failures.append(("frame pacing", "\n".join(out.splitlines()[:20])))

    return failures


def write_state(root: str, failures: list[tuple[str, str]]) -> None:
    """Record the verdict for record-usage.py. Best effort; never raises."""
    try:
        path = os.path.join(root, STATE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "passed": not failures,
                    "failed_checks": [name for name, _ in failures],
                },
                handle,
            )
    except OSError:
        pass


def report(failures: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"FAIL {name}:\n{out}" for name, out in failures)


def main() -> int:
    if "--token-lint" in sys.argv:
        # Standalone mode so tools/delegate.py can run the *same* check rather
        # than shelling out to lint_tokens.py, which takes 35s and rewrites
        # spike/web/tokens.css. Two lanes, one implementation.
        status, text = token_lint(project_dir())
        if status == "pass":
            print("token lint: clean (read-only checks)")
            return 0
        print(text or "token lint: unverified")
        return 1

    if "--selftest" in sys.argv:
        root = project_dir()
        started = time.time()
        failures = run_gate(root)
        elapsed = time.time() - started
        print(f"root:    {root}")
        print(f"elapsed: {elapsed:.2f}s")
        if failures:
            print("\n" + report(failures))
            print(f"\nok (gate wired; {len(failures)} check(s) currently failing)")
        else:
            print("\nok (gate clean)")
        return 0

    if disabled():
        return emit()

    data = read_input()
    if str(data.get("status") or "").lower() in SKIP_STATUS:
        return emit()

    root = project_dir()
    failures = run_gate(root)
    write_state(root, failures)
    if not failures:
        return emit()

    return emit({"followup_message": FOLLOWUP.format(report=report(failures))})


if __name__ == "__main__":
    raise SystemExit(main())
