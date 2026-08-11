"""What a fresh Cursor session actually costs, in characters and tokens.

"Does this kill my tokens?" should be a command, not a guess. Reports the fixed
per-turn overhead, separates it from what loads on demand, and shows the deferred
content you are NOT paying for.

Token figures are chars/4 - the same rough estimator the handoff ledger uses.
Good to ~10%; not a substitute for a real tokeniser.

    python tools/context_budget.py
    python tools/context_budget.py --verbose   # per-skill and per-rule detail
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME_SKILLS = os.path.join(os.path.expanduser("~"), ".cursor", "skills")
MCP_CONFIGS = [
    os.path.join(os.path.expanduser("~"), ".cursor", "mcp.json"),
    os.path.join(ROOT, ".cursor", "mcp.json"),
]


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def frontmatter(text: str) -> str:
    """The name+description block - the only part of a skill that is indexed."""
    if not text.startswith("---"):
        return text[:400]
    parts = text.split("---", 2)
    return parts[1] if len(parts) > 2 else text[:400]


def rules() -> tuple[list, list]:
    always, on_demand = [], []
    for path in sorted(glob.glob(os.path.join(ROOT, ".cursor", "rules", "*.mdc"))):
        text = read(path)
        head = text.split("---", 2)[1] if text.startswith("---") else ""
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        entry = (rel, len(text))
        if re.search(r"alwaysApply:\s*true", head):
            always.append(entry)
        else:
            trigger = "glob" if re.search(r"^globs:", head, re.M) else "agent-requested"
            on_demand.append((rel, len(text), trigger))
    return always, on_demand


def skills() -> list:
    out = []
    for base, label in ((HOME_SKILLS, "user"), (os.path.join(ROOT, ".cursor", "skills"), "project")):
        for path in sorted(glob.glob(os.path.join(base, "*", "SKILL.md"))):
            text = read(path)
            out.append((os.path.basename(os.path.dirname(path)), label,
                        len(frontmatter(text)), len(text)))
    return out


def agents() -> list:
    """Subagent routing index: name + description, per agent.

    The model needs these to decide what to delegate to, so they are fixed cost
    like the skill index - and they are the reason bulk-installing a 100-agent
    collection is not free.
    """
    out = []
    for base, label in (
        (os.path.join(os.path.expanduser("~"), ".cursor", "agents"), "user"),
        (os.path.join(ROOT, ".cursor", "agents"), "project"),
    ):
        for path in sorted(glob.glob(os.path.join(base, "*.md"))):
            text = read(path)
            head = text.split("---", 2)[1] if text.startswith("---") else text[:300]
            match = re.search(r"description:\s*(.+?)(?=\n\w+:|\Z)", head, re.S)
            name = os.path.basename(path)[:-3]
            out.append((name, label, len(name) + len(match.group(1).strip() if match else "")))
    return out


def mcp_servers() -> list:
    out = []
    for path in MCP_CONFIGS:
        if not os.path.isfile(path):
            continue
        try:
            data = json.loads(read(path))
        except ValueError:
            continue
        for name in (data.get("mcpServers") or {}):
            out.append((name, os.path.relpath(path, os.path.expanduser("~"))))
    return out


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    always, on_demand = rules()
    sk = skills()

    ag = agents()
    agents_md = len(read(os.path.join(ROOT, "AGENTS.md")))
    rules_always = sum(n for _, n in always)
    skill_index = sum(n for _, _, n, _ in sk)
    skill_bodies = sum(b for _, _, _, b in sk)
    on_demand_total = sum(n for _, n, _ in on_demand)
    agent_index = sum(n for _, _, n in ag)

    fixed = agents_md + rules_always + skill_index + agent_index
    print("FIXED - in context every turn")
    print(f"  {agents_md:6d} ch  ~{agents_md // 4:5d} tok  AGENTS.md")
    for rel, n in always:
        print(f"  {n:6d} ch  ~{n // 4:5d} tok  {rel}")
    print(f"  {skill_index:6d} ch  ~{skill_index // 4:5d} tok  skill index ({len(sk)} skills)")
    if verbose:
        for name, label, idx, body in sk:
            print(f"           {idx:5d} ch  {name} ({label}, body {body} ch deferred)")
    print(f"  {agent_index:6d} ch  ~{agent_index // 4:5d} tok  agent index ({len(ag)} subagents)")
    if verbose:
        for name, label, idx in ag:
            print(f"           {idx:5d} ch  {name} ({label})")
    if ag:
        each = agent_index // len(ag)
        print(f"           ~{each} ch each - bulk-installing 100 agents would add "
              f"~{each * 100 // 4} tok/turn")
    print(f"  {'-' * 6}")
    print(f"  {fixed:6d} ch  ~{fixed // 4:5d} tok   before MCP")

    servers = mcp_servers()
    print(f"\nMCP - {len(servers)} server(s), tool schemas load every turn")
    for name, where in servers:
        print(f"          {name}  (from ~/{where})")
    print("  ask-question: 2265 ch (~566 tok) on the wire after schema trimming;")
    print("  was 2951 ch (~737 tok) before pydantic titles and envelope outputSchemas")
    print("  were stripped. Re-measure with that server's own tools/list.")

    print("\nDEFERRED - costs nothing until pulled in")
    for rel, n, trigger in on_demand:
        print(f"  {n:6d} ch  ~{n // 4:5d} tok  {rel}  [{trigger}]")
    print(f"  {skill_bodies:6d} ch  ~{skill_bodies // 4:5d} tok  skill bodies ({len(sk)} files)")
    deferred = on_demand_total + skill_bodies
    print(f"  {'-' * 6}")
    print(f"  {deferred:6d} ch  ~{deferred // 4:5d} tok  available, unloaded")

    ratio = deferred / fixed if fixed else 0
    print(f"\n  fixed ~{fixed // 4} tok  |  deferred ~{deferred // 4} tok  ({ratio:.1f}x)")
    print("  Every deferred item is named in AGENTS.md, so it can be asked for by name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
