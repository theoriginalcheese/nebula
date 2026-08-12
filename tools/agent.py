"""One entry point for the agent tooling. `python tools/agent.py` lists it all.

There are six tools and six hook scripts. They each do one thing well, and
nothing here replaces them - the hooks still call their scripts directly, so the
hot path is untouched. This exists so you have one thing to remember instead of
twelve paths.

Every subcommand is imported *lazily*, at the moment it runs. `agent.py gate`
never pays for PIL, and the gate stays as fast as calling it directly.

    python tools/agent.py                 # what's available
    python tools/agent.py gate            # the fast gate (~0.2s)
    python tools/agent.py budget -v       # what loads every turn
    python tools/agent.py check           # gate + skills + ledger, one pass
"""

from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# name -> (path relative to repo root, one-line help)
COMMANDS = {
    "gate":   (".cursor/hooks/gate.py",      "ruff + token lint + skill sync (~0.2s)"),
    "budget": ("tools/context_budget.py",    "what costs context every turn"),
    "audit":  ("tools/audit_commands.py",    "what delegated agents actually ran"),
    "sync":   ("tools/sync_skills.py",       ".claude/skills -> .cursor/skills"),
    "ledger": ("tools/backfill_ledger.py",   "recover delegation history"),
    "glyph":  ("tools/verify_glyph.py",      "verify an icon codepoint by rendering it"),
    "design": ("tools/design_sync.py",       "mirror a Claude Design project into the repo"),
    "gate!":  ("tools/delegate.py",          "full gate incl. test suites (~4.4s)"),
}

# Subcommands whose default argv differs from "no arguments".
DEFAULT_ARGS = {
    "gate": ["--selftest"],
    "gate!": ["verify"],
    "audit": ["--all", "--quiet"],
    "design": ["status"],
}


def run(name: str, argv: list[str]) -> int:
    rel, _help = COMMANDS[name]
    path = os.path.join(ROOT, rel)
    if not os.path.isfile(path):
        print(f"missing: {rel}")
        return 1
    spec = importlib.util.spec_from_file_location(f"_agent_{name.strip('!')}", path)
    if spec is None or spec.loader is None:
        print(f"could not load {rel}")
        return 1
    module = importlib.util.module_from_spec(spec)
    # The tools resolve siblings off their own __file__, and some import helpers
    # from their own directory (the hooks import _common).
    sys.path.insert(0, os.path.dirname(path))
    saved, sys.argv = sys.argv, [path, *(argv or DEFAULT_ARGS.get(name, []))]
    try:
        spec.loader.exec_module(module)
        main = getattr(module, "main", None)
        if main is None:
            return 0
        try:
            return int(main(sys.argv[1:]) or 0)
        except TypeError:
            return int(main() or 0)
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        sys.argv = saved
        sys.path.pop(0)


def check() -> int:
    """The three things worth knowing before you call something done."""
    worst = 0
    for name in ("gate", "sync"):
        print(f"--- {name}")
        worst = max(worst, run(name, DEFAULT_ARGS.get(name, [])))
    return worst


def usage() -> int:
    print(__doc__.strip().split("\n\n")[0])
    print()
    width = max(len(n) for n in COMMANDS) + 2
    for name, (rel, help_) in COMMANDS.items():
        print(f"  {name:<{width}} {help_}")
        print(f"  {'':<{width}} {rel}")
    print(f"\n  {'check':<{width}} gate + skill sync in one pass")
    print("\nArguments pass straight through:  agent.py audit --task t013")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        return usage()
    name, rest = argv[0], argv[1:]
    if name == "check":
        return check()
    if name not in COMMANDS:
        print(f"unknown command {name!r}\n")
        return usage()
    return run(name, rest)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
