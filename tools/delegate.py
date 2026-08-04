"""Hand a task to Cursor, then verify what comes back.

    python tools/delegate.py status
    python tools/delegate.py send  --title "Clips: by-game column" --spec spec.md
    python tools/delegate.py verify
    python tools/delegate.py collect

Why a bridge at all
-------------------
Cursor's built-in models (Composer) are far cheaper per token than a frontier
model, and the work they are good at here - building a pane against a fixed
design frame - is well specified and mechanically checkable. So the split that
makes sense is: **Cursor writes volume, this file guarantees quality.**

The guarantee is the point. Delegating to a cheaper model is only safe if the
acceptance criteria are machine-checked rather than eyeballed, so every task
that comes back runs the same gate before anyone looks at it:

    ruff check .                 defects, not style
    tools/lint_tokens.py         the design contract
    tests/test_v4_tray.py        step 1 still holds
    tests/test_design_v3.py      BUILD-SPEC vs design_v3.py
    tools/shoot.py               it still renders

A task is not "done" because an agent said so. It is done when the gate passes.

Two transports
--------------
`cli`   - `cursor-agent -p ...`, fully headless. Nothing to paste. Needs the
          Cursor CLI installed (see `status` for the command).
`queue` - writes the brief to `.cursor/handoff/inbox/`. Cursor's in-IDE agent
          picks it up via `.cursor/rules/handoff.mdc` and writes its report to
          `outbox/`. Works today, costs one sentence in the Cursor chat.

`send` picks `cli` when it is available and falls back to `queue`, so the same
command works either way.

Every brief is composed with the project contract already in it - authority
order, hard rules, traps, definition of done. A cheap model with the contract
in front of it beats an expensive one guessing.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

# Agent output contains em dashes, arrows and box glyphs. Windows' default
# console codec is cp1252, so printing it raised UnicodeEncodeError *after* the
# agent had finished and *before* the gate ran - a completed task reported as a
# failure by its own reporting tool.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDOFF = os.path.join(ROOT, ".cursor", "handoff")
INBOX = os.path.join(HANDOFF, "inbox")
OUTBOX = os.path.join(HANDOFF, "outbox")
DONE = os.path.join(HANDOFF, "done")
LEDGER = os.path.join(HANDOFF, "ledger.jsonl")

INSTALL_HINT = "irm 'https://cursor.com/install?win32=true' | iex"

# Injected into every brief. Cursor starts cold every time; this is the
# difference between a cheap model that knows the rules and one that guesses.
CONTRACT = """
## Project contract - read before writing any code

Repo root: {root}

Read these first, in order:
  1. .claude/skills/nebula-ui/SKILL.md      rules, traps, the screenshot loop
  2. .claude/skills/nebula-polish/SKILL.md  the aesthetic checklist
  3. design/ui-v3/BUILD-SPEC.md             THE AUTHORITY on every number
  4. V4-GUIDE.md                            what v4 is, and the build order

Authority order:
  BUILD-SPEC.md > design/ui-v3/frames/*.png > everything else.
  If a frame and the spec table disagree, the table wins.

Hard rules - these outrank the design:
  1. Animate ONLY `transform` and `opacity`. Never width/height/top/left/filter.
  2. NO FABRICATED NUMBERS. Every figure comes from a real source through
     window.pywebview.api. No source -> render the honest empty state. The
     mockup is full of filler (418 clips, 1.9 TB, a connected macropad with an
     HID id) - do not copy any of it.
  3. No hand-typed colours, radii, durations or easings. Everything comes from
     spike/web/tokens.css, GENERATED from obsauto/design_v3.py by
     `python spike/gen_tokens.py`. Need a new token? Add it to the Python and
     re-run. Never edit tokens.css by hand.
  4. Do not modify obsauto/, main.py or tests/. Need data that isn't exposed?
     Add a method to the Api class in spike/app.py that calls the existing
     modules.
  5. Every card is two layers: tinted shell wrapping a darker core, with
     inner radius = outer radius - padding. A flat card is a bug.
  6. No npm, no bundler, no framework, no dependency. Plain HTML/CSS/JS.

Traps that have already cost time:
  - `rgb(var(--x-rgb) / .8)` needs a SPACE-separated triplet. `rgb(24, 20, 40
    / .8)` is a parse error, dropped silently, and the surface does not paint.
  - pywebview injects its bridge asynchronously. Poll for window.pywebview.api;
    do not rely on the pywebviewready event alone.
  - There is no console. Surface JS errors in the HUD (see fail() in app.js).
  - Before trusting a screenshot: `python tools/shoot.py --list`. Two windows
    titled Nebula means you are looking at a stale process.
  - A kill filter matching 'app.py' also matches its own command line. Exclude
    os.getpid() or you kill your own shell.

Definition of done - all of these, every task:
  python -m ruff check .          (or `ruff check .`)
  python tools/lint_tokens.py
  python tests/test_v4_tray.py
  python tests/test_design_v3.py
  python tools/shoot.py --out shots/check.png     and LOOK at it

Deliberate deviations are fine and must be written down with the reason.
Never silently "fix" something the spec asked for by removing it.
"""

REPORT_TEMPLATE = """
## Report back

When finished, write `.cursor/handoff/outbox/{task_id}.md` containing:

  # {task_id}
  status: done | blocked | partial

  ## Changed
  (files touched, one line each)

  ## Deliberate deviations
  (what you did not do the way the design says, and why - or "none")

  ## Gate
  (paste the output of each command in Definition of done)

  ## Notes for review
  (anything the reviewer should look at first)
"""


def ensure_dirs():
    for d in (INBOX, OUTBOX, DONE):
        os.makedirs(d, exist_ok=True)


SESSIONS = os.path.join(HANDOFF, "sessions.json")


def cli_path():
    """The Cursor CLI, if it is installed.

    The Windows installer drops a .cmd shim in %LOCALAPPDATA%/cursor-agent and
    does not put it on PATH for an already-running shell, so look there too
    rather than reporting "not installed" at someone who just installed it.
    """
    for name in ("cursor-agent", "cursor-agent.cmd", "cursor-agent.exe"):
        found = shutil.which(name)
        if found:
            return found
    local_app = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local")
    for cand in (os.path.join(local_app, "cursor-agent", "cursor-agent.cmd"),
                 os.path.join(os.path.expanduser("~"), ".local", "bin", "cursor-agent")):
        if os.path.isfile(cand):
            return cand
    return None


def authed():
    """(ok, detail). Cursor's CLI needs a browser OAuth login once."""
    cli = cli_path()
    if not cli:
        return False, "cursor-agent not installed"
    try:
        p = subprocess.run([cli, "status"], capture_output=True, text=True, timeout=60)
        out = (p.stdout + p.stderr).strip()
        # `status` prints "Not logged in" and exits **0**, so the return code
        # says nothing. Only treat an explicitly positive answer as logged in;
        # anything unrecognised is "no", because a false yes sends a task off
        # to an agent that cannot run it.
        low = out.lower()
        if any(bad in low for bad in ("not logged in", "authentication required",
                                      "unauthenticated", "no account")):
            return False, "not logged in - run: cursor-agent login"
        if p.returncode == 0 and out:
            return True, out.splitlines()[0]
        return False, out or "could not determine auth state"
    except Exception as exc:
        return False, str(exc)


def _sessions():
    if os.path.isfile(SESSIONS):
        try:
            return json.load(open(SESSIONS, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_session(task, chat_id):
    ensure_dirs()
    data = _sessions()
    data[task] = chat_id
    with open(SESSIONS, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def talk(task, prompt, model=None, resume=True, timeout=3600, force=True):
    """One turn of a conversation with Cursor's agent.

    This is a *conversation*, not a file drop. The chat id is kept per task, so
    a follow-up - "the gate failed on X, fix it" - lands in the same session
    with all its context intact, rather than starting a cold agent that has to
    rediscover the repo. That is the whole reason to prefer the CLI over the
    inbox: continuity is what makes a cheap model competent.
    """
    cli = cli_path()
    if not cli:
        raise SystemExit("cursor-agent not installed")

    # ORDER MATTERS. The CLI's usage is `agent [options] [command] [prompt...]`
    # and `prompt` is **variadic**, so every argument after it is swallowed into
    # the prompt text rather than parsed as a flag. Putting the prompt first
    # silently discarded --model, --output-format, --trust and --force: the run
    # came back asking for workspace trust while "--trust" sat inside the
    # message. Options first, prompt last, always.
    cmd = [cli, "-p", "--output-format", "text"]
    if model:
        cmd += ["--model", model]

    # `--trust` and `--force` are separate gates and both are needed for an
    # unattended run:
    #
    #   --trust  this workspace is safe to operate in at all. Asked once per
    #            directory; without it the agent stops before doing anything.
    #   --force  run shell commands without asking. Required because the whole
    #            point is that the agent runs its own Definition of done -
    #            ruff, the token lint, the tests - and there is nobody sitting
    #            there to approve each one.
    #
    # Together that is full autonomy inside this repo. That is a real decision,
    # not a detail: pass force=False to make it ask instead, at the cost of the
    # run stalling on the first command.
    if force:
        cmd += ["--trust", "--force"]

    # Mint the chat id up front rather than scraping it out of the reply.
    #
    # The first version parsed the id from stdout. In `--output-format text`
    # the CLI does not print one at all, so nothing was ever captured and every
    # follow-up silently opened a *cold* session - which is precisely the thing
    # this bridge exists to avoid, failing quietly. `create-chat` returns a bare
    # UUID, so the id is known before the first word is sent and continuity is
    # deterministic instead of best-effort.
    chat = _sessions().get(task) if resume else None
    if not chat:
        made = subprocess.run([cli, "create-chat"], cwd=ROOT,
                              capture_output=True, text=True, timeout=120)
        chat = (made.stdout or "").strip().splitlines()[-1].strip() if made.stdout else ""
        if not chat:
            raise SystemExit("could not create a chat session: %s"
                             % (made.stderr or "").strip())
        _save_session(task, chat)
        fresh = True
    else:
        fresh = False
    cmd += ["--resume", chat]

    cmd.append(prompt)          # variadic positional - must be last

    print("cursor-agent %s %s%s" % ("new chat" if fresh else "resuming", chat,
                                    " --model " + model if model else ""))

    # Stream to a log rather than capturing into a pipe, and hard-close stdin.
    #
    # The first long run hung for 56 minutes with no children, no output and no
    # files written. A short prompt through the identical call returns in ten
    # seconds, so the pipe is not the problem - the agent was waiting on
    # something nobody was there to answer. DEVNULL turns any such prompt into
    # an immediate EOF, which fails loudly instead of hanging silently.
    #
    # The log also means progress is watchable while it runs, which a captured
    # pipe never was: `tail -f` the path this prints.
    log_path = os.path.join(HANDOFF, "%s.log" % task)
    ensure_dirs()
    print("  streaming to %s" % os.path.relpath(log_path, ROOT))

    with open(log_path, "w", encoding="utf-8", errors="replace") as fh:
        try:
            p = subprocess.run(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                               stdout=fh, stderr=subprocess.STDOUT,
                               timeout=timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            fh.write("\n[delegate] timed out after %ds\n" % timeout)
            rc = 124

    out = open(log_path, encoding="utf-8", errors="replace").read()
    print(out[-4000:] if len(out) > 4000 else out)
    return rc, out


def next_id():
    ensure_dirs()
    used = [f[:-3] for f in os.listdir(INBOX) if f.endswith(".md")]
    used += [f[:-3] for f in os.listdir(DONE) if f.endswith(".md")]
    n = 1
    while "t%03d" % n in used:
        n += 1
    return "t%03d" % n


def compose(task_id, title, body):
    return "\n".join([
        "# %s - %s" % (task_id, title),
        "",
        body.strip(),
        "",
        CONTRACT.format(root=ROOT),
        REPORT_TEMPLATE.format(task_id=task_id),
    ])


def log(entry):
    ensure_dirs()
    entry["at"] = datetime.datetime.now().isoformat(timespec="seconds")
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# --- the gate --------------------------------------------------------------

GATE = [
    ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
    ("token lint", [sys.executable, "tools/lint_tokens.py"]),
    ("tray tests", [sys.executable, "tests/test_v4_tray.py"]),
    # Added after step 2 landed. A gate that does not include the test a task
    # just wrote cannot verify that task - the step 2 run reported 22/22 and
    # the gate could not confirm it.
    ("monitor tests", [sys.executable, "tests/test_v4_monitor.py"]),
    ("design contract", [sys.executable, "tests/test_design_v3.py"]),
]


def verify(quiet=False):
    """Run every acceptance check. Returns (ok, results)."""
    results = []
    for name, cmd in GATE:
        try:
            p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                               timeout=300)
            ok = p.returncode == 0
            tail = (p.stdout or p.stderr or "").strip().splitlines()
            detail = tail[-1] if tail else ""
        except Exception as exc:
            ok, detail = False, str(exc)
        results.append((name, ok, detail))
        if not quiet:
            print("  %-16s %s  %s" % (name, "PASS" if ok else "FAIL", detail[:70]))
    return all(ok for _, ok, _ in results), results


# --- commands --------------------------------------------------------------

def cmd_status(a):
    ensure_dirs()
    cli = cli_path()
    print("transport")
    if cli:
        print("  cursor-agent   %s" % cli)
        print("  -> headless delegation available, nothing to paste")
    else:
        print("  cursor-agent   NOT INSTALLED")
        print("  -> falling back to the file queue.")
        print("     To enable headless delegation, run in PowerShell:")
        print("       %s" % INSTALL_HINT)

    pending = sorted(f for f in os.listdir(INBOX) if f.endswith(".md"))
    reports = sorted(f for f in os.listdir(OUTBOX) if f.endswith(".md"))
    print("\nqueue")
    print("  inbox   %d task(s)   %s" % (len(pending), ", ".join(pending) or "-"))
    print("  outbox  %d report(s) %s" % (len(reports), ", ".join(reports) or "-"))
    if reports:
        print("\n  run `python tools/delegate.py collect` to gate and accept them")
    return 0


def cmd_send(a):
    ensure_dirs()
    task_id = a.id or next_id()

    if a.spec:
        body = open(a.spec, encoding="utf-8").read()
    elif a.body:
        body = a.body
    else:
        body = sys.stdin.read()

    brief = compose(task_id, a.title, body)
    path = os.path.join(INBOX, "%s.md" % task_id)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(brief)
    print("wrote %s" % os.path.relpath(path, ROOT))

    cli = cli_path()
    if a.transport == "queue" or (a.transport == "auto" and not cli):
        log({"id": task_id, "title": a.title, "transport": "queue", "event": "sent"})
        print("\nqueued for Cursor's in-IDE agent.")
        print("In Cursor, say:  work the handoff inbox")
        print("(.cursor/rules/handoff.mdc tells it the protocol)")
        return 0

    # Headless. Keep the prompt short - point at the file rather than inlining
    # it, so the agent reads the brief with its own file tools and the contract
    # does not get truncated in an argv.
    prompt = ("Read %s and do exactly what it says. Follow its Definition of "
              "done and write the report file it asks for before finishing."
              % os.path.relpath(path, ROOT).replace("\\", "/"))
    cmd = [cli, "-p", prompt, "--output-format", "text"]
    if a.model:
        cmd += ["--model", a.model]

    print("\nrunning: %s -p ... --model %s" % (os.path.basename(cli), a.model or "default"))
    log({"id": task_id, "title": a.title, "transport": "cli",
         "model": a.model, "event": "sent"})
    try:
        p = subprocess.run(cmd, cwd=ROOT, text=True, timeout=a.timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        print("cursor-agent timed out after %ds" % a.timeout)
        rc = 124
    log({"id": task_id, "event": "returned", "rc": rc})

    print("\ngate:")
    ok, _ = verify()
    log({"id": task_id, "event": "gate", "ok": ok})
    print("\n%s" % ("ACCEPTED - gate clean" if ok else
                    "REJECTED - gate failed, do not merge until it is green"))
    return 0 if ok else 1


def cmd_verify(a):
    print("gate:")
    ok, _ = verify()
    print("\n%s" % ("clean" if ok else "FAILED"))
    return 0 if ok else 1


def cmd_collect(a):
    """Read reports, run the gate, archive what passes."""
    ensure_dirs()
    reports = sorted(f for f in os.listdir(OUTBOX) if f.endswith(".md"))
    if not reports:
        print("no reports in outbox")
        return 0

    for name in reports:
        print("\n=== %s" % name)
        text = open(os.path.join(OUTBOX, name), encoding="utf-8").read()
        print(text[:1200])

    print("\ngate:")
    ok, _ = verify()
    if not ok:
        print("\nGATE FAILED - reports left in outbox, nothing archived.")
        return 1

    for name in reports:
        task_id = name[:-3]
        for folder in (INBOX, OUTBOX):
            src = os.path.join(folder, name)
            if os.path.isfile(src):
                shutil.move(src, os.path.join(DONE, "%s-%s.md" % (
                    task_id, "brief" if folder == INBOX else "report")))
        log({"id": task_id, "event": "accepted"})
    print("\nACCEPTED %d task(s) - archived to .cursor/handoff/done/" % len(reports))
    return 0


def cmd_chat(a):
    ok, detail = authed()
    if not ok:
        print("cursor-agent: %s" % detail)
        print("\nRun this once, then re-run the same command:")
        print("  cursor-agent login")
        return 2

    msg = open(a.spec, encoding="utf-8").read() if a.spec else (a.say or sys.stdin.read())
    if not a.no_contract:
        msg = msg.rstrip() + "\n" + CONTRACT.format(root=ROOT)

    rc, out = talk(a.task, msg, model=a.model, resume=not a.new,
                   timeout=a.timeout, force=not a.ask)
    log({"task": a.task, "event": "chat", "rc": rc, "model": a.model})

    # A gate that only asks "is the repo clean?" says ACCEPTED when the agent
    # never ran at all - an untouched tree passes every check by definition.
    # The first live run did exactly that: cursor-agent failed on auth and the
    # gate reported success. So the agent's own outcome is part of the verdict.
    agent_ok = rc == 0 and not any(
        m in out.lower() for m in ("authentication required", "not logged in",
                                   "error:", "rate limit"))
    if not agent_ok:
        print("\nREJECTED - cursor-agent did not complete the task (rc=%s)." % rc)
        print("Nothing was changed, so the gate below is meaningless on its own.")
        return 2

    print("\ngate:")
    gate_ok, _ = verify()
    log({"task": a.task, "event": "gate", "ok": gate_ok})
    if gate_ok:
        print("\nACCEPTED - agent finished and gate is clean")
    else:
        print("\nREJECTED - gate failed. Send the failures straight back:")
        print("  python tools/delegate.py chat --task %s --no-contract --say ..."
              % a.task)
    return 0 if gate_ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("status", help="transport + queue state")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("send", help="hand a task to Cursor")
    s.add_argument("--title", required=True)
    s.add_argument("--spec", help="path to a markdown file describing the task")
    s.add_argument("--body", help="the task text inline")
    s.add_argument("--id")
    s.add_argument("--model", default="composer",
                   help="Cursor model to run it on (default: composer)")
    s.add_argument("--transport", choices=["auto", "cli", "queue"], default="auto")
    s.add_argument("--timeout", type=int, default=3600)
    s.set_defaults(fn=cmd_send)

    s = sub.add_parser("verify", help="run the acceptance gate")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("collect", help="gate and archive finished reports")
    s.set_defaults(fn=cmd_collect)

    s = sub.add_parser("chat", help="talk to Cursor's agent directly (keeps the session)")
    s.add_argument("--task", required=True, help="conversation name, e.g. step2")
    s.add_argument("--spec", help="file whose contents become the message")
    s.add_argument("--say", help="the message inline")
    s.add_argument("--model", default="composer")
    s.add_argument("--no-contract", action="store_true",
                   help="skip the contract preamble (use on follow-up turns)")
    s.add_argument("--new", action="store_true", help="start a fresh session")
    s.add_argument("--ask", action="store_true",
                   help="make the agent ask before each shell command "
                        "(safer, but an unattended run will stall on the first one)")
    s.add_argument("--timeout", type=int, default=3600)
    s.set_defaults(fn=cmd_chat)

    a = ap.parse_args()
    if not getattr(a, "fn", None):
        ap.print_help()
        return 1
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
