"""Audit what a delegated agent actually ran, against the same guards.

Hooks only cover the GUI. `cursor-agent -p` - the transport tools/delegate.py
uses - runs no project hooks at all, verified 2026-08-11: two real CLI sessions
produced no hooks-log entries, no .gate-state.json update and no ledger row.
And delegate.py passes --trust --force, so nothing prompts either.

That leaves the acceptance boundary as the place to enforce, which is where
delegate.py already gates. Cursor records every shell command in the session
transcript, so this replays them through the *same* classifiers the live hooks
use - no second copy of the rules.

Detection, not prevention: a denied command has already run by the time this
sees it. It fails the gate so the work is not archived, and it tells you what
happened, which is strictly better than the silence that was there before.

    python tools/audit_commands.py --task t013
    python tools/audit_commands.py --chat <chat_id>
    python tools/audit_commands.py --all
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, ".cursor", "hooks")
SESSIONS = os.path.join(ROOT, ".cursor", "handoff", "sessions.json")
TRANSCRIPTS = os.path.join(
    os.path.expanduser("~"), ".cursor", "projects", "*", "agent-transcripts"
)


def load_guard(name: str):
    """Import a hook module for its classify() - the live rules, not a copy."""
    path = os.path.join(HOOKS, f"{name}.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(f"_guard_{name.replace('-', '_')}", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, HOOKS)  # the guards import _common
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(HOOKS)
    return module


def transcript_for(chat_id: str) -> str | None:
    for base in glob.glob(TRANSCRIPTS):
        path = os.path.join(base, chat_id, f"{chat_id}.jsonl")
        if os.path.isfile(path):
            return path
    return None


def commands_in(path: str) -> list[str]:
    """Every shell command in the transcript, in order.

    Walks the parsed JSON rather than regexing the raw text - tool calls nest,
    and a "command" key can appear at any depth.
    """
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            value = node.get("command")
            if isinstance(value, str) and value.strip():
                found.append(value)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                walk(json.loads(line))
            except ValueError:
                continue
    return found


def audit(chat_id: str, label: str, verbose: bool = True) -> tuple[int, int, int]:
    """Returns (destructive, launches, total).

    The two guards are NOT equally severe here, and the history proves why:
    across 14 delegated sessions every single app-launch hit was a launch the
    brief itself ordered - t013 literally says `python spike/app.py --show
    --url=customise=1`, then "kill every process you started, immediately".
    Failing the gate on those would break the screenshot workflow rather than
    protect anything.

    So only the destructive guard is fatal. Those - rm -rf, force push,
    curl|bash - are never something a brief asks for.
    """
    path = transcript_for(chat_id)
    if not path:
        if verbose:
            print(f"  {label}: no transcript found for {chat_id}")
        return 0, 0, 0

    destructive = load_guard("guard-destructive")
    launch = load_guard("guard-app-launch")
    commands = commands_in(path)

    fatal = launches = 0
    for command in commands:
        flat = " ".join(command.split())[:100]
        if destructive:
            got = destructive.classify(command)
            if got:
                decision, reason = got
                if decision == "deny":
                    fatal += 1
                    print(f"  {label}  DESTRUCTIVE  {reason}\n           {flat}")
                elif verbose:
                    print(f"  {label}  confirm      {reason}\n           {flat}")
        if launch and launch.classify(command):
            launches += 1
            if verbose:
                print(f"  {label}  launch       {launch.classify(command)}\n           {flat}")
    return fatal, launches, len(commands)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", help="task id from sessions.json, e.g. t013")
    group.add_argument("--chat", help="chat/conversation id")
    group.add_argument("--all", action="store_true", help="every task in sessions.json")
    parser.add_argument("--quiet", action="store_true",
                        help="only report destructive hits (what delegate.py gates on)")
    args = parser.parse_args(argv)

    sessions: dict[str, str] = {}
    if os.path.isfile(SESSIONS):
        with open(SESSIONS, encoding="utf-8") as handle:
            sessions = json.load(handle)

    if args.chat:
        targets = [(args.chat[:8], args.chat)]
    elif args.task:
        if args.task not in sessions:
            print(f"unknown task {args.task!r}; known: {', '.join(sorted(sessions))}")
            return 2
        targets = [(args.task, sessions[args.task])]
    else:
        targets = sorted(sessions.items())

    fatal = launches = total = 0
    for label, chat_id in targets:
        f, la, t = audit(chat_id, label, verbose=not args.quiet)
        fatal, launches, total = fatal + f, launches + la, total + t

    print(f"\n{total} command(s) audited across {len(targets)} session(s): "
          f"{fatal} destructive, {launches} app launch(es)")
    if fatal:
        print("DESTRUCTIVE commands ran in a lane with no guard. Do not archive "
              "the task until each one is explained.")
    elif launches:
        print("App launches are expected when a brief asks for screenshots - "
              "reported, not fatal. Check each was the brief's idea, and that "
              "the agent killed what it started.")
    return 1 if fatal else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
