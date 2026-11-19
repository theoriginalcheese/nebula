"""The phone's real-state studio: no invented clips, games, peers or pending apps.

    python tests/test_mobile_real.py

`seed_mock()` stays the contract fixture (test_mobile_contract.py). This covers
`obsauto.mobile_real`, which `python -m obsauto.mobile_agent` serves by default.
Everything runs against a temp directory; no recording is created, moved or
removed outside it.
"""
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import fsprobe
from obsauto.mobile_agent import MOCK_TOKEN
from obsauto.mobile_real import RealStudio, build_real_agent
from obsauto.phone_state import DiskSnapshot, peer_rows

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def say(agent, kind, data=None):
    return agent.handle({"type": kind, "id": "t", "data": data or {}})


def find(events, kind):
    return next((event for event in events if event["type"] == kind), None)


def write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


SIFU = ("Sifu", "Hades", "Sandfall")


def fake_status():
    def peer(host, dns, online, ips):
        return {"hostname": host, "dns": dns, "online": online, "active": False,
                "ips": ips, "os": "", "relay": "", "direct": False}
    return {
        "self": {"hostname": "Strix-Laptop", "dns": "strix-laptop.tail1.ts.net",
                 "ips": ["100.64.0.1"], "online": True},
        "self_online": True,
        "peer_list": [
            peer("llm", "llm.tail1.ts.net", True, ["100.64.0.2"]),
            peer("nas", "nas.tail1.ts.net", True, ["100.64.0.3"]),
            peer("Framework", "framework.tail1.ts.net", False, ["100.64.0.4"]),
            peer("localhost", "iphone172-1.tail1.ts.net", False, ["100.64.0.5"]),
            peer("100.64.0.6", "", False, ["100.64.0.6"]),
            peer("strix-laptop", "strix-laptop-1.tail1.ts.net", False, ["100.64.0.7"]),
            peer("strix-laptop", "strix-laptop.tail1.ts.net", True, ["100.64.0.1"]),
            peer("localhost", "", False, ["100.64.0.8"]),
        ],
    }


class Foreground:
    def __init__(self):
        self.value = None

    def __call__(self):
        return self.value


def make(root, foreground, config=None):
    cfg = {"recording_root": os.path.join(root, "recordings"), "sync_folder": ""}
    cfg.update(config or {})
    write(os.path.join(root, "config.json"), cfg)
    return RealStudio(MOCK_TOKEN, disk=DiskSnapshot(root=root),
                      foreground=foreground, tailscale_status=fake_status)


def pair(agent):
    return say(agent, "hello", {"deviceToken": MOCK_TOKEN})


def fg(exe, path="C:/Games/x/" ):
    return {"exe": exe, "path": path + exe, "name": exe, "title": "T",
            "width": 2560, "height": 1440, "fullscreen": True}


with tempfile.TemporaryDirectory() as root:
    # ------------------------------------------------ empty machine: nothing invented
    probe = Foreground()
    agent = make(root, probe)
    snap = find(pair(agent), "snapshot")["data"]
    blob = json.dumps(snap)
    check("a missing recording root sends an empty clip list", snap["clips"] == [])
    check("no games file sends no games", snap["games"] == [] and snap["nonGames"] == [])
    check("none of the mock titles appear", not any(word in blob for word in SIFU))
    check("nothing is pending with no foreground app", snap["pending"] == [])

    # ------------------------------------------------ real clips, real games
    rec = os.path.join(root, "recordings")
    fsprobe.forget(rec)  # the "missing" verdict above is memoised for ~10s
    os.makedirs(os.path.join(rec, "Portal 2"))
    clip_path = os.path.join(rec, "Portal 2", "one.mkv")
    with open(clip_path, "wb") as fh:
        fh.write(b"x" * 2048)
    os.utime(clip_path, (time.time() - 3600, time.time() - 3600))
    with open(os.path.join(rec, "notes.txt"), "w") as fh:
        fh.write("not a video")
    write(os.path.join(root, "games.json"), {
        "games": {"portal2.exe": {"display_name": "Portal 2", "source": "steam"},
                  "portal2_x.exe": {"display_name": "Portal 2", "source": "steam"},
                  "zzz.exe": {"display_name": "ZZZ", "source": "manual", "capture": "both"}},
        "non_games": {"blender.exe": True},
    })
    agent = make(root, probe)
    snap = find(pair(agent), "snapshot")["data"]
    check("clips are the video files that exist under the root",
          [c["file"] for c in snap["clips"]] == ["one.mkv"] and snap["clips"][0]["bytes"] == 2048,
          snap["clips"])
    check("an unmeasured clip length is null, not a number", snap["clips"][0]["duration"] is None)
    names = sorted(g["name"] for g in snap["games"])
    check("games come from games.json, grouped by display name",
          names == ["Portal 2", "ZZZ"], names)
    portal = next(g for g in snap["games"] if g["name"] == "Portal 2")
    check("a game's clip count and bytes are measured",
          portal["clipCount"] == 1 and portal["bytes"] == 2048 and portal["source"] == "steam")
    check("capture override is read", next(g for g in snap["games"] if g["name"] == "ZZZ")["capture"] == "both")
    check("non-games come from games.json",
          [row["exe"] for row in snap["nonGames"]] == ["blender.exe"])
    check("the clip's game id matches its game row",
          snap["clips"][0]["game"]["id"] == portal["id"])
    check("an hour-old clip is not flagged as still being written",
          snap["clips"][0]["writing"] is False)
    last = snap["session"]["lastSession"]
    check("the idle card is that clip, not a sample session",
          last["game"]["name"] == "Portal 2" and last["bytes"] == 2048
          and last["duration"] == 0 and snap["clips"][0]["thumbnailURL"] is None,
          last)
    check("a thumbnail request cannot name a recording",
          agent.thumb_bytes("../one.mkv") is None
          and agent.thumb_bytes(r"..\one.mkv") is None
          and agent.thumb_bytes("one.mkv") is None)

    # ------------------------------------------------ peers: names only
    peers = snap["peers"]
    check("every named peer is sent, online or not",
          [p["name"] for p in peers] == [
              "llm", "nas", "Framework", "iphone172-1", "strix-laptop-1"], peers)
    check("the local node is skipped", all(p["name"].lower() != "strix-laptop" for p in peers))
    check("no IP address anywhere in the payload",
          not re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", json.dumps(snap)))
    check("peer rows are name/online/isHost only",
          all(set(p) == {"name", "online", "isHost"} for p in peers))
    check("offline peers stay in", sum(1 for p in peers if not p["online"]) == 3)
    check("a useless hostname is not shown",
          all(p["name"] not in ("localhost", "") for p in peers))
    check("peer_rows tolerates no tailscale", peer_rows(None) == [])
    check("the tailnet suffix never appears", "tail1" not in json.dumps(peers))

    # ------------------------------------------------ pending
    probe.value = fg("portal2.exe")
    agent.refresh(force=True)
    check("a known game in front is never pending", agent.pending == [])
    probe.value = fg("blender.exe")
    agent.refresh(force=True)
    check("a known non-game in front is never pending", agent.pending == [])
    probe.value = fg("explorer.exe")
    agent.refresh(force=True)
    check("a denylisted shell is never pending", agent.pending == [])
    probe.value = fg("Nebula.exe")
    agent.refresh(force=True)
    check("Nebula itself is never pending", agent.pending == [])

    probe.value = fg("Sandfall-Win64-Shipping.exe")
    agent.refresh(force=True)
    check("an unknown exe needs a second look before it is asked about", agent.pending == [])
    agent.refresh(force=True)
    check("an unknown foreground exe becomes pending",
          [p["exe"] for p in agent.pending] == ["Sandfall-Win64-Shipping.exe"])
    check("pending carries the real window",
          agent.pending[0]["window"] == {"fullscreen": True, "width": 2560, "height": 1440})
    events = agent.poll_events()
    check("poll_events announces it", find(events, "app.pending") is not None)

    # Another machine adds a game to the file while this one is running.
    on_disk = json.load(open(os.path.join(root, "games.json")))
    on_disk["games"]["elsewhere.exe"] = {"display_name": "Elsewhere", "source": "manual"}
    write(os.path.join(root, "games.json"), on_disk)

    pid = agent.pending[0]["id"]
    out = say(agent, "app.classify", {"pendingId": pid, "isGame": True, "capture": "buffer"})
    check("classify acks and resolves", out[0]["type"] == "ack" and find(out, "app.resolved") is not None)
    saved = json.load(open(os.path.join(root, "games.json")))
    entry = saved["games"].get("sandfall-win64-shipping.exe")
    check("the verdict is written to games.json", entry is not None and entry["capture"] == "buffer", entry)
    check("it lives in exactly one bucket",
          "sandfall-win64-shipping.exe" not in saved["non_games"])
    check("another machine's addition survives",
          "elsewhere.exe" in saved["games"] and "portal2.exe" in saved["games"])
    check("existing non-games survive", "blender.exe" in saved["non_games"])
    check("the games event lists the new game",
          any(g["name"] == "Sandfall-Win64-Shipping" for g in find(out, "games")["data"]["games"]))
    check("classifying the same app twice is refused", say(agent, "app.classify",
          {"pendingId": pid, "isGame": True})[0]["data"]["code"] == "notFound")

    restarted = make(root, probe)
    pair(restarted)
    restarted.refresh(force=True)
    restarted.refresh(force=True)
    check("after a restart the same exe is not asked about again", restarted.pending == [])
    check("and it is still a game",
          any(g["name"] == "Sandfall-Win64-Shipping" for g in restarted.games))

    # A non-game verdict, then a flip, never leaves the exe in both buckets.
    probe.value = fg("someutility.exe")
    restarted.refresh(force=True)
    restarted.refresh(force=True)
    out = say(restarted, "app.classify",
              {"pendingId": restarted.pending[0]["id"], "isGame": False})
    saved = json.load(open(os.path.join(root, "games.json")))
    check("a non-game verdict persists", saved["non_games"].get("someutility.exe") is True)
    say(restarted, "app.reclassify", {"exe": "someutility.exe", "isGame": True})
    saved = json.load(open(os.path.join(root, "games.json")))
    check("a flip moves it, one bucket only",
          "someutility.exe" in saved["games"] and "someutility.exe" not in saved["non_games"])
    say(restarted, "app.reclassify", {"exe": "Portal 2", "isGame": False})
    saved = json.load(open(os.path.join(root, "games.json")))
    check("demoting a game by name files all its exes under non-games",
          {"portal2.exe", "portal2_x.exe"} <= set(saved["non_games"])
          and not ({"portal2.exe", "portal2_x.exe"} & set(saved["games"])))

    # ------------------------------------------------ an unreadable file is never clobbered
    with open(os.path.join(root, "games.json"), "w") as fh:
        fh.write("{ not json")
    probe.value = fg("another.exe")
    restarted.refresh(force=True)
    restarted.refresh(force=True)
    refusal = say(restarted, "app.classify", {"pendingId": restarted.pending[0]["id"], "isGame": True})
    check("a corrupt games.json is refused, not overwritten",
          refusal[0]["data"]["code"] == "unsaved"
          and open(os.path.join(root, "games.json")).read() == "{ not json")

    # ------------------------------------------------ nothing here touches a recording
    check("clip.delete is refused", say(restarted, "clip.delete", {"id": "x"})[0]["data"]["code"] == "readOnly")
    check("clip.trim is refused", say(restarted, "clip.trim", {"id": "x"})[0]["data"]["code"] == "readOnly")
    check("session.start does not invent a recording",
          say(restarted, "session.start")[0]["data"]["code"] == "obsUnavailable"
          and restarted.session["state"] == "idle")
    check("the recording and the folder are untouched",
          os.path.getsize(clip_path) == 2048 and os.path.isdir(os.path.join(rec, "Portal 2")))

    check("build_real_agent uses the real class", isinstance(build_real_agent(root=root), RealStudio))

source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "obsauto", "mobile_real.py"), encoding="utf-8").read()
check("mobile_real never removes or renames a file",
      not any(token in source for token in ("os.remove", "os.unlink", "shutil.rmtree",
                                            "shutil.move", "os.rename", "os.rmdir")))

passed_all = all(ok for _, ok, _ in results)
for name, ok, detail in results:
    print("%s  %-62s %s" % ("PASS" if ok else "FAIL", name, detail if not ok else ""))
print("\n%s (%d checks)" % ("ALL PASS" if passed_all else "FAILURES PRESENT", len(results)))
sys.exit(0 if passed_all else 1)
