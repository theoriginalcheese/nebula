"""Bugs found by trying to break the data paths, then fixed.

    python tests/test_hunt_fixes.py
"""
import json
import os
import socket
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.atomic_json import read_json, write_json_atomic
from obsauto.classifier import merge_classifications
from obsauto.clip_catalog import ClipCatalog
from obsauto.gamesync import NasGameSync
from obsauto.monitor import Monitor
from obsauto.replay import ReplayBuffer
from obsauto import classifier as classifier_mod
from obsauto import monitor as monitor_mod
from obsauto import paths as paths_mod
from obsauto import recycle
from obsauto import session_log
from obsauto.offload import Offloader
from spike.host import NebulaHost

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def test_locked_json_is_not_empty():
    work = tempfile.mkdtemp(prefix="nebula-hunt-json-")
    target = os.path.join(work, "state.json")
    write_json_atomic(target, ["a", "b"])
    blocked = os.path.join(work, "blocked")
    os.mkdir(blocked)
    raised = False
    try:
        read_json(blocked, [])
    except OSError:
        raised = True
    check("unreadable state file is not returned as empty", raised)
    check("the real file is untouched", read_json(target, None) == ["a", "b"])

    original = paths_mod.APP_DIR
    paths_mod.APP_DIR = work
    try:
        off = Offloader({})
        off._queue_file = blocked
        off._queue = [{"path": "keep.mkv"}]
        off._load_queue()
        check("a locked queue is not saved away", off._queue == [{"path": "keep.mkv"}])
        check("the unreadable queue path is still not a file", os.path.isdir(blocked))
        real = os.path.join(work, "offload_queue.json")
        write_json_atomic(real, [{"path": "already.mkv", "game": "G"}])
        off._queue_file = real
        off._queue_loaded = False
        off._queue = [{"path": "only-the-new-one.mkv"}]
        off._save_queue()
        check("a save after a failed read does not replace the queue",
              read_json(real, None) == [{"path": "already.mkv", "game": "G"}])
    finally:
        paths_mod.APP_DIR = original


def test_double_filed_key_survives_merge():
    merged = merge_classifications(
        {"games": {}, "non_games": {}},
        {"games": {"starrail.exe": {"display_name": "Star Rail"}},
         "non_games": {"starrail.exe": True}},
    )
    check("double-filed overlay keeps the game",
          "starrail.exe" in merged["games"], merged)
    check("double-filed overlay drops the non-game copy",
          "starrail.exe" not in merged["non_games"], merged)

    work = tempfile.mkdtemp(prefix="nebula-hunt-clf-")
    data_file = os.path.join(work, "games.json")
    previous = classifier_mod.DATA_FILE
    classifier_mod.DATA_FILE = data_file
    try:
        clf = classifier_mod.Classifier(on_log=lambda _m: None,
                                        on_saved=lambda _d: None)
        added = clf.absorb({
            "games": {"starrail.exe": {"display_name": "Star Rail"}},
            "non_games": {"starrail.exe": True},
        })
        on_disk = json.load(open(data_file, encoding="utf-8"))
        check("absorb reports the new game", added == 1, added)
        check("absorb keeps it in games",
              "starrail.exe" in clf._data["games"]
              and "starrail.exe" not in clf._data["non_games"])
        check("the saved list still has it",
              "starrail.exe" in on_disk["games"]
              and "starrail.exe" not in on_disk.get("non_games", {}))
    finally:
        classifier_mod.DATA_FILE = previous


def test_nas_bad_shape_is_not_emptied():
    root = tempfile.mkdtemp(prefix="nebula-hunt-nas-")
    path = os.path.join(root, ".nebula", "games.json")
    os.makedirs(os.path.dirname(path))
    original = {"games": ["not-a-dict"], "non_games": {"b.exe": True}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(original, fh)
    nas = NasGameSync({"nas_offload_root": root, "games_sync_nas": True},
                      on_log=lambda _m: None)
    check("a malformed NAS list is refused", nas.fetch() is None)
    pushed = nas.push({"games": {"a.exe": {"display_name": "A"}}, "non_games": {}})
    with open(path, encoding="utf-8") as fh:
        after = json.load(fh)
    check("push does not overwrite the malformed list",
          pushed is None and after == original, after)


def test_replay_stays_inside_the_root():
    root = tempfile.mkdtemp(prefix="nebula-hunt-replay-")
    buf = ReplayBuffer(object(), {
        "recording_root": root,
        "replay_subfolder": "Replays",
    })
    buf.set_game("..")
    landed = os.path.abspath(buf.target_dir())
    check("a '..' game cannot leave the recording root",
          os.path.commonpath([os.path.abspath(root), landed]) == os.path.abspath(root),
          landed)
    buf.set_game("Honkai: Star Rail")
    name = os.path.basename(os.path.dirname(buf.target_dir()))
    check("a colon in the game name stays one folder",
          ":" not in name and name.startswith("Honkai"), name)
    buf.config["replay_subfolder"] = r"C:\tmp"
    escaped = os.path.abspath(buf.target_dir())
    check("the replay subfolder cannot be an absolute path",
          os.path.commonpath([os.path.abspath(root), escaped]) == os.path.abspath(root),
          escaped)
    buf.config["recording_root"] = ""
    check("no recording root means the replay is not filed",
          buf.target_dir() is None)


def test_replay_does_not_close_the_recording():
    rows = [
        {"type": "rec_start", "ts": 0, "game": "Game"},
        {"type": "rec_stop", "ts": 600, "game": "Game", "replay": True,
         "duration": 30, "path": "replay.mkv", "size": 10},
        {"type": "rec_stop", "ts": 3600, "game": "Game", "duration": 3600,
         "path": "full.mkv", "size": 100},
    ]
    spans = session_log.spans(rows, now=4000)
    check("one recording produces one span", len(spans) == 1, spans)
    check("the span ends at the real stop",
          spans and spans[0]["end"] == 3600 and spans[0]["path"] == "full.mkv",
          spans)

    work = tempfile.mkdtemp(prefix="nebula-hunt-sessions-")
    previous = session_log.APP_DIR
    session_log.APP_DIR = work
    try:
        session_log.append("rec_start", game="Game")
        session_log.append("rec_stop", game="Game", path="replay.mkv",
                           duration=30, replay=True, size=10)
        live = session_log.today()
        check("a replay during a recording does not become the whole tile",
              live["clips"] == 1 and live["recorded_seconds"] < 15, live)
        session_log.append("rec_stop", game="Game", path="full.mkv",
                           duration=100, size=50)
        done = session_log.today()
        check("the recording's own duration is what gets counted",
              abs(done["recorded_seconds"] - 100) < 1 and done["clips"] == 2, done)
    finally:
        session_log.APP_DIR = previous


def test_clip_index_keeps_other_writers():
    app = tempfile.mkdtemp(prefix="nebula-hunt-clips-")
    cat = ClipCatalog({}, app_dir=app, on_log=lambda _m: None)
    cat.record_offload(
        r"D:\local\clip.mkv", r"Z:\G\clip.mkv",
        game="G", sha256="11", size=1, mtime=1)
    cat.record_offload(
        r"D:\local\clip.mkv", r"Z:\G\clip (2).mkv",
        game="G", sha256="22", size=1, mtime=1)
    rels = {e["rel"] for e in cat.list_entries()}
    check("renamed NAS copies keep both index keys",
          rels == {"G/clip.mkv", "G/clip (2).mkv"}, rels)

    other = ClipCatalog({}, app_dir=app, on_log=lambda _m: None)
    other.upsert(game="G", name="from-app.mkv", sha256="33", size=1, mtime=1)
    again = ClipCatalog({}, app_dir=app, on_log=lambda _m: None)
    names = {e["name"] for e in again.list_entries()}
    check("a second catalog does not drop the offloader's entries",
          names == {"clip.mkv", "clip (2).mkv", "from-app.mkv"}, names)

    bad = tempfile.mkdtemp(prefix="nebula-hunt-badindex-")
    index = os.path.join(bad, "clip_index.json")
    os.mkdir(index)
    broken = ClipCatalog({}, app_dir=bad, on_log=lambda _m: None)
    broken.upsert(game="G", name="new.mkv", sha256="44", size=1, mtime=1)
    check("an unreadable index is not overwritten", os.path.isdir(index))


def test_reconnect_keeps_a_live_recording():
    monitor_mod.ensure_obs_running = lambda *a, **k: False

    class Obs:
        def __init__(self):
            self.connected = False
            self.active = True

        def connect(self):
            self.connected = True

        def get_record_status(self):
            return {"outputActive": self.active}

    obs = Obs()
    mon = Monitor(obs, None, {"reconnect_interval_seconds": 0, "obs_path": ""},
                  on_log=lambda _m: None)
    target = (1, "game.exe", "Game", "D:/Game")
    mon._recording_target = target
    mon._maybe_reconnect()
    check("disconnect does not forget the target", mon._recording_target == target)
    mon._maybe_reconnect()
    check("reconnect keeps the target while OBS is still recording",
          mon._recording_target == target)

    obs.connected = False
    obs.active = False
    mon._was_disconnected = False
    mon._recording_target = target
    mon._maybe_reconnect()
    mon._maybe_reconnect()
    check("reconnect clears the target when OBS is not recording",
          mon._recording_target is None)

    obs.connected = False
    obs.active = False
    mon._was_disconnected = False
    mon._recording_target = target

    def flaky():
        flaky.calls += 1
        if flaky.calls == 1:
            raise RuntimeError("not ready")
        return {"outputActive": False}

    flaky.calls = 0
    obs.get_record_status = flaky
    mon._maybe_reconnect()
    mon._maybe_reconnect()
    check("a failed status check does not drop the target yet",
          mon._recording_target == target)
    mon._maybe_reconnect()
    check("the next status check clears it once OBS is idle",
          mon._recording_target is None)


def test_udp_rebind_closes_the_old_socket():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    class Keys:
        def bind(self, *_a, **_k):
            return True

        def defer(self, *_a, **_k):
            return None

    host = NebulaHost({"replay_udp_port": port, "palette_hotkey": "",
                       "toggle_hotkey": "", "replay_hotkey": ""})
    host.hotkeys = Keys()
    host.monitor = None
    host.replay = None
    try:
        host.start_hotkeys()
        first = host._udp_trigger
        check("udp trigger bound", first is not None and first._sock is not None)
        host.start_hotkeys()
        second = host._udp_trigger
        check("rebind replaced the trigger", second is not first)
        check("the new socket is listening", second._sock is not None)
        again = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            again.bind(("127.0.0.1", port))
            bound_twice = False
        except OSError:
            bound_twice = True
        finally:
            again.close()
        check("the port is held once", bound_twice)
    finally:
        trigger = getattr(host, "_udp_trigger", None)
        if trigger is not None:
            trigger.stop()


def test_obs_endpoint_reaches_the_client():
    host = NebulaHost({"obs_host": "localhost", "obs_port": 4455,
                       "obs_password": ""})

    class Obs:
        def __init__(self):
            self.host = "localhost"
            self.port = 4455
            self.password = ""
            self.disconnected = False

        def disconnect(self):
            self.disconnected = True

    host.obs = Obs()
    host.config["obs_host"] = "127.0.0.1"
    host.config["obs_port"] = 4460
    host.config["obs_password"] = "secret"
    queued = []
    host.call_soon = lambda fn: queued.append(fn)
    host.apply_obs_endpoint()
    check("the client takes the saved port", host.obs.port == 4460, host.obs.port)
    check("the client takes the saved host and password",
          host.obs.host == "127.0.0.1" and host.obs.password == "secret")
    check("the old connection is dropped", host.obs.disconnected)
    check("a reconnect is queued and not run here", len(queued) == 1)

    class Running:
        _running = True

    host.monitor = Running()
    host.obs.disconnected = False
    queued.clear()
    host.apply_obs_endpoint()
    check("a running monitor reconnects itself",
          host.obs.disconnected and not queued)
    host._monitoring_paused = True
    host.monitor = None
    host.obs.disconnected = False
    host.apply_obs_endpoint()
    check("a paused monitor is not resumed by a port change",
          host.obs.disconnected and not queued)


def test_removable_volume_is_not_recyclable():
    if recycle.win32file is None:
        check("removable check skipped (no pywin32)", True)
        return
    real = recycle.win32file.GetDriveType
    recycle.win32file.GetDriveType = lambda _drive: recycle.win32file.DRIVE_REMOVABLE
    try:
        check("a removable drive is not recyclable",
              recycle.recyclable(r"E:\clips\a.mkv") is False)
    finally:
        recycle.win32file.GetDriveType = real


def main():
    test_locked_json_is_not_empty()
    test_double_filed_key_survives_merge()
    test_nas_bad_shape_is_not_emptied()
    test_replay_stays_inside_the_root()
    test_replay_does_not_close_the_recording()
    test_clip_index_keeps_other_writers()
    test_reconnect_keeps_a_live_recording()
    test_udp_rebind_closes_the_old_socket()
    test_obs_endpoint_reaches_the_client()
    test_removable_volume_is_not_recyclable()
    passed_all = all(ok for _name, ok, _detail in results)
    for name, ok, detail in results:
        print("%s  %-58s %s" % ("PASS" if ok else "FAIL", name, detail))
    print("\n%s (%d checks)" % (
        "ALL PASS" if passed_all else "FAILURES PRESENT", len(results)))
    return 0 if passed_all else 1


if __name__ == "__main__":
    sys.exit(main())
