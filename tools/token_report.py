"""What a delegated job cost, measured rather than asserted.

    python tools/token_report.py --chat <id> --task t001
    python tools/token_report.py --rollup

Run automatically by `tools/delegate.py` after every gate.

What this measures, and what it does not
----------------------------------------
`cursor-agent` keeps a transcript per chat under

    ~/.cursor/projects/<workspace-slug>/agent-transcripts/<chat-id>/

That is local, needs no credentials, and is a **floor** on what a job cost. It
is emphatically not a bill:

* tool output the agent read may not all land in the transcript - `step2`
  measured 8.6 KB for work that edited ~600 lines across four files, so the
  transcript plainly does not contain everything the model was charged for
* cached input is billed differently from fresh input, and nothing local
  distinguishes them
* chars/4 is a rule of thumb for prose; code and JSON run nearer chars/3

So every row is labelled `source=proxy` and no dollar figure is invented. For
money, read Cursor's own dashboard - it is the only thing that knows.

Why not pull the dashboard automatically
----------------------------------------
The obvious next step is to read Cursor's session token out of
`state.vscdb` and call `api2.cursor.sh/aiserver.v1.DashboardService/...`.
Deliberately not done: that means lifting a credential out of a local database
and calling private, undocumented endpoints. It would break without warning and
it is not our token to take. An honest floor beats a fragile exact number.

What it is genuinely good for
-----------------------------
Relative comparison, which is the actual question: is delegating this class of
task getting cheaper or more expensive, and which tasks are expensive? The
ledger answers that without anyone guessing.
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, ".cursor", "handoff", "token-ledger.jsonl")

# `cursor-agent` slugs the workspace path: C:\Users\antho\nebula -> c-Users-antho-nebula
def slug(path):
    return path.replace(":", "").replace("\\", "-").replace("/", "-").lower()


def transcript_dir(chat_id, workspace=ROOT):
    base = os.path.join(os.path.expanduser("~"), ".cursor", "projects")
    exact = os.path.join(base, slug(workspace), "agent-transcripts", chat_id)
    if os.path.isdir(exact):
        return exact
    # The slug rule is undocumented; fall back to finding the id anywhere.
    if os.path.isdir(base):
        for proj in os.listdir(base):
            cand = os.path.join(base, proj, "agent-transcripts", chat_id)
            if os.path.isdir(cand):
                return cand
    return None


def measure(chat_id, workspace=ROOT):
    d = transcript_dir(chat_id, workspace)
    if not d:
        return {"source": "unavailable", "transcript_chars": 0,
                "est_tokens": 0, "files": 0}
    chars = files = 0
    for dirpath, _, names in os.walk(d):
        for n in names:
            try:
                chars += os.path.getsize(os.path.join(dirpath, n))
                files += 1
            except OSError:
                continue
    return {"source": "proxy", "transcript_chars": chars,
            "est_tokens": chars // 4, "files": files}


def append(row):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def report(chat_id, task, model, gate_ok, workspace=ROOT, quiet=False):
    m = measure(chat_id, workspace)
    row = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "chat_id": chat_id,
        "task": task,
        "model": model,
        "gate_passed": gate_ok,
        "source": m["source"],
        "transcript_chars": m["transcript_chars"],
        "est_tokens_chars_div_4": m["est_tokens"],
        # Filled in by hand or by the orchestrator's own meter - Claude Code's
        # /cost knows this and nothing here can.
        "claude_cost_usd": None,
        "charged_usd": None,          # only Cursor's dashboard knows
    }
    append(row)
    if not quiet:
        if m["source"] == "unavailable":
            print("tokens: no local transcript for %s (source=unavailable)" % chat_id[:8])
        else:
            print("tokens: ~%s est · %.1f KB transcript · source=proxy (floor, not a bill)"
                  % ("{:,}".format(m["est_tokens"]), m["transcript_chars"] / 1024.0))
    return row


def rollup(path=LEDGER):
    if not os.path.isfile(path):
        print("no ledger yet: %s" % path)
        return 1
    rows = [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]
    if not rows:
        print("ledger is empty")
        return 0

    by_task = {}
    for r in rows:
        t = by_task.setdefault(r["task"], {"turns": 0, "est": 0, "chars": 0,
                                           "pass": 0, "chat": r["chat_id"]})
        t["turns"] += 1
        t["est"] = max(t["est"], r.get("est_tokens_chars_div_4") or 0)
        t["chars"] = max(t["chars"], r.get("transcript_chars") or 0)
        t["pass"] += 1 if r.get("gate_passed") else 0

    print("%-10s %6s %7s %12s  %s" % ("task", "turns", "passed", "~tokens", "chat"))
    print("-" * 58)
    total = 0
    for name, t in sorted(by_task.items(), key=lambda kv: -kv[1]["est"]):
        total += t["est"]
        print("%-10s %6d %7d %12s  %s"
              % (name, t["turns"], t["pass"], "{:,}".format(t["est"]), t["chat"][:8]))
    print("-" * 58)
    print("%-10s %6s %7s %12s" % ("total", "", "", "{:,}".format(total)))
    print("\nsource=proxy: transcript size / 4. A floor, not a bill.")
    print("For money, open Cursor's dashboard - nothing local knows the charge.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chat")
    ap.add_argument("--task", default="?")
    ap.add_argument("--model", default="composer")
    ap.add_argument("--gate-ok", action="store_true")
    ap.add_argument("--workspace", default=ROOT)
    ap.add_argument("--rollup", action="store_true")
    a = ap.parse_args()

    if a.rollup:
        return rollup()
    if not a.chat:
        ap.error("--chat is required unless --rollup")
    report(a.chat, a.task, a.model, a.gate_ok, a.workspace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
