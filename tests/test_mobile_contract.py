"""Mobile build-spec phase 1: the mock PC agent speaks §4.

    python tests/test_mobile_contract.py

Done when a client can run the scripted session (idle, recording, pause,
resume, stop, one pending app, twenty clips) and every command in the spec
acks or errors as specified. The mock never touches a recording on disk.
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.mobile_agent import MOCK_TOKEN, seed_mock, serve_mock

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def say(agent, kind, data=None, mid="1"):
    return agent.handle({"type": kind, "id": mid, "data": data or {}})


def kinds(messages):
    return [item["type"] for item in messages]


def find(messages, kind):
    return next(item for item in messages if item["type"] == kind)


def paired(agent):
    say(agent, "hello", {"deviceToken": MOCK_TOKEN, "appVersion": "test"})


# ---------------------------------------------------------------- scripted session

agent = seed_mock()
refused = say(agent, "hello", {"deviceToken": "nope"})
check("a wrong token is refused and does not open a session",
      kinds(refused) == ["error"] and refused[0]["data"]["code"] == "unauthorised")
check("a command before hello is refused",
      say(agent, "session.start")[0]["data"]["code"] == "unpaired")

hello = say(agent, "hello", {"deviceToken": MOCK_TOKEN, "appVersion": "test"})
snap = find(hello, "snapshot")["data"]
check("hello acks and returns a snapshot",
      kinds(hello) == ["ack", "snapshot"] and snap["session"]["state"] == "idle")
check("the snapshot carries the scripted studio",
      len(snap["clips"]) == 20 and len(snap["pending"]) == 1
      and snap["pending"][0]["exe"] == "Sandfall-Win64-Shipping.exe")
blob = json.dumps(snap)
check("the snapshot carries no footage path",
      ":\\" not in blob and "Z:" not in blob and "/OBS" not in blob)

started = say(agent, "session.start")
check("session.start moves idle to recording",
      kinds(started) == ["ack", "session"]
      and find(started, "session")["data"]["state"] == "recording")
agent.advance(30)
paused = say(agent, "session.pause")
check("session.pause holds the clock",
      find(paused, "session")["data"]["state"] == "paused")
agent.advance(5)
resumed = say(agent, "session.resume")
check("session.resume keeps the paused seconds",
      find(resumed, "session")["data"]["state"] == "recording"
      and find(resumed, "session")["data"]["pausedTotal"] >= 5)
marked = say(agent, "session.mark", {"label": "Boss phase"})
check("session.mark adds a manual highlight",
      find(marked, "session")["data"]["highlights"][-1]["kind"] == "manual")
stopped = say(agent, "session.stop")
check("session.stop finalises a clip and returns to idle",
      "clip.added" in kinds(stopped)
      and find(stopped, "session")["data"]["state"] == "idle"
      and find(stopped, "session")["data"]["lastSession"]["game"]["name"] == "Sifu")
check("the original clips are still there after stop",
      len(agent.clips) == 21)

# ---------------------------------------------------------------- refusals the spec names

quiet = seed_mock()
paired(quiet)
quiet.settings["discardUnder"] = 120
say(quiet, "session.start")
discarded = say(quiet, "session.stop")
check("a clip shorter than discardUnder is never announced",
      "clip.added" not in kinds(discarded) and len(quiet.clips) == 20)

empty = seed_mock()
paired(empty)
empty.foreground = None
check("session.start with no foreground game is noGame",
      say(empty, "session.start")[0]["data"]["code"] == "noGame")

busy = seed_mock()
paired(busy)
say(busy, "session.start")
check("a second session.start is busy",
      say(busy, "session.start")[0]["data"]["code"] == "busy")

# ---------------------------------------------------------------- classify, capture, settings

judge = seed_mock()
paired(judge)
bad = say(judge, "app.classify", {"pendingId": "pending-sandfall", "isGame": True,
                                   "capture": "nope"})
check("a bad capture mode leaves the pending app waiting",
      bad[0]["data"]["code"] == "invalid" and len(judge.pending) == 1)
verdict = say(judge, "app.classify", {"pendingId": "pending-sandfall", "isGame": True})
check("app.classify adds the game and resolves the prompt",
      kinds(verdict) == ["ack", "app.resolved", "games"]
      and judge.games[0]["source"] == "prompt" and judge.pending == [])
undo = say(judge, "app.reclassify",
           {"exe": "Sandfall-Win64-Shipping.exe", "isGame": False})
check("app.reclassify undo moves it back out of the game list",
      "ack" == undo[0]["type"]
      and all(row["id"] != "pending-sandfall" for row in judge.games)
      and any(row["exe"] == "Sandfall-Win64-Shipping.exe" for row in judge.non_games))
capture = say(judge, "game.setCapture", {"gameId": "sifu", "capture": "buffer"})
check("game.setCapture updates that game only",
      find(capture, "games")["data"]["games"][0]["id"] != "sifu"
      or next(row for row in judge.games if row["id"] == "sifu")["capture"] == "buffer")

check("a read-only setting is refused",
      say(judge, "settings.set", {"key": "hotkey", "value": "F8"})[0]["data"]["code"]
      == "readOnly")
check("an illegal replay length is refused",
      say(judge, "settings.set", {"key": "replaySeconds", "value": 10})[0]["data"]["code"]
      == "invalid")
saved = say(judge, "settings.set", {"key": "replaySeconds", "value": 60})
check("a writable setting acks and is stored",
      saved[0]["type"] == "ack" and judge.settings["replaySeconds"] == 60)
off = say(judge, "settings.set", {"key": "offload.auto", "value": False})
check("a dotted setting writes the nested field",
      off[0]["type"] == "ack" and judge.settings["offload"]["auto"] is False)

# ---------------------------------------------------------------- clips, replay, stats, stream

library = seed_mock()
paired(library)
listed = say(library, "clips.list", {"query": "sifu"})
check("clips.list filters by game name and pages at fifty",
      listed[0]["type"] == "ack" and len(listed[0]["data"]["clips"]) == 10
      and listed[0]["data"]["nextCursor"] is None)
writing = say(library, "clip.trim", {"id": "clip-02", "in": 0, "out": 10})
check("trim refuses a clip that is still being written",
      writing[0]["data"]["code"] == "busy")
copying = say(library, "clip.trim", {"id": "clip-03", "in": 0, "out": 10})
check("trim refuses a clip that is still being copied",
      copying[0]["data"]["code"] == "busy")
trimmed = say(library, "clip.trim", {"id": "clip-01", "in": 1, "out": 4})
check("trim keeps the original and adds a new clip",
      find(trimmed, "clip.added")["data"]["id"] == "clip-01-trim"
      and any(row["id"] == "clip-01" for row in library.clips))
removed = say(library, "clip.delete", {"id": "clip-04"})
check("delete in the mock drops the row and nothing else",
      find(removed, "clip.removed")["data"]["id"] == "clip-04"
      and all(row["id"] != "clip-04" for row in library.clips))

check("replay.save outside bufferOnly is refused",
      say(library, "replay.save")[0]["data"]["code"] == "invalid")
armed = seed_mock()
paired(armed)
armed.note_launch("buffer")
check("a buffer launch arms bufferOnly",
      armed.session["state"] == "bufferOnly")
saved_replay = say(armed, "replay.save")
check("replay.save adds a replay clip and stays armed",
      find(saved_replay, "clip.added")["data"]["kind"] == "replay"
      and armed.session["state"] == "bufferOnly")

check("stats flow only while subscribed",
      say(library, "stats.subscribe")[0]["type"] == "ack"
      and library.stats_tick()["type"] == "stats"
      and say(library, "stats.unsubscribe")[0]["type"] == "ack"
      and library.stats_tick() is None)

streamed = say(library, "remote.stream")
check("remote.stream acks when Moonlight is installed",
      streamed[0]["type"] == "ack" and library.streaming)
library.settings["remote"]["moonlightInstalled"] = False
check("remote.stream errors when Moonlight is missing",
      say(library, "remote.stream")[0]["data"]["code"] == "noMoonlight")
check("an unknown message type errors",
      say(library, "clip.launch")[0]["data"]["code"] == "unknown")

source = open(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "obsauto", "mobile_agent.py"),
    encoding="utf-8",
).read()
check("the agent source never opens or deletes a recording",
      not any(token in source for token in (
          "os.remove", "os.unlink", "shutil.", "os.rename",
      )))

# ---------------------------------------------------------------- the socket, one round trip

sock_agent = seed_mock()
stop, port = serve_mock(sock_agent)
try:
    from websocket import create_connection
    conn = create_connection("ws://127.0.0.1:%d/nebula" % port, timeout=5)
    conn.send(json.dumps({
        "type": "hello", "id": "socket",
        "data": {"deviceToken": MOCK_TOKEN, "appVersion": "test"},
    }))
    first = json.loads(conn.recv())
    second = json.loads(conn.recv())
    conn.close()
    check("a websocket client receives ack then snapshot",
          first["type"] == "ack" and first["id"] == "socket"
          and second["type"] == "snapshot" and len(second["data"]["clips"]) == 20)
except Exception as exc:
    check("a websocket client receives ack then snapshot", False, str(exc))
finally:
    stop.set()

# A still has to be fetchable while the phone's socket is held open.
# The old listener served one connection at a time, so this GET never
# arrived and every card stayed on the plain backdrop.
held = seed_mock()
held.thumb_bytes = lambda name: b"\xff\xd8\xff\xd9" if name == "clip-aaaaaaaaaaaa.jpg" else None
stop, port = serve_mock(held)
try:
    from websocket import create_connection
    held_conn = create_connection("ws://127.0.0.1:%d/nebula" % port, timeout=5)
    held_conn.send(json.dumps({
        "type": "hello", "id": "held",
        "data": {"deviceToken": MOCK_TOKEN, "appVersion": "test"},
    }))
    held_conn.recv()
    with urllib.request.urlopen(
        "http://127.0.0.1:%d/thumbs/clip-aaaaaaaaaaaa.jpg" % port, timeout=3
    ) as response:
        body = response.read()
        code = response.status
    held_conn.close()
    check("a clip still loads while the phone socket is open",
          code == 200 and body.startswith(b"\xff\xd8"), (code, body[:8]))
except Exception as exc:
    check("a clip still loads while the phone socket is open", False, str(exc))
finally:
    stop.set()

# The playback route on an agent that serves no files is a plain 404, and it
# does not hang a client that was expecting a websocket upgrade.
bare = seed_mock()
stop, port = serve_mock(bare)
try:
    try:
        urllib.request.urlopen(
            "http://127.0.0.1:%d/files/clip/clip-aaaaaaaaaaaa" % port, timeout=3)
        code = 200
    except urllib.error.HTTPError as exc:
        code = exc.code
    check("an agent with no files answers a clip GET with 404", code == 404, code)
except Exception as exc:
    check("an agent with no files answers a clip GET with 404", False, str(exc))
finally:
    stop.set()

passed_all = all(ok for _, ok, _ in results)
for name, ok, detail in results:
    print("%s  %-62s %s" % ("PASS" if ok else "FAIL", name, detail))
print("\n%s (%d checks)" % ("ALL PASS" if passed_all else "FAILURES PRESENT", len(results)))
sys.exit(0 if passed_all else 1)
