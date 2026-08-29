"""Phone-agent contract guard: honest nulls, auth, scrubbing, read-only.

    python tests/test_phone_agent.py

The agent is the only surface that leaves the studio PC, so the things worth
pinning are not its happy path but its refusals. Each block below maps to a
rule in `docs/PHONE-AGENT.md`:

  * a faulted `Api.snapshot()` section must project as null, never as a
    plausible zero - the phone renders null as an em-dash, and "0 Mb/s" would
    be a lie the UI cannot distinguish from a real reading;
  * a footage path must never leave the process, even if the desktop starts
    putting one in a label;
  * an unset or wrong token refuses, and an empty token refuses everything
    rather than degrading to open;
  * the agent refuses to bind at all when Tailscale has no address, because
    the fallback would be a socket on the home LAN;
  * only GET /v1/* exists - there is no mutating route to find.
"""
import json
import os
import sys
import threading
from http.server import HTTPServer
from urllib import error, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto import phone_agent as pa

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


# ---------------------------------------------------------------- projection

# No activity source in these cases - the feed is tested on its own below.
NO_EVENTS = lambda limit=None: []

empty = pa.project({}, 1000.0, activity_reader=NO_EVENTS)

check("empty snapshot still yields a versioned payload",
      empty["v"] == pa.PAYLOAD_VERSION and empty["at"] == 1000000,
      "v=%s at=%s" % (empty["v"], empty["at"]))

# Python speaks epoch seconds, JavaScript's Date takes milliseconds. Handing
# seconds over put every timestamp in January 1970 while still rendering as a
# plausible clock time, so it survived inspection. Pin the unit.
check("timestamps leave as milliseconds, not seconds",
      pa._epoch_ms(1787992441.846) == 1787992441846, pa._epoch_ms(1787992441.846))
check("a missing timestamp stays null rather than becoming 1970",
      pa._epoch_ms(None) is None and pa._epoch_ms("") is None, "null")

check("no snapshot means idle, not a fabricated session",
      empty["recording"]["status"] == "idle",
      empty["recording"]["status"])

null_fields = [k for k, v in empty["recording"].items()
               if k not in ("status", "diskWarning") and v is not None]
check("every unknown recording readout is null", not null_fields,
      "non-null: %s" % null_fields)

check("unknown disk state is not a warning",
      empty["recording"]["diskWarning"] is False,
      empty["recording"]["diskWarning"])

check("empty lists rather than invented rows",
      empty["activity"] == [] and empty["clips"] == []
      and empty["peers"] == [] and empty["detectedGames"] == [],
      "activity=%d clips=%d peers=%d games=%d" % (
          len(empty["activity"]), len(empty["clips"]),
          len(empty["peers"]), len(empty["detectedGames"])))

check("no offload job is null, not a zero-progress job",
      empty["offload"] is None, empty["offload"])

# `_remote` emits {enabled, text} only — no progress source exists, so a
# disabled job is null and an enabled one carries words, not a fake fraction.
check("a disabled offloader is null",
      pa.project({"remote": {"offload": {"enabled": False, "text": ""}}},
                 1.0)["offload"] is None, "null")
_run = pa.project({"remote": {"offload": {"enabled": True,
                                          "text": "3 clips queued"}}}, 1.0)["offload"]
check("an enabled offloader reports its note with no invented progress",
      _run and _run["note"] == "3 clips queued"
      and _run["total"] is None and _run["done"] is None,
      _run)

check("unknown pairing is null, never assumed true",
      empty["moonlightPaired"] is None, empty["moonlightPaired"])

check("unknown non-games count is null, not zero",
      empty["notGamesCount"] is None, empty["notGamesCount"])

# The desktop uses "" for unknown. That must not survive as a rendered value.
blank = pa.project({"hero": {"state": "recording", "size": "", "bitrate": "  ",
                             "title": "Helldivers II", "elapsed": "01:12:33"}},
                   1000.0, activity_reader=NO_EVENTS)
check("desktop's empty-string idiom becomes null",
      blank["recording"]["fileSizeLabel"] is None
      and blank["recording"]["bitrateLabel"] is None,
      "size=%r rate=%r" % (blank["recording"]["fileSizeLabel"],
                           blank["recording"]["bitrateLabel"]))

check("a real title survives projection",
      blank["recording"]["gameTitle"] == "Helldivers II",
      blank["recording"]["gameTitle"])

check("elapsed clock parses to seconds",
      blank["recording"]["elapsedSec"] == 4353,
      blank["recording"]["elapsedSec"])

check("a non-clock elapsed is null, not zero",
      pa._elapsed_seconds("just now") is None
      and pa._elapsed_seconds("") is None,
      "%r / %r" % (pa._elapsed_seconds("just now"), pa._elapsed_seconds("")))

# Readouts belong to a live session only.
stopped = pa.project({"hero": {"state": "saved", "size": "8.42 GB",
                               "title": "Helldivers II"}}, 1000.0,
                     activity_reader=NO_EVENTS)
check("stopped sessions do not keep reporting a live file size",
      stopped["recording"]["status"] == "stopped"
      and stopped["recording"]["fileSizeLabel"] is None,
      "%s / %r" % (stopped["recording"]["status"],
                   stopped["recording"]["fileSizeLabel"]))

# ------------------------------------------------------------------ scrubbing

for path in ("Z:\\OBS\\Helldivers II\\2026-08-07.mkv",
             "D:/OBS TEMP/clip.mkv",
             "Z:\\OBS-recovered\\thing.mkv"):
    check("footage path is recognised: %s" % path,
          pa.looks_like_footage_path(path), path)

check("an ordinary label is not mistaken for a path",
      not pa.looks_like_footage_path("Helldivers II")
      and not pa.looks_like_footage_path("3.10 GB · on NAS"),
      "clean")

leaky = pa.project({
    "clips_panel": {"clips": [
        {"name": "Z:\\OBS\\Helldivers II\\2026-08-07.mkv", "game": "Helldivers II"},
        {"name": "2026-08-07 19-33-41", "game": "Helldivers II",
         "size_label": "7.20 GB", "state": "on-nas"},
    ]},
}, 1000.0)
check("a clip whose title is a footage path is dropped entirely",
      len(leaky["clips"]) == 1, "kept %d" % len(leaky["clips"]))
check("...and the well-formed clip beside it survives",
      leaky["clips"] and leaky["clips"][0]["title"] == "2026-08-07 19-33-41",
      leaky["clips"][0]["title"] if leaky["clips"] else "none")

serialised = repr(leaky)
check("no footage path appears anywhere in the payload",
      not pa.looks_like_footage_path(serialised), "scrubbed")

check("an unrecognised clip state falls back to local, not to on-nas",
      pa.project({"clips_panel": {"clips": [{"name": "x", "state": "weird"}]}},
                 1.0, activity_reader=NO_EVENTS)["clips"][0]["state"] == "local",
      pa.project({"clips_panel": {"clips": [{"name": "x", "state": "weird"}]}},
                 1.0, activity_reader=NO_EVENTS)["clips"][0]["state"])

# ------------------------------------------------------------------ activity

# The desktop's own `activity` pane is a debug log with clock-string stamps;
# the phone's feed comes from session_log instead.
events = [
    {"ts": 1787992406.8, "type": "rec_start", "game": "Helldivers II"},
    {"ts": 1787992441.5, "type": "rec_stop", "game": "Helldivers II"},
    {"ts": 1787992500.0, "type": "idle_in", "game": "unknown"},
    {"ts": 1787992600.0, "type": "wat", "game": "x"},
]
feed = pa._activity(reader=lambda limit=None: events)
check("activity is newest-first", [r["label"] for r in feed][0].startswith("Paused"),
      [r["label"] for r in feed])
check("rec_start reads as the design's line",
      "Recording started, Helldivers II" in [r["label"] for r in feed],
      [r["label"] for r in feed])
check("timestamps are real epoch milliseconds, not clock strings",
      all(isinstance(r["at"], int) and r["at"] > 1_600_000_000_000 for r in feed),
      [r["at"] for r in feed])
check("the detector's 'unknown' placeholder is not shown as a title",
      not any("unknown" in r["label"].lower() for r in feed),
      [r["label"] for r in feed])
check("an unrecognised event type is dropped, not guessed at",
      len(feed) == 3, len(feed))
check("recording events are tagged as such",
      [r["kind"] for r in feed].count("recording") == 2,
      [r["kind"] for r in feed])
check("an unreadable session log yields no activity, never raises",
      pa._activity(reader=lambda limit=None: (_ for _ in ()).throw(IOError("x"))) == [],
      "empty")

# ------------------------------------------------- disk warning derivation

# `_forecast` in spike/app.py returns only {label, rate, used_pct} - there is
# no boolean - so the warning is read out of the label vocabulary.
for label, expected in [("4 days left", True), ("7 days left", True),
                        ("8 days left", False), ("1 day left", True),
                        ("3 hours left", True), ("60+ days left", False),
                        ("", False), ("drive unavailable", False),
                        ("Not enough history", False), (None, False)]:
    check("disk warning for %r is %s" % (label, expected),
          pa.disk_warning(label) is expected, pa.disk_warning(label))

warned = pa.project({"forecast": {"label": "4 days left"}}, 1.0, activity_reader=NO_EVENTS)
check("a low forecast surfaces as diskWarning on the phone",
      warned["recording"]["diskWarning"] is True
      and warned["recording"]["diskLeftLabel"] == "4 days left",
      warned["recording"]["diskLeftLabel"])

# ------------------------------------------------------ real desktop shapes

# These key names are the ones spike/app.py actually emits. Guessing them wrong
# silently nulls a field, which looks like honest-empty rather than a bug.
real_clips = pa.project({"clips_panel": {"clips": [
    {"rel": "Helldivers II/2026-08-07.mkv", "name": "2026-08-07 19-33-41.mkv",
     "title": "2026-08-07 19-33-41", "game": "Helldivers II",
     "size_label": "7.20 GB", "location": "remote", "mtime": 1787000000.0},
    {"rel": "Factorio/x.mkv", "title": "x", "game": "Factorio",
     "size_label": "184 MB", "location": "local"},
]}}, 1.0, activity_reader=NO_EVENTS)["clips"]
check("clip title prefers the extension-less form",
      real_clips[0]["title"] == "2026-08-07 19-33-41", real_clips[0]["title"])
check("location=remote maps to on-nas",
      real_clips[0]["state"] == "on-nas", real_clips[0]["state"])
check("a local clip is not claimed to be on the NAS",
      real_clips[1]["state"] == "local", real_clips[1]["state"])
check("clip id is an opaque hash, not the catalogue path",
      len(real_clips[0]["id"]) == 16 and "/" not in real_clips[0]["id"],
      real_clips[0]["id"])
check("...and is stable across projections",
      real_clips[0]["id"] == pa._stable_id("Helldivers II/2026-08-07.mkv", 0),
      real_clips[0]["id"])
check("size label projects from size_label",
      real_clips[0]["sizeLabel"] == "7.20 GB", real_clips[0]["sizeLabel"])

real_games = pa.project({"games": {"games": [
    {"name": "Helldivers II", "exes": ["helldivers2.exe"], "meta": "553850"},
    {"name": "Factorio", "exes": ["factorio.exe"]},
], "non_games": [{"name": "cursor.exe"}]}}, 1.0, activity_reader=NO_EVENTS)
check("game exe comes from the exes list, not a singular key",
      real_games["detectedGames"][0]["exe"] == "helldivers2.exe",
      real_games["detectedGames"][0]["exe"])
check("classified games are all recorded - membership is the decision",
      all(g["recording"] for g in real_games["detectedGames"]), "all true")
check("non-games are counted, not listed",
      real_games["notGamesCount"] == 1, real_games["notGamesCount"])

# --------------------------------------------------------------------- peers

peered = pa.project({"remote": {"tailscale": {"peers": [
    {"name": "nas-vault", "online": True, "status": "direct"},
    {"name": "work-laptop", "online": False},
]}}}, 1000.0, activity_reader=NO_EVENTS)
check("peers project from the nested tailscale section",
      [p["name"] for p in peered["peers"]] == ["nas-vault", "work-laptop"],
      [p["name"] for p in peered["peers"]])
check("ping is null when the desktop does not measure it",
      all(p["pingMs"] is None for p in peered["peers"]), "null")
check("offline peers keep their offline flag",
      peered["peers"][1]["online"] is False, peered["peers"][1]["online"])

# ---------------------------------------------------------------------- auth


class _Cfg(dict):
    pass


def agent_with(**cfg):
    return pa.PhoneAgent(api=None, config=_Cfg(cfg), clock=lambda: 1000.0)

live = agent_with(phone_agent_enabled=True, phone_agent_token="s3cret")
check("correct bearer token is accepted",
      live.authorised("Bearer s3cret"), "ok")
check("wrong token is refused",
      not live.authorised("Bearer wrong"), "refused")
check("missing header is refused",
      not live.authorised(None) and not live.authorised(""), "refused")
check("non-bearer scheme is refused",
      not live.authorised("Basic s3cret"), "refused")

open_agent = agent_with(phone_agent_enabled=True, phone_agent_token="")
check("an unset token refuses everything rather than running open",
      not open_agent.authorised("Bearer ") and not open_agent.authorised(None),
      "refused")
check("...and such an agent refuses to start at all",
      open_agent.start() is None, "refused")

check("the agent is off unless explicitly enabled",
      not agent_with(phone_agent_token="s3cret").enabled
      and agent_with(phone_agent_token="s3cret").start() is None,
      "off")

check("default port is used when unset",
      live.port == pa.DEFAULT_PORT, live.port)

# ----------------------------------------------------------------- bind rules


class _NoTailscale:
    @staticmethod
    def status():
        return None


sys.modules["obsauto.tailscale"], _real_ts = _NoTailscale, sys.modules.get("obsauto.tailscale")
try:
    check("no tailnet address means refuse to bind, never 0.0.0.0",
          live.bind_host() is None and live.start() is None, "refused")
finally:
    if _real_ts is not None:
        sys.modules["obsauto.tailscale"] = _real_ts
    else:
        sys.modules.pop("obsauto.tailscale", None)

# --------------------------------------------------------------- read-only


class _FaultyApi:
    @staticmethod
    def snapshot():
        raise RuntimeError("obs went away")


faulty = pa.PhoneAgent(api=_FaultyApi, config=_Cfg(), clock=lambda: 1000.0)
payload = faulty.snapshot()
check("a snapshot fault degrades to an honest empty payload, never raises",
      payload["recording"]["status"] == "idle" and payload["clips"] == [],
      payload["recording"]["status"])

source = open(pa.__file__, encoding="utf-8").read()
check("the module defines no write verbs",
      "def do_POST" not in source and "def do_PUT" not in source
      and "def do_DELETE" not in source and "def do_PATCH" not in source,
      "GET only")

check("no delete/move call exists anywhere in the module",
      not any(tok in source for tok in ("os.remove", "os.unlink", "shutil.move",
                                        "shutil.rmtree", "os.rmdir")),
      "clean")

# --------------------------------------------------- contract key agreement

# mobile/state/agent.ts reads exactly these names. Renaming one on either side
# without the other silently drops a field to null, which the phone would then
# render as an honest-looking em-dash - a lie that is hard to spot. Pin them.
EXPECTED_TOP = {
    "v", "at", "connection", "recording", "activity", "clips", "moonlight",
    "moonlightPaired", "peers", "offload", "detectedGames", "notGamesCount",
    "classifyQueue",
}
EXPECTED_RECORDING = {
    "status", "encoder", "gameTitle", "sceneName", "elapsedSec",
    "fileSizeLabel", "bitrateLabel", "diskLeftLabel", "diskWarning",
}
check("payload top-level keys match the documented contract",
      set(empty) == EXPECTED_TOP,
      "extra=%s missing=%s" % (set(empty) - EXPECTED_TOP, EXPECTED_TOP - set(empty)))
check("recording keys match the documented contract",
      set(empty["recording"]) == EXPECTED_RECORDING,
      "extra=%s missing=%s" % (set(empty["recording"]) - EXPECTED_RECORDING,
                               EXPECTED_RECORDING - set(empty["recording"])))

check("the whole payload is JSON-serialisable",
      bool(json.dumps(empty)), "ok")

# ------------------------------------------------------------- HTTP end-to-end

served = pa.PhoneAgent(api=_FaultyApi, config=_Cfg(phone_agent_token="s3cret"),
                       clock=lambda: 1000.0)
httpd = HTTPServer(("127.0.0.1", 0), pa._make_handler(served))
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % httpd.server_address[1]


def get(path, token="s3cret"):
    req = request.Request(base + path)
    if token is not None:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


try:
    code, body = get("/v1/health")
    check("GET /v1/health with a good token returns 200",
          code == 200 and body.get("ok") is True, "%s %s" % (code, body))

    code, body = get("/v1/snapshot")
    check("GET /v1/snapshot returns the versioned payload",
          code == 200 and body.get("v") == pa.PAYLOAD_VERSION, "%s" % code)

    code, _ = get("/v1/snapshot", token="wrong")
    check("a wrong token is rejected over the wire", code == 401, code)

    code, _ = get("/v1/snapshot", token=None)
    check("a missing header is rejected over the wire", code == 401, code)

    code, _ = get("/v1/nope")
    check("an unknown path 404s rather than leaking anything", code == 404, code)

    # Read-only: there is no write route to reach, authorised or not.
    req = request.Request(base + "/v1/snapshot", data=b"{}", method="POST")
    req.add_header("Authorization", "Bearer s3cret")
    try:
        with request.urlopen(req, timeout=5) as resp:
            post_code = resp.status
    except error.HTTPError as exc:
        post_code = exc.code
    except Exception:
        post_code = "refused"
    check("POST is not implemented anywhere on the surface",
          post_code in (405, 501, "refused"), post_code)

    # The phone app is served from a different port, so its fetch is
    # cross-origin and the browser preflights before sending the token.
    req = request.Request(base + "/v1/snapshot", method="OPTIONS")
    with request.urlopen(req, timeout=5) as resp:
        pre_code, pre_hdrs = resp.status, dict(resp.headers)
    check("CORS preflight succeeds without a token", pre_code == 204, pre_code)
    check("preflight allows the Authorization header",
          "authorization" in (pre_hdrs.get("Access-Control-Allow-Headers") or "").lower(),
          pre_hdrs.get("Access-Control-Allow-Headers"))
    check("preflight advertises GET only, never a write verb",
          "POST" not in (pre_hdrs.get("Access-Control-Allow-Methods") or ""),
          pre_hdrs.get("Access-Control-Allow-Methods"))

    _, _ = get("/v1/health")
    req = request.Request(base + "/v1/health")
    req.add_header("Authorization", "Bearer s3cret")
    with request.urlopen(req, timeout=5) as resp:
        check("real responses carry the CORS origin header",
              resp.headers.get("Access-Control-Allow-Origin") == "*",
              resp.headers.get("Access-Control-Allow-Origin"))
finally:
    httpd.shutdown()
    httpd.server_close()

# ------------------------------------------------------- headless disk source

# obsauto/phone_state.py is what makes the phone work after a reboot with
# nobody logged in: no Api, no OBS, no desktop session. It must emit the same
# shape project() already consumes, and it must never touch a video file.
from obsauto import phone_state as ps

fake_cfg = {"recording_root": "", "sync_folder": "", "nas_offload_root": ""}
disk = ps.DiskSnapshot(root=os.path.join(os.path.dirname(__file__), "__missing__"),
                       config=fake_cfg, clock=lambda: 2000.0)
raw = disk.snapshot()
check("disk snapshot emits the Api.snapshot() section names",
      {"hero", "forecast", "clips_panel", "games", "remote"} <= set(raw),
      sorted(raw))

projected = pa.project(raw, 2000.0, activity_reader=NO_EVENTS)
check("...and projects without special-casing",
      projected["v"] == pa.PAYLOAD_VERSION and projected["clips"] == [],
      projected["v"])
check("a missing recordings root is not a crash and not a fake reading",
      projected["recording"]["diskLeftLabel"] in (None, "drive unavailable"),
      projected["recording"]["diskLeftLabel"])

# A live span is the whole recording test - no OBS connection involved.
live = disk._hero([{"game": "Sifu", "start": 1000.0, "end": None,
                    "live": True, "size": 8_000_000, "marks": []}])
check("a span with no rec_stop reads as recording",
      live["state"] == "recording" and live["title"] == "Sifu", live)
check("elapsed is derived from the span start",
      live["elapsed"] == "00:16:40", live["elapsed"])
check("OBS-only facts stay empty rather than being guessed",
      live["scene"] == "" and live["video"] == "" and live["bitrate"] == "",
      live)
check("a closed span is not reported as recording",
      disk._hero([{"game": "Sifu", "start": 1000.0, "end": 1500.0,
                   "live": False, "marks": []}])["state"] != "recording",
      "not recording")

check("clip formatting matches the desktop's readouts",
      ps._format_bytes(64000) == "62.5 KB" and ps._format_bytes(4_500_000_000) == "4.2 GB",
      "%s / %s" % (ps._format_bytes(64000), ps._format_bytes(4_500_000_000)))

# The sacred-footage rule, enforced at the source rather than only downstream.
disk_src = open(ps.__file__, encoding="utf-8").read()
check("the disk source never opens, moves or deletes a recording",
      not any(tok in disk_src for tok in ("os.remove", "os.unlink", "shutil.move",
                                          "shutil.rmtree", "os.rename", "os.rmdir")),
      "clean")
check("clip discovery is metadata only - scandir/stat, never a file read",
      "os.scandir" in disk_src and "os.walk" not in disk_src, "scandir only")

check("games are read from the richest source, not the first readable one",
      len(ps.DiskSnapshot(config={"sync_folder": "", "nas_offload_root": ""})
          .games_sources()) >= 1, "candidates")

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<62} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} ({len(results)} checks)")
sys.exit(0 if passed_all else 1)
