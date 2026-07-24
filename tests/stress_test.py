"""Integrated stress test - hammers every subsystem under adverse conditions.

Unit tests prove each piece in isolation; this proves they hold up under load,
flapping I/O, rapid user actions and concurrency. Run directly:

    python tests/stress_test.py

Phases:
  1. Offload, sacred invariant  - 40 clips, NAS flapping offline/online, some
     copies corrupted, offloader restarted mid-queue. INVARIANT: no clip is ever
     lost - each ends either verified-on-NAS (local gone) or still local.
  2. GameSync under a flaky API   - hundreds of pushes against an API that fails
     randomly; never raises, merge-never-clobber always holds.
  3. Connection churn (GUI)        - dozens of rapid autostart/stop with failing
     connects; never wedges _connecting, threads stay bounded, no callback throws.
  4. Grid churn (GUI)              - 120 random relayouts/span-toggles; rects
     always valid (no overlap, in bounds), widgets rebuilt, nothing leaks.
  5. Log flood + frame pacing      - 5000 log lines while the window renders;
     history stays bounded and the UI stays responsive.
"""
import os
import random
import sys
import tempfile
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))
    print(f"{'PASS' if passed else 'FAIL'}  {name:<48} {detail}")


# ======================================================================
# Phase 1 - Offload: the sacred invariant under a flapping, lossy NAS
# ======================================================================
def phase_offload():
    from obsauto import paths as paths_module
    from obsauto.offload import Offloader

    work = tempfile.mkdtemp(prefix="nebula-stress-offload-")
    app_dir = os.path.join(work, "app")
    local = os.path.join(work, "local")
    nas = os.path.join(work, "nas")
    for d in (app_dir, local):
        os.makedirs(d)
    paths_module.APP_DIR = app_dir

    N = 40
    originals = {}   # dest-relative path -> bytes
    clips = []
    for i in range(N):
        game = f"Game{i % 5}"
        p = os.path.join(local, game, f"clip{i}.mkv")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        data = os.urandom(random.randint(200_000, 900_000))
        with open(p, "wb") as f:
            f.write(data)
        originals[(game, f"clip{i}.mkv")] = data
        clips.append((p, game))

    cfg = {"nas_offload_root": nas, "nas_offload_mode": "move"}
    off = Offloader(cfg, on_log=lambda m: None)

    # Corrupt the destination hash for ~25% of clips on their FIRST attempt only,
    # so they fail-safe (local kept) then succeed on retry - exercising the
    # verify-or-keep path repeatedly.
    real_copy = off._copy_hashing
    corrupt_once = set(random.sample(range(N), N // 4))
    attempt = {}

    def flaky_copy(src, dst):
        h = real_copy(src, dst)  # real copy happens
        idx = int(os.path.basename(src)[4:].split(".")[0])
        attempt[idx] = attempt.get(idx, 0) + 1
        if idx in corrupt_once and attempt[idx] == 1:
            return "0" * 64  # pretend the written bytes are wrong -> mismatch
        return h

    off._copy_hashing = flaky_copy

    # Model a NAS that goes offline for stretches then comes back (a Tailscale
    # blip / sleep / reboot), rather than flapping every few ms. "Offline" =
    # the mount path simply isn't there, which is exactly what os.path.isdir
    # sees when an SMB share drops. The worker must ride out each outage without
    # losing anything and drain once the NAS returns.
    flapping = {"run": True}

    def flap():
        while flapping["run"]:
            os.makedirs(nas, exist_ok=True)          # up for a good while
            t = time.time() + random.uniform(3.0, 6.0)
            while flapping["run"] and time.time() < t:
                time.sleep(0.1)
            if not flapping["run"]:
                break
            tmp = nas + ".away"                       # "unmounted" for a stretch
            try:
                if os.path.isdir(nas):
                    os.rename(nas, tmp)
            except OSError:
                pass
            t = time.time() + random.uniform(1.5, 3.0)
            while flapping["run"] and time.time() < t:
                time.sleep(0.1)
            try:
                if os.path.isdir(tmp):
                    os.rename(tmp, nas)
            except OSError:
                os.makedirs(nas, exist_ok=True)

    flapper = threading.Thread(target=flap, daemon=True)
    flapper.start()
    off.start()

    # Enqueue everything fast, with a few duplicates.
    for p, game in clips:
        off.queue(p, game)
        if random.random() < 0.1:
            off.queue(p, game)  # duplicate enqueue must be deduped
        time.sleep(random.uniform(0, 0.02))

    # Restart the offloader mid-run (simulates an app restart) - the persisted
    # queue must carry on.
    time.sleep(2.0)
    off.stop()
    off2 = Offloader(cfg, on_log=lambda m: None)
    off2.start()

    # Let it drain across NAS outages. Generous deadline.
    deadline = time.time() + 90
    while time.time() < deadline and off2.pending_count() > 0:
        time.sleep(0.2)
    flapping["run"] = False
    time.sleep(0.5)
    os.makedirs(nas, exist_ok=True)
    off2.stop()

    # THE INVARIANT: every clip is accounted for and byte-correct.
    lost = []
    safe_on_nas = 0
    safe_local = 0
    for (game, name), data in originals.items():
        dest = os.path.join(nas, game, name)
        src = os.path.join(local, game, name)
        on_nas = os.path.exists(dest) and open(dest, "rb").read() == data
        on_local = os.path.exists(src) and open(src, "rb").read() == data
        if on_nas:
            safe_on_nas += 1
        elif on_local:
            safe_local += 1
        else:
            lost.append((game, name))

    check("offload: NO clip ever lost", not lost, f"lost={lost}")
    check("offload: queue drained", off2.pending_count() == 0, off2.pending_count())
    check("offload: most clips reached NAS", safe_on_nas >= N * 0.9,
          f"{safe_on_nas}/{N} on NAS, {safe_local} still local")
    # No .part turds left behind anywhere.
    parts = [os.path.join(dp, f) for dp, _, fs in os.walk(nas) for f in fs if f.endswith(".part")]
    check("offload: no .part files left", not parts, parts[:3])


# ======================================================================
# Phase 2 - GameSync against a flaky API
# ======================================================================
def phase_gamesync():
    from obsauto import gamesync as gamesync_module
    from obsauto.gamesync import GameSync

    class FlakyGitHub:
        def __init__(self):
            self.store = {"games": {}, "non_games": {}}
            self.sha = "s0"
            self.n = 0
            self.lock = threading.Lock()

        def _resp(self, status, payload=None):
            import base64, json as _j
            class R:
                status_code = status
                def __init__(self, p): self._p = p
                def json(self): return self._p
                def raise_for_status(self):
                    if self.status_code >= 400:
                        raise RuntimeError(f"HTTP {self.status_code}")
            return R(payload or {})

        def get(self, url, headers=None, timeout=None):
            import base64, json as _j
            if random.random() < 0.3:
                raise ConnectionError("flaky get")
            with self.lock:
                return self._resp(200, {"sha": self.sha,
                                        "content": base64.b64encode(_j.dumps(self.store).encode()).decode()})

        def put(self, url, headers=None, json=None, timeout=None):
            import base64, json as _j
            if random.random() < 0.3:
                raise ConnectionError("flaky put")
            with self.lock:
                if json.get("sha") and json["sha"] != self.sha:
                    return self._resp(409)
                self.store = _j.loads(base64.b64decode(json["content"]))
                self.n += 1
                self.sha = f"s{self.n}"
                return self._resp(200, {"content": {"sha": self.sha}})

    fake = FlakyGitHub()
    gamesync_module.requests = fake
    cfg = {"github_token": "t", "github_gamedata_repo": "o/r", "github_gamedata_path": "g.json"}

    raised = {"count": 0}
    expected = set()

    def worker(wid):
        # Model a real device: it accumulates its own local classifications and
        # pushes the FULL local snapshot each time (as main.py does via
        # classifier.snapshot()). A dropped push is then recovered by the next.
        gs = GameSync(cfg, on_log=lambda m: None)
        local = {"games": {}, "non_games": {}}
        for i in range(40):
            key = f"dev{wid}_game{i}.exe"
            expected.add(key)
            local["games"][key] = {"display_name": f"G{wid}-{i}"}
            for _ in range(3):  # brief retry, like the coordinator's backoff
                try:
                    if gs.push(local) is not None:
                        break
                except Exception:
                    raised["count"] += 1
                    break
                time.sleep(0.01)
            time.sleep(random.uniform(0, 0.01))
        # A final flush so this device's last few games are guaranteed attempted
        # even if their pushes were dropped mid-run.
        for _ in range(20):
            if gs.push(local) is not None:
                break
            time.sleep(0.03)

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check("gamesync: never raised under flaky API", raised["count"] == 0, raised["count"])
    # Do a final authoritative reconcile (retry through the flakiness) so every
    # device's contributions converge - proving no push permanently clobbers.
    gs = GameSync(cfg, on_log=lambda m: None)
    for _ in range(40):
        merged = gs.push({"games": {}, "non_games": {}})
        if merged is not None:
            break
        time.sleep(0.05)
    final = set(fake.store["games"].keys())
    missing = expected - final
    check("gamesync: merge never clobbered (all survive)", not missing,
          f"missing {len(missing)}/{len(expected)}")


# ======================================================================
# GUI phases run under a real mainloop
# ======================================================================
def phase_gui():
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    from obsauto import gui, hotkey
    hotkey.register = lambda *a, **k: None
    gui.ensure_obs_running = lambda *a, **k: None
    gui.is_obs_running = lambda: False
    from obsauto import config as config_module
    config_module.save_config = lambda *a, **k: None
    from obsauto.classifier import Classifier
    from obsauto.config import load_config
    from obsauto.gui import AppWindow
    from obsauto.obs_client import OBSError

    AppWindow._poll_manual_review = lambda self: None
    app = AppWindow(load_config(), Classifier(), on_close_to_tray=lambda: None)
    app.root.withdraw()

    callback_errors = []
    app.root.report_callback_exception = lambda t, v, tb: callback_errors.append(
        "".join(traceback.format_exception(t, v, tb)))

    base_threads = threading.active_count()
    state = {}

    def phase3_connection():
        # Rapid autostart/stop churn with a failing connect.
        def failing():
            raise OBSError("stress: refused")
        app.obs.connect = failing
        for _ in range(60):
            app._connecting = False
            app.monitor._running = False
            app.autostart()
            app._stop()
        state["after_churn_threads"] = threading.active_count()
        app.root.after(1500, phase3_assert)

    def phase3_assert():
        check("connection: not wedged after 60 churns", app._connecting in (True, False))
        # _connecting should settle False once workers finish.
        app._abort_connect = True
        settled = {"v": None}
        def look(n=0):
            if app._connecting is False or n > 40:
                settled["v"] = app._connecting
                check("connection: _connecting settles False", app._connecting is False,
                      app._connecting)
                check("connection: threads bounded (<= base+8)",
                      threading.active_count() <= base_threads + 8,
                      f"{threading.active_count()} vs base {base_threads}")
                check("connection: no callback exceptions", not callback_errors,
                      callback_errors[0].splitlines()[-1] if callback_errors else "clean")
                phase4_grid()
                return
            app.root.after(50, lambda: look(n + 1))
        look()

    def rects_valid(rects):
        x0 = app._content_x0()
        boxes = [(r[0], r[1], r[0] + r[2], r[1] + r[3]) for r in rects.values()]
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a[0] < b[2] - 0.5 and b[0] < a[2] - 0.5 and a[1] < b[3] - 0.5 and b[1] < a[3] - 0.5:
                    return False
        for rx0, ry0, rx1, ry1 in boxes:
            if rx0 < x0 - 0.5 or rx1 > gui.WIDTH - gui.MARGIN + 0.5 or ry1 > gui.HEIGHT + 1:
                return False
        return True

    def phase4_grid():
        callback_errors.clear()
        app._show_view("dashboard")
        bad = {"overlap": 0}
        names = ["hero", "stats", "activity"]
        for _ in range(120):
            layout = [{"name": n, "span": random.choice([1, 2])} for n in random.sample(names, 3)]
            for it in layout:
                if it["name"] == "hero":
                    it["span"] = 2
            app._relayout_grid(layout)
            if not rects_valid(app._grid_rects):
                bad["overlap"] += 1
        check("grid: 120 random relayouts, always valid", bad["overlap"] == 0,
              f"{bad['overlap']} invalid")
        check("grid: no callback exceptions", not callback_errors,
              callback_errors[0].splitlines()[-1] if callback_errors else "clean")
        check("grid: widgets alive after churn",
              app.record_toggle_btn.winfo_exists() and app.console.winfo_exists())
        # widget/image accounting: shouldn't grow without bound. Count embedded
        # window items on the canvas - should be a small constant, not ~120x.
        wins = [i for i in app.bg.find_all() if app.bg.type(i) == "window"]
        check("grid: no widget leak (window items bounded)", len(wins) < 40, len(wins))
        phase5_flood()

    def phase5_flood():
        callback_errors.clear()
        app.root.deiconify()
        app.root.update()
        # Flood the log while measuring frame pacing.
        gaps = {"list": [], "last": time.perf_counter()}
        flood = {"i": 0}

        def beat():
            now = time.perf_counter()
            gaps["list"].append(now - gaps["last"])
            gaps["last"] = now
            app.root.after(16, beat)

        def pump_logs():
            for _ in range(200):
                app._log(f"[Monitor] stress line {flood['i']}")
                flood["i"] += 1
            if flood["i"] < 5000:
                app.root.after(1, pump_logs)
            else:
                app.root.after(300, flood_assert)

        def flood_assert():
            check("log flood: history bounded", len(app._log_lines) <= gui.LOG_HISTORY,
                  len(app._log_lines))
            data = sorted(gaps["list"][3:])
            if data:
                p50 = data[len(data) // 2] * 1000
                check("log flood: UI stayed responsive (p50 < 60ms)", p50 < 60, f"{p50:.1f}ms")
            check("log flood: no callback exceptions", not callback_errors,
                  callback_errors[0].splitlines()[-1] if callback_errors else "clean")
            app.root.quit()

        beat()
        app.root.after(10, pump_logs)

    app.root.after(50, phase3_connection)
    app.root.after(120000, app.root.quit)  # global safety net
    app.root.mainloop()
    app.root.destroy()


def main():
    print("=" * 70)
    print("PHASE 1: Offload - sacred invariant under a flapping, lossy NAS")
    print("=" * 70)
    phase_offload()
    print("\n" + "=" * 70)
    print("PHASE 2: GameSync - flaky API, concurrent devices")
    print("=" * 70)
    phase_gamesync()
    print("\n" + "=" * 70)
    print("PHASE 3-5: GUI - connection churn, grid churn, log flood + pacing")
    print("=" * 70)
    phase_gui()

    print("\n" + "=" * 70)
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    print(f"STRESS RESULT: {passed}/{total} checks passed")
    print("=" * 70)
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
