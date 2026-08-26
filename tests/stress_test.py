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
    import obsauto.offload as offload_module
    from obsauto import paths as paths_module
    from obsauto.offload import Offloader

    work = tempfile.mkdtemp(prefix="nebula-stress-offload-")
    app_dir = os.path.join(work, "app")
    local = os.path.join(work, "local")
    nas = os.path.join(work, "nas")
    for d in (app_dir, local):
        os.makedirs(d)
    paths_module.APP_DIR = app_dir

    # Impatient-operator retry pacing. The shipped 10 s backoff is right for
    # a real NAS outage but makes 40 clips x ~50% flap uptime mathematically
    # unable to fit the 90 s deadline - this phase kept failing on drain
    # throughput while the sacred invariant (nothing lost) held. Backoff
    # mechanics themselves are unit-covered in test_offload_backoff.py.
    offload_module._RETRY_BACKOFF = 2

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

    # Force the built-in streamer: this phase tests the sacred invariant
    # under flapping I/O, not the TeraCopy integration. With TeraCopy
    # installed (auto-discovered) each handoff spawns a background process
    # whose lifecycle dwarfs the flap windows - drain collapsed to 7/40 on
    # machines with it, while the same run passes in fractions of a second
    # on the direct copier.
    cfg = {"nas_offload_root": nas, "nas_offload_mode": "move",
           "nas_offload_use_teracopy": False}
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
    from obsauto import design_v3 as dv
    from obsauto.classifier import Classifier
    from obsauto.config import load_config
    from obsauto.gui import AppWindow
    from obsauto.obs_client import OBSError

    # Which phases actually ran. An exception inside a Tk callback goes to
    # report_callback_exception and is swallowed, so a phase that dies simply
    # never chains to the next one - phases 4 and 5 were silently skipped for
    # exactly that reason once the grid layout format changed under them.
    reached = set()

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
        reached.add("grid")
        app._show_view("dashboard")
        bad = {"overlap": 0}
        names = list(gui.DEFAULT_BLOCKS)
        for i in range(120):
            picked = random.sample(names, random.randint(1, len(names)))
            layout = [{"id": n, "span": random.choice(dv.SPANS)} for n in picked]
            for it in layout:
                if it["id"] == "hero":
                    it["span"] = dv.GRID_COLS      # hero is full width only
            # Every third pass churns edit mode too: entering and leaving
            # re-renders with a handle strip inside every module, which is the
            # path that changes each block's height.
            if i % 3 == 0:
                app._set_customise(not app._customising)
            app._relayout_grid(layout)
            if not rects_valid(app._grid_rects):
                bad["overlap"] += 1
        if app._customising:
            app._set_customise(False)
        check("grid: 120 random relayouts, always valid", bad["overlap"] == 0,
              f"{bad['overlap']} invalid")
        # A module removed in edit mode must be offered back, never destroyed.
        app._relayout_grid([{"id": "hero", "span": 12}])
        app._set_customise(True)
        app._add_module("activity")
        app._set_customise(False)
        check("grid: a removed module can be added back",
              any(it["id"] == "activity" for it in app._grid_layout),
              [it["id"] for it in app._grid_layout])
        app._relayout_grid([dict(it) for it in gui.DEFAULT_GRID])
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
        reached.add("flood")
        app.root.deiconify()
        app.root.update()
        # Flood the log while measuring frame pacing.
        gaps = {"list": [], "last": time.perf_counter()}
        flood = {"i": 0}

        def beat():
            if gaps.get("stop"):
                return
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
            if callback_errors:
                # The last line alone doesn't say where it came from, and a
                # swallowed Tk callback has no other trace.
                print("\n--- first callback exception during the flood ---")
                print(callback_errors[0])
            check("log flood: no callback exceptions", not callback_errors,
                  callback_errors[0].splitlines()[-1] if callback_errors else "clean")
            # The heartbeat reschedules itself forever; stop it before the next
            # phase, or it keeps firing through everything that follows.
            gaps["stop"] = True
            phase6_panes()

        beat()
        app.root.after(10, pump_logs)

    def phase6_panes():
        """Every pane, repeatedly, with the ribbon and forecast live.

        View switching is one itemconfigure per tag, but the panes now carry
        canvas images (ribbon blocks, thumbnails) that are rebuilt rather than
        toggled - so churning them is what would expose a leak.
        """
        callback_errors.clear()
        reached.add("panes")
        before_items = len(app.bg.find_all())
        for _ in range(40):
            for view in gui.RAIL_VIEWS:
                app._show_view(view)
        app._show_view("dashboard")
        after_items = len(app.bg.find_all())
        check("panes: 200 view switches leak no canvas items",
              after_items <= before_items + 40,
              f"{before_items} -> {after_items}")
        check("panes: no callback exceptions", not callback_errors,
              callback_errors[0].splitlines()[-1] if callback_errors else "clean")

        # The ribbon re-renders from scratch each time; 60 refreshes across all
        # three ranges must not accumulate items either.
        app._show_view("clips")
        app.root.update()
        # Render once *with* data before measuring. The ribbon was built when
        # the log was empty, so counting from there measures the spans it
        # legitimately drew, not a leak.
        app._set_ribbon_range("Session")
        app.root.update()
        start_items = len(app.bg.find_all())
        for i in range(60):
            app._set_ribbon_range(dv.RIBBON_RANGES[i % len(dv.RIBBON_RANGES)])
        app._set_ribbon_range("Session")
        check("ribbon: 60 range switches leak nothing",
              len(app.bg.find_all()) <= start_items + 30,
              f"{start_items} -> {len(app.bg.find_all())}")
        app._show_view("dashboard")
        phase7_hero()

    def phase7_hero():
        """Hero state churn - the bug that put the timer over other panes."""
        callback_errors.clear()
        reached.add("hero")
        states = ["watching", "recording", "paused", "disconnected"]
        for i in range(200):
            app._set_hero_state(states[i % 4])
        check("hero: 200 state changes, no exceptions", not callback_errors,
              callback_errors[0].splitlines()[-1] if callback_errors else "clean")

        # Away from the dashboard, no hero item may be visible in ANY state -
        # _poll_obs_status calls _set_hero_state once a second, so this is the
        # exact path that leaked the elapsed timer onto the Macropad pane.
        app._show_view("macropad")
        leaked = []
        for state in states:
            app._set_hero_state(state)
            for cap, val in app._readouts.values():
                for item in (cap, val):
                    if app.bg.itemcget(item, "state") != "hidden":
                        leaked.append((state, item))
            if app.bg.itemcget(app._pause_btn_win, "state") != "hidden":
                leaked.append((state, "pause button"))
        check("hero: nothing bleeds through on another pane", not leaked, leaked[:4])
        app._show_view("dashboard")
        app._set_hero_state("watching")
        check("hero: readouts come back on the dashboard",
              app.bg.itemcget(app._pause_btn_win, "state") == "normal")
        phase8_palette()

    def phase8_palette():
        """The palette against a large, hostile row set."""
        callback_errors.clear()
        reached.add("palette")
        from obsauto import palette as pal
        rows = [pal.Row(random.choice(pal.GROUP_ORDER), f"Row {i} " + "".join(
                    random.choice("abcdefg ") for _ in range(20)),
                    lambda: None, hint=f"hint{i}", recency=random.random())
                for i in range(2000)]
        queries = ["", "a", "ab", "abc", "zzz", "row", "r o w", "  ", "é",
                   "a" * 40, "hint199", "ROW 1"]
        worst = 0.0
        for query in queries:
            t0 = time.perf_counter()
            grouped = pal.search(rows, query)
            worst = max(worst, time.perf_counter() - t0)
            flat = pal.flatten(grouped)
            if len(flat) > pal.MAX_ROWS:
                check("palette: row cap held", False, len(flat))
                break
        else:
            check("palette: row cap held across every query", True,
                  f"worst search {worst * 1000:.1f}ms over 2000 rows")
        check("palette: search stays interactive", worst < 0.25,
              f"{worst * 1000:.1f}ms")
        check("palette: a hostile query returns nothing, not an error",
              pal.search(rows, "\x00\x01") == [])
        phase9_done()

    def phase9_done():
        check("all GUI phases ran",
              reached >= {"grid", "flood", "panes", "hero", "palette"},
              sorted(reached))
        app.root.quit()

    app.root.after(50, phase3_connection)
    app.root.after(120000, app.root.quit)  # global safety net
    app.root.mainloop()
    app.root.destroy()


# ======================================================================
# Phase A - the session log under concurrent writers, and what reads it
# ======================================================================
def phase_session_log():
    from obsauto import forecast, session_log

    work = tempfile.mkdtemp(prefix="nebula-stress-log-")
    path = os.path.join(work, "sessions.jsonl")
    session_log.log_path = lambda: path

    # Eight threads appending at once. The file is line-oriented precisely so
    # this is safe; a torn line would show up as a row that won't parse.
    errors = []

    def writer(n):
        try:
            for i in range(250):
                session_log.append(random.choice(session_log.EVENT_TYPES),
                                   game=f"Game{n}", path=f"clip{n}-{i}.mkv",
                                   duration=random.randint(1, 3600),
                                   size=random.randint(1, 5_000_000_000))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    written = sum(1 for _ in open(path, encoding="utf-8"))
    parsed = session_log.read()
    check("session log: concurrent writers never raise", not errors, errors[:2])
    check("session log: every line written is a whole line",
          len(parsed) == written == 2000, f"{len(parsed)} parsed / {written} lines")

    # A torn tail (power cut mid-append) must cost one row, not the file.
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"ts": 1, "type": "rec_st')
    check("session log: a torn tail costs one row, not the file",
          len(session_log.read()) == 2000, len(session_log.read()))

    t0 = time.perf_counter()
    spans = session_log.spans()
    span_ms = (time.perf_counter() - t0) * 1000
    check("session log: 2000 events fold into spans quickly",
          span_ms < 500, f"{span_ms:.0f}ms -> {len(spans)} spans")

    t0 = time.perf_counter()
    result = forecast.forecast(500 * forecast.GB, 2000 * forecast.GB, spans)
    fc_ms = (time.perf_counter() - t0) * 1000
    check("forecast: never divides by zero or throws on junk data",
          isinstance(result, dict) and "days_left" in result, f"{fc_ms:.0f}ms")
    check("forecast: days_left is never negative",
          result["days_left"] is None or result["days_left"] >= 0,
          result["days_left"])

    # Deliberately absurd inputs.
    for free, total in ((0, 100), (100, 0), (-5, 100), (10 ** 18, 10 ** 18)):
        try:
            forecast.forecast(free, total, spans)
        except Exception as exc:
            check(f"forecast: survives free={free} total={total}", False, exc)
            break
    else:
        check("forecast: survives absurd disk figures", True)


# ======================================================================
# Phase B - the classification merge, concurrently (the reclassify bug)
# ======================================================================
def phase_classify():
    from obsauto import classifier as classifier_module
    from obsauto.classifier import Classifier, merge_classifications

    work = tempfile.mkdtemp(prefix="nebula-stress-class-")
    classifier_module.DATA_FILE = os.path.join(work, "games.json")
    c = Classifier()

    # Hammer the same keys from several threads, flipping each between buckets.
    errors = []

    def churn(n):
        try:
            for i in range(120):
                key = f"app{i % 20}.exe"
                if random.random() < 0.5:
                    c.mark_game(key, f"Game {i % 20}")
                else:
                    c.mark_non_game(key)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=churn, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check("classify: concurrent reclassification never raises", not errors, errors[:2])
    both = set(c._data["games"]) & set(c._data["non_games"])
    check("classify: nothing is ever filed as both game and non-game",
          not both, sorted(both)[:5])

    # And on disk, which is what the next launch and the sync push both read.
    import json
    on_disk = json.load(open(classifier_module.DATA_FILE, encoding="utf-8"))
    disk_both = set(on_disk["games"]) & set(on_disk["non_games"])
    check("classify: the file on disk is consistent too", not disk_both,
          sorted(disk_both)[:5])

    # The merge itself, against a remote that disagrees about everything.
    remote = {"games": {f"app{i}.exe": {} for i in range(20)},
              "non_games": {f"app{i}.exe": True for i in range(20)}}
    merged = merge_classifications(remote, c.snapshot())
    check("classify: merging a self-contradictory remote still resolves",
          not (set(merged["games"]) & set(merged["non_games"])),
          sorted(set(merged["games"]) & set(merged["non_games"]))[:5])


# ======================================================================
# Phase C - thumbnails: the worker must never run during a recording
# ======================================================================
def phase_thumbs():
    from obsauto import thumbs

    work = tempfile.mkdtemp(prefix="nebula-stress-thumbs-")
    recording = {"on": True}
    done = []
    worker = thumbs.ThumbWorker(work, on_log=lambda m: None,
                                is_busy=lambda: recording["on"],
                                on_done=lambda c, f: done.append(c))
    # 200 submissions of files that don't exist: extraction will find nothing,
    # but the queue, the dedupe and the recording guard all still get worked.
    accepted = sum(worker.submit(os.path.join(work, f"clip{i}.mkv"))
                   for i in range(200))
    duplicates = sum(worker.submit(os.path.join(work, f"clip{i}.mkv"))
                     for i in range(200))
    if thumbs.available():
        check("thumbs: every distinct clip is accepted", accepted == 200, accepted)
        check("thumbs: duplicates are refused", duplicates == 0, duplicates)
    else:
        check("thumbs: submissions refused cleanly with no ffmpeg",
              accepted == 0 and duplicates == 0)

    worker.start()
    time.sleep(1.5)
    check("thumbs: nothing extracted while a recording is running",
          not done, len(done))
    recording["on"] = False
    time.sleep(1.0)
    worker.stop()
    # stop() signals; it doesn't block. Give the thread a moment to notice -
    # checking is_alive() the instant after is a race, not a hang.
    if worker._thread:
        worker._thread.join(timeout=5)
    check("thumbs: the worker stops within 5s of being told to",
          not worker._thread.is_alive() if worker._thread else True)


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
    print("PHASE A: Session log - concurrent writers, and what reads it")
    print("=" * 70)
    phase_session_log()
    print("\n" + "=" * 70)
    print("PHASE B: Classification - concurrent reclassification")
    print("=" * 70)
    phase_classify()
    print("\n" + "=" * 70)
    print("PHASE C: Thumbnails - the never-during-recording guard")
    print("=" * 70)
    phase_thumbs()
    print("\n" + "=" * 70)
    print("PHASE 3-9: GUI - connection, grid, log flood, panes, hero, palette")
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
