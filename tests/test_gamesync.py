"""Tests for the GitHub game-list sync, with the GitHub API mocked.

Verifies the merge-never-clobber contract (the whole point of syncing through a
shared store) and that failures degrade to no-ops rather than raising.

    python tests/test_gamesync.py
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import gamesync as gamesync_module
from obsauto.gamesync import GameSync

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeGitHub:
    """A tiny in-memory stand-in for the GitHub contents API."""
    def __init__(self, initial):
        self.body = json.dumps(initial).encode()
        self.sha = "sha0"
        self.puts = 0

    def get(self, url, headers=None, timeout=None):
        return FakeResponse(200, {
            "sha": self.sha,
            "content": base64.b64encode(self.body).decode(),
        })

    def put(self, url, headers=None, json=None, timeout=None):
        self.puts += 1
        self.body = base64.b64decode(json["content"])
        self.sha = f"sha{self.puts}"
        return FakeResponse(200, {"content": {"sha": self.sha}})


CFG = {
    "github_token": "t", "github_gamedata_repo": "o/r",
    "github_gamedata_path": "games.json",
}


def run():
    # ---- enabled/disabled gating ----
    off = GameSync({"github_token": "", "github_gamedata_repo": ""})
    check("disabled when unconfigured", off.enabled is False)
    check("disabled fetch is None", off.fetch() is None)
    check("disabled push is None", off.push({"games": {}}) is None)

    # ---- merge, never clobber ----
    # Remote already knows game A; local just learned game B. A push must keep
    # BOTH, not replace remote with local.
    remote_start = {"games": {"a.exe": {"display_name": "A"}}, "non_games": {}}
    fake = FakeGitHub(remote_start)
    gamesync_module.requests = fake

    sync = GameSync(CFG, on_log=lambda m: None)
    local = {"games": {"b.exe": {"display_name": "B"}}, "non_games": {"tool.exe": True}}
    merged = sync.push(local)
    check("push returns merged", merged is not None)
    check("merge keeps remote entry", "a.exe" in merged["games"], list(merged["games"]))
    check("merge adds local entry", "b.exe" in merged["games"])
    check("merge keeps non_games", "tool.exe" in merged["non_games"])
    on_remote = json.loads(fake.body)
    check("remote now has both", "a.exe" in on_remote["games"] and "b.exe" in on_remote["games"])

    # ---- fetch reflects what's stored ----
    got = sync.fetch()
    check("fetch returns stored data", "a.exe" in got["games"] and "b.exe" in got["games"])

    # ---- no-op when already in sync (no redundant PUT) ----
    puts_before = fake.puts
    sync.fetch()  # refresh sha
    sync.push(merged)
    check("no PUT when already in sync", fake.puts == puts_before, f"{fake.puts} vs {puts_before}")

    # ---- a reclassification survives the round trip ----
    # The merge used to be a plain union, which cannot express a *removal*: the
    # remote's copy of the old bucket was read straight back in, so promoting
    # an ignored app left it in both lists and the next pull put it back where
    # it started. Local wins per key, in both directions.
    remote_says_tool = {"games": {}, "non_games": {"tool.exe": True}}
    fake2 = FakeGitHub(remote_says_tool)
    gamesync_module.requests = fake2
    sync4 = GameSync(CFG, on_log=lambda m: None)
    promoted = {"games": {"tool.exe": {"display_name": "Tool"}}, "non_games": {}}
    out = sync4.push(promoted)
    check("promotion reaches the remote", "tool.exe" in out["games"], out)
    check("promotion clears the old bucket",
          "tool.exe" not in out["non_games"], out["non_games"])
    stored = json.loads(fake2.body)
    check("the remote file itself lists it once",
          "tool.exe" in stored["games"] and "tool.exe" not in stored["non_games"],
          stored)

    # And the other way: demoting a game the remote still lists as one.
    fake3 = FakeGitHub({"games": {"setup.exe": {"display_name": "Setup"}}, "non_games": {}})
    gamesync_module.requests = fake3
    sync5 = GameSync(CFG, on_log=lambda m: None)
    out = sync5.push({"games": {}, "non_games": {"setup.exe": True}})
    check("demotion clears the games bucket",
          "setup.exe" not in out["games"] and "setup.exe" in out["non_games"], out)

    # Additions made elsewhere still survive - that is what merging is for.
    fake4 = FakeGitHub({"games": {"other.exe": {"display_name": "Other"}},
                        "non_games": {"tool.exe": True}})
    gamesync_module.requests = fake4
    sync6 = GameSync(CFG, on_log=lambda m: None)
    out = sync6.push({"games": {"tool.exe": {"display_name": "Tool"}}, "non_games": {}})
    check("another machine's game is not lost by a local reclassification",
          "other.exe" in out["games"], out["games"])

    # ---- 404 (empty repo) treated as empty, not an error ----
    class Fake404(FakeGitHub):
        def get(self, url, headers=None, timeout=None):
            return FakeResponse(404)
    gamesync_module.requests = Fake404({})
    sync2 = GameSync(CFG, on_log=lambda m: None)
    empty = sync2.fetch()
    check("404 -> empty dict", empty == {"games": {}, "non_games": {}}, empty)

    # ---- network error degrades to None, never raises ----
    class Boom:
        def get(self, *a, **k):
            raise ConnectionError("no network")
        def put(self, *a, **k):
            raise ConnectionError("no network")
    gamesync_module.requests = Boom()
    sync3 = GameSync(CFG, on_log=lambda m: None)
    raised = False
    try:
        r1 = sync3.fetch()
        r2 = sync3.push(local)
    except Exception:
        raised = True
    check("network error never raises", not raised)
    check("network error fetch -> None", r1 is None)
    check("network error push -> None", r2 is None)


run()

# ---- NAS + MultiGameSync -------------------------------------------------
import tempfile
from obsauto.gamesync import NasGameSync, MultiGameSync

nas_root = tempfile.mkdtemp(prefix="nebula-nas-games-")
nas_cfg = {"nas_offload_root": nas_root, "games_sync_nas": True}
nas = NasGameSync(nas_cfg, on_log=lambda m: None)
check("nas enabled with root", nas.enabled)
empty = nas.fetch()
check("nas empty fetch", empty == {"games": {}, "non_games": {}})
seed = {"games": {"a.exe": {"name": "A"}}, "non_games": {}}
pushed = nas.push(seed)
check("nas push ok", pushed is not None and "a.exe" in pushed["games"])
again = nas.fetch()
check("nas fetch sees push", "a.exe" in (again or {}).get("games", {}))

other = {"games": {"b.exe": {"name": "B"}}, "non_games": {}}
merged = nas.push(other)
check("nas merge keeps both",
      merged and "a.exe" in merged["games"] and "b.exe" in merged["games"])

off = NasGameSync({"nas_offload_root": "", "games_sync_nas": True})
check("nas disabled without root", not off.enabled)

multi = MultiGameSync([nas, GameSync({"github_token": "", "github_gamedata_repo": ""})])
check("multi enabled via nas", multi.enabled)
check("multi status mentions NAS", "NAS" in multi.status_label())
mf = multi.fetch()
check("multi fetch has games", mf and "a.exe" in mf["games"])

# unreachable root
gone = NasGameSync({"nas_offload_root": os.path.join(nas_root, "missing-dir"),
                    "games_sync_nas": True})
check("nas fetch None when root missing", gone.fetch() is None)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<38} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
