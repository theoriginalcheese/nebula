"""The phone's real-state studio: no invented clips, games, peers or pending apps.

    python tests/test_mobile_real.py

`seed_mock()` stays the contract fixture (test_mobile_contract.py). This covers
`obsauto.mobile_real`, which `python -m obsauto.mobile_agent` serves by default.
Everything runs against a temp directory; no recording is created, moved or
removed outside it.
"""
import http.client
import json
import os
import re
import socket
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import config as config_mod
from obsauto import fsprobe, mobile_real
from obsauto.mobile_agent import MOCK_TOKEN, serve_mock
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

# ====================================================================== OBS probe
def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen(4)
open_port = listener.getsockname()[1]
dead_port = free_port()
check("a closed OBS port probes false", mobile_real.probe_obs("127.0.0.1", dead_port) is False)
check("an open OBS port probes true", mobile_real.probe_obs("127.0.0.1", open_port) is True)
check("a junk port probes false, never raises",
      mobile_real.probe_obs("127.0.0.1", "nope") is False
      and mobile_real.probe_obs("127.0.0.1", 0) is False
      and mobile_real.probe_obs(None, 70000) is False)
began = time.monotonic()
mobile_real.probe_obs("127.0.0.1", dead_port)
check("a probe is bounded", time.monotonic() - began < 1.0)

with tempfile.TemporaryDirectory() as root:
    agent = make(root, Foreground(), {"obs_host": "127.0.0.1", "obs_port": dead_port})
    check("obs.connected is false while the port is closed",
          find(pair(agent), "snapshot")["data"]["obs"] == {"connected": False})
    agent = make(root, Foreground(), {"obs_host": "127.0.0.1", "obs_port": open_port,
                                      "obs_password": "hunter2-secret"})
    snap = find(pair(agent), "snapshot")["data"]
    check("obs.connected is true while the port is open", snap["obs"] == {"connected": True})
    check("the OBS password is never in the payload", "hunter2-secret" not in json.dumps(snap))
listener.close()

# ====================================================================== settings.set
with tempfile.TemporaryDirectory() as root:
    agent = make(root, Foreground(), {"obs_password": "keep-me", "toggle_hotkey": "f12",
                                      "obs_port": dead_port, "obs_host": "127.0.0.1"})
    snap = find(pair(agent), "snapshot")["data"]["settings"]
    check("an unset idle timeout reads as the desktop default, not 0",
          snap["idleTimeout"] == config_mod.DEFAULTS["idle_timeout_seconds"] != 0, snap)
    check("unset replay and minimum-clip values are the defaults",
          snap["replaySeconds"] == config_mod.DEFAULTS["replay_seconds"]
          and snap["discardUnder"] == config_mod.DEFAULTS["min_clip_seconds"])

    def saved_config():
        with open(os.path.join(root, "config.json"), encoding="utf-8") as fh:
            return json.load(fh)

    cases = (("launchCapture", "both", "default_capture_mode", "both"),
             ("replaySeconds", 45, "replay_seconds", 45),
             ("idleTimeout", 120, "idle_timeout_seconds", 120),
             ("discardUnder", 25, "min_clip_seconds", 25),
             ("keepAliveApps", [" Discord.exe ", "", "discord.exe", "teams.exe"],
              "keep_alive_audio_processes", ["Discord.exe", "teams.exe"]))
    for key, value, cfg_key, stored in cases:
        out = say(agent, "settings.set", {"key": key, "value": value})
        check("settings.set %s persists to config.json" % key,
              out[0]["type"] == "ack" and saved_config().get(cfg_key) == stored,
              (out, saved_config().get(cfg_key)))
    check("a settings event carries the new value",
          find(say(agent, "settings.set", {"key": "idleTimeout", "value": 30}),
               "settings")["data"]["idleTimeout"] == 30 and saved_config()["idle_timeout_seconds"] == 30)
    check("saving merges: other keys are untouched",
          saved_config()["obs_password"] == "keep-me" and saved_config()["toggle_hotkey"] == "f12"
          and saved_config()["obs_port"] == dead_port)
    before = saved_config()
    for key, value in (("idleTimeout", 0), ("idleTimeout", 3601), ("idleTimeout", True),
                       ("idleTimeout", "30"), ("replaySeconds", 9), ("replaySeconds", 301),
                       ("discardUnder", -1), ("launchCapture", "stream"),
                       ("keepAliveApps", "discord.exe"), ("keepAliveApps", ["C:/x/y.exe"]),
                       ("offload.auto", "yes"), ("gameListSync.provider", "dropbox")):
        out = say(agent, "settings.set", {"key": key, "value": value})
        check("out-of-bounds %s=%r is refused" % (key, value),
              out[0]["type"] == "error" and out[0]["data"]["code"] == "invalid", out)
    check("a refused value leaves config.json byte-for-byte alone", saved_config() == before)
    for key in ("hotkey", "obs_password", "recordingRoot", "appVersion", "remote.tailscale"):
        out = say(agent, "settings.set", {"key": key, "value": "x"})
        check("%s stays read-only" % key,
              out[0]["data"]["code"] == "readOnly" and saved_config() == before, out)
    out = say(agent, "settings.set", {"key": "offload.auto", "value": True})
    check("auto offload with no NAS root is refused, not faked",
          out[0]["data"]["code"] == "invalid" and "nas_offload_interval_hours" not in saved_config())
    say(agent, "settings.set", {"key": "gameListSync.provider", "value": "none"})
    check("sync provider none clears sync_folder", saved_config()["sync_folder"] == "")

    write(os.path.join(root, "config.json"), dict(saved_config(),
                                                   nas_offload_root="Z:/OBS Recordings"))
    agent = make(root, Foreground(), {"nas_offload_root": "Z:/OBS Recordings",
                                      "obs_port": dead_port, "obs_host": "127.0.0.1"})
    pair(agent)
    check("auto offload is on when a NAS root is set",
          agent.settings["offload"] == {"target": "OBS Recordings", "auto": True},
          agent.settings["offload"])
    say(agent, "settings.set", {"key": "offload.auto", "value": False})
    check("offload.auto false persists as manual-only",
          saved_config()["nas_offload_interval_hours"] == 0
          and agent.settings["offload"]["auto"] is False)
    say(agent, "settings.set", {"key": "offload.auto", "value": True})
    check("offload.auto true restores the desktop default interval",
          saved_config()["nas_offload_interval_hours"]
          == config_mod.DEFAULTS["nas_offload_interval_hours"])
    with open(os.path.join(root, "config.json"), "w") as fh:
        fh.write("{ not json")
    out = say(agent, "settings.set", {"key": "idleTimeout", "value": 50})
    check("an unreadable config.json is refused, not overwritten",
          out[0]["data"]["code"] == "unsaved"
          and open(os.path.join(root, "config.json")).read() == "{ not json")

# ====================================================================== playback
with tempfile.TemporaryDirectory() as root:
    rec = os.path.join(root, "recordings")
    os.makedirs(os.path.join(rec, "Hades"))
    body = bytes(range(256)) * 40
    clip_path = os.path.join(rec, "Hades", "run.mp4")
    with open(clip_path, "wb") as fh:
        fh.write(body)
    secret = os.path.join(root, "secret.txt")
    with open(secret, "wb") as fh:
        fh.write(b"not a recording")
    agent = make(root, Foreground(), {"obs_port": dead_port, "obs_host": "127.0.0.1"})
    snap = find(pair(agent), "snapshot")["data"]
    clip_id = snap["clips"][0]["id"]
    stop, port = serve_mock(agent)
    try:
        from websocket import create_connection
        held = create_connection("ws://127.0.0.1:%d/nebula" % port, timeout=5)
        held.send(json.dumps({"type": "hello", "id": "h", "data": {"deviceToken": MOCK_TOKEN}}))
        held.recv()

        def get(path, headers=None):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", path, headers=headers or {})
            reply = conn.getresponse()
            data = reply.read()
            out = (reply.status, dict(reply.getheaders()), data)
            conn.close()
            return out

        status, headers, data = get("/files/clip/" + clip_id)
        check("a clip streams in full while the socket is held",
              status == 200 and data == body and headers.get("Accept-Ranges") == "bytes"
              and headers.get("Content-Type") == "video/mp4", (status, headers))
        status, headers, data = get("/files/clip/" + clip_id, {"Range": "bytes=100-199"})
        check("a byte range answers 206 with Content-Range",
              status == 206 and data == body[100:200]
              and headers.get("Content-Range") == "bytes 100-199/%d" % len(body), (status, headers))
        status, headers, data = get("/files/clip/" + clip_id, {"Range": "bytes=%d-" % (len(body) - 10)})
        check("an open-ended range runs to the end", status == 206 and data == body[-10:])
        status, headers, data = get("/files/clip/" + clip_id, {"Range": "bytes=-16"})
        check("a suffix range is the last bytes", status == 206 and data == body[-16:])
        status, headers, data = get("/files/clip/" + clip_id, {"Range": "bytes=999999-"})
        check("a range past the end is 416",
              status == 416 and headers.get("Content-Range") == "bytes */%d" % len(body))
        check("a clip id with its extension still resolves",
              get("/files/clip/" + clip_id + ".mp4")[0] == 200)
        for path in ("/files/clip/clip-000000000000", "/files/clip/", "/files/clip",
                     "/files/clip/..%2Fsecret.txt", "/files/clip/../../secret.txt",
                     "/files/clip/clip-0123456789ab/../..", "/files/clip/run.mp4",
                     "/files/clip/Hades/run.mp4", "/files/clip/clip-%s" % ("g" * 12)):
            check("%s is a 404, never a file or a listing" % path, get(path)[0] == 404, path)
        check("the thumbnail route still answers beside it", get("/thumbs/clip-000000000000.jpg")[0] == 404)
        held.close()
    except Exception as exc:
        check("playback over the listener", False, repr(exc))
    finally:
        stop.set()

    # an id whose file has gone, and an escape through a symlink-free `..` rel
    row = {"rel": "../secret.txt", "name": "secret.txt", "game": "", "size": 15,
           "mtime": time.time()}
    agent._clip_cache = (time.time(), agent._clip_cache[1] + [row])
    check("a rel that climbs out of the root resolves to nothing",
          agent.clip_file(mobile_real._clip_id("../secret.txt")) is None
          and mobile_real._inside(rec, "../secret.txt") is None
          and mobile_real._inside(rec, "..\\secret.txt") is None
          and mobile_real._inside(rec, os.path.abspath(secret)) is None)
    check("the recording and its folder are untouched",
          open(clip_path, "rb").read() == body and sorted(os.listdir(rec)) == ["Hades"]
          and sorted(os.listdir(os.path.join(rec, "Hades"))) == ["run.mp4"])

# ====================================================================== ffprobe fields
class FakeDone:
    def __init__(self, text, code=0):
        self.stdout, self.returncode = text.encode(), code


def probe_with(payload, code=0):
    real_run, real_which = mobile_real.subprocess.run, mobile_real.shutil.which
    mobile_real.subprocess.run = lambda *a, **k: FakeDone(payload, code)
    mobile_real.shutil.which = lambda name: "ffprobe"
    try:
        return mobile_real._ffprobe("x.mkv")
    finally:
        mobile_real.subprocess.run, mobile_real.shutil.which = real_run, real_which


full = probe_with(json.dumps({
    "streams": [{"codec_name": "h264", "width": 2560, "height": 1440,
                 "avg_frame_rate": "60000/1001", "r_frame_rate": "60/1"}],
    "format": {"duration": "612.25"}}))
check("ffprobe fills resolution, fps, encoder and duration",
      full == {"duration": 612.25, "resolution": "2560x1440", "fps": 60, "encoder": "H.264"}, full)
sparse = probe_with(json.dumps({"streams": [{"codec_name": "hevc", "width": 1280,
                                              "avg_frame_rate": "0/0"}], "format": {}}))
check("what ffprobe does not return stays empty, never 1080p60",
      sparse == {"duration": None, "resolution": "", "fps": 0, "encoder": "HEVC"}, sparse)
check("a failed or unparseable probe is all-unknown",
      probe_with("", 1) == {"duration": None, "resolution": "", "fps": 0, "encoder": ""}
      and probe_with("not json") == {"duration": None, "resolution": "", "fps": 0, "encoder": ""}
      and probe_with(json.dumps({"streams": [], "format": {"duration": "0"}}))["duration"] is None)
check("r_frame_rate backs up an empty avg_frame_rate",
      probe_with(json.dumps({"streams": [{"avg_frame_rate": "0/0", "r_frame_rate": "30/1"}],
                             "format": {}}))["fps"] == 30)

with tempfile.TemporaryDirectory() as root:
    rec = os.path.join(root, "recordings", "Hades")
    os.makedirs(rec)
    path = os.path.join(rec, "tiny.mkv")
    with open(path, "wb") as fh:
        fh.write(b"x" * 2048)
    agent = make(root, Foreground(), {"obs_port": dead_port, "obs_host": "127.0.0.1"})
    row = find(pair(agent), "snapshot")["data"]["clips"][0]
    check("an unprobed clip has empty resolution, fps and encoder",
          (row["resolution"], row["fps"], row["encoder"]) == ("", 0, ""), row)
    agent._media[row["id"]] = {"duration": 61.5, "thumb": False, "resolution": "1920x1080",
                               "fps": 144, "encoder": "AV1"}
    row = agent._clip_row(agent._clip_cache[1][0], time.time())
    check("measured fields reach the clip row",
          (row["resolution"], row["fps"], row["encoder"], row["duration"])
          == ("1920x1080", 144, "AV1", 61.5), row)

# ====================================================================== non-games, storage, offload
with tempfile.TemporaryDirectory() as root:
    rec = os.path.join(root, "recordings", "Hades")
    os.makedirs(rec)
    path = os.path.join(rec, "a.mkv")
    other = os.path.join(rec, "b.mkv")
    for item in (path, other):
        with open(item, "wb") as fh:
            fh.write(b"x" * 2048)
    write(os.path.join(root, "games.json"), {
        "games": {}, "non_games": {"blender.exe": True, "Discord.EXE": True, "tool": True,
                                   ".exe": True}})
    cfg = {"obs_port": dead_port, "obs_host": "127.0.0.1"}
    agent = make(root, Foreground(), cfg)
    snap = find(pair(agent), "snapshot")["data"]
    names = {row["exe"]: row["displayName"] for row in snap["nonGames"]}
    check("non-game display names drop a trailing .exe, nothing prettier",
          names == {"blender.exe": "blender", "Discord.EXE": "Discord", "tool": "tool",
                    ".exe": ".exe"}, names)
    check("a non-game keeps its exe untouched", "blender.exe" in names)

    session = snap["session"]
    check("storage total sits beside free from the real disk",
          isinstance(session["storageTotalBytes"], int) and session["storageTotalBytes"] > 0
          and session["storageFreeBytes"] <= session["storageTotalBytes"], session)
    check("no history means no remaining-time estimate", session["estimatedRemaining"] is None)
    check("idle stays idle, with no scene and no live output",
          session["state"] == "idle" and session["scene"] == ""
          and session["output"] == {"resolution": "", "fps": 0, "encoder": ""}
          and session["game"] is None)
    check("the mock's scene name is not copied back", "Gameplay" not in json.dumps(snap))
    check("no clip is on the NAS or queued without data",
          all(c["locations"] == ["pc"] and c["offload"] == "none" for c in snap["clips"]))

    write(os.path.join(root, "offload_queue.json"),
          [{"path": path.replace("\\", "/"), "game": "Hades"}])
    agent.refresh(force=True)
    states = {c["file"]: (c["offload"], c["locations"]) for c in agent.clips}
    check("a clip in the real queue reads queued, still only on the PC",
          states["a.mkv"] == ("queued", ["pc"]) and states["b.mkv"] == ("none", ["pc"]), states)
    check("the idle card follows the queue state",
          agent.session["lastSession"]["offload"] in ("queued", "none"))

    now = time.time()
    rows = []
    for back in range(1, 5):
        start = now - back * 86400 - 7200
        rows.append({"ts": start, "type": "rec_start", "game": "Hades"})
        rows.append({"ts": start + 3600, "type": "rec_stop", "game": "Hades",
                     "duration": 3600, "size": 4 * 1024 ** 3, "path": "x"})
    with open(os.path.join(root, "sessions.jsonl"), "w", encoding="utf-8") as fh:
        for entry in rows:
            fh.write(json.dumps(entry) + "\n")
        fh.write("{ torn line")
    agent.refresh(force=True)
    estimate = agent.session["estimatedRemaining"]
    check("a ready forecast gives seconds remaining",
          isinstance(estimate, float) and estimate > 0, estimate)
    check("a history log does not invent a live recording",
          agent.session["state"] == "idle" and agent.session["game"] is None)
    short = rows[:4]
    with open(os.path.join(root, "sessions.jsonl"), "w", encoding="utf-8") as fh:
        for entry in short:
            fh.write(json.dumps(entry) + "\n")
    agent.refresh(force=True)
    check("under three days of history the estimate is null, not a guess",
          agent.session["estimatedRemaining"] is None)

source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "obsauto", "mobile_real.py"), encoding="utf-8").read()
check("mobile_real never removes or renames a file",
      not any(token in source for token in ("os.remove", "os.unlink", "shutil.rmtree",
                                            "shutil.move", "os.rename", "os.rmdir")))
check("a thumbnail spare file keeps a .jpg suffix ffmpeg will accept",
      ".part.jpg" in source and 'dest + ".part"' not in source)

passed_all = all(ok for _, ok, _ in results)
for name, ok, detail in results:
    print("%s  %-62s %s" % ("PASS" if ok else "FAIL", name, detail if not ok else ""))
print("\n%s (%d checks)" % ("ALL PASS" if passed_all else "FAILURES PRESENT", len(results)))
sys.exit(0 if passed_all else 1)
