"""Toast replace-in-place contract for v4 auxiliary windows (frame 2i).

Headless — mocks pywebview. No desktop session required.

    python tests/test_v4_windows.py
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spike import windows as nw_mod

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


class FakeWindow:
    _n = 0

    def __init__(self, title):
        FakeWindow._n += 1
        self.uid = "child_%d" % FakeWindow._n
        self.title = title
        self.shown = False
        self.destroyed = False
        self.js = []

    def show(self):
        self.shown = True

    def move(self, x, y):
        self.x, self.y = x, y

    def evaluate_js(self, script):
        self.js.append(script)

    def destroy(self):
        self.destroyed = True


class FakeNative:
    InvokeRequired = False

    def Invoke(self, fn):
        fn()


class FakeMaster:
    def __init__(self):
        self.native = FakeNative()


class StubHost:
    def __init__(self):
        self.window = FakeMaster()
        self.log = []

    def _log(self, msg):
        self.log.append(msg)


def with_fake_webview():
    created = []

    def fake_create(title, url, **kw):
        win = FakeWindow(title)
        created.append(win)
        return win

    return created, fake_create


def test_replace_one_slot():
    created, fake_create = with_fake_webview()
    old_create = nw_mod.webview.create_window
    nw_mod.webview.create_window = fake_create
    try:
        host = StubHost()
        ctl = nw_mod.ToastController(host)
        ctl._ready.set()

        ctl.replace("start", "Helldivers 2", {"duration": 90, "size": 1000})
        check("first replace creates one window", len(created) == 1, len(created))

        ctl.replace("pause", "Helldivers 2")
        check("second replace does not create another", len(created) == 1, len(created))
        check("second replace pushes JS", any("toastReplace" in j for j in created[0].js),
              created[0].js[-1:] if created[0].js else "")

        ctl.replace("stop", "Helldivers 2")
        check("third replace still one window", len(created) == 1)
    finally:
        nw_mod.webview.create_window = old_create


def test_pending_before_ready():
    created, fake_create = with_fake_webview()
    old_create = nw_mod.webview.create_window
    nw_mod.webview.create_window = fake_create
    try:
        host = StubHost()
        ctl = nw_mod.ToastController(host)
        ctl.replace("start", "Game A")
        check("create before ready", len(created) == 1)
        check("no JS before ready", len(created[0].js) == 0)

        ctl.replace("pause", "Game B")
        check("still one window", len(created) == 1)

        ctl._on_ready()
        check("ready drains pending via push", len(created[0].js) == 1)
        check("pushed latest sub", "Game B" in created[0].js[0])
    finally:
        nw_mod.webview.create_window = old_create


def test_gui_dispatch_from_worker():
    host = StubHost()
    host.window.native.InvokeRequired = True
    ran = []
    lock = threading.Lock()

    def fn():
        with lock:
            ran.append(threading.current_thread().name)

    nw_mod._run_on_gui(host, fn)
    check("Invoke path ran callback", len(ran) == 1)
    check("host window used for dispatch", host.window.native.InvokeRequired is True)


def test_string_details():
    content = nw_mod._toast_content("start", "Game", "1.2 GB")
    check("string details accepted", content["detail"] == "1.2 GB")


def test_expired_clears_slot():
    created, fake_create = with_fake_webview()
    old_create = nw_mod.webview.create_window
    nw_mod.webview.create_window = fake_create
    try:
        host = StubHost()
        ctl = nw_mod.ToastController(host)
        ctl._ready.set()
        ctl.replace("start", "Game")
        win = created[0]
        ctl._on_expired()
        # _on_expired is synchronous when InvokeRequired is False
        check("expired destroys window", win.destroyed)
        check("controller drops handle", ctl._window is None)
        check("ready cleared", not ctl._ready.is_set())

        ctl.replace("resume", "Game")
        check("after expiry next event rebuilds", len(created) == 2)
    finally:
        nw_mod.webview.create_window = old_create


def test_reclaim_orphans():
    """Foreign toast/overlay HWNDs get WM_CLOSE; same-PID windows are kept."""
    import ctypes

    posted = []
    destroyed = []
    keep_pid = os.getpid()
    orphan_pid = keep_pid + 99999
    fake_windows = [
        (101, "Nebula Toast", orphan_pid),
        (102, "Nebula Overlay", orphan_pid),
        (103, "Nebula Toast", keep_pid),
    ]
    old_iter = nw_mod._iter_auxiliary_windows
    old_post = ctypes.windll.user32.PostMessageW
    old_destroy = ctypes.windll.user32.DestroyWindow
    old_alive = nw_mod._pid_alive

    def fake_alive(pid):
        return pid in (keep_pid, orphan_pid)

    def fake_post(hwnd, msg, wparam, lparam):
        posted.append((int(hwnd), int(msg)))
        return 1

    def fake_destroy(hwnd):
        destroyed.append(int(hwnd))
        return 1

    nw_mod._iter_auxiliary_windows = lambda: list(fake_windows)
    nw_mod._pid_alive = fake_alive
    ctypes.windll.user32.PostMessageW = fake_post
    ctypes.windll.user32.DestroyWindow = fake_destroy
    try:
        result = nw_mod.reclaim_orphan_windows(keep_pid=keep_pid)
        closed_hwnds = [h for h, _, _ in result]
        check("reclaim closes orphan toast", 101 in closed_hwnds)
        check("reclaim closes orphan overlay", 102 in closed_hwnds)
        check("reclaim keeps own toast", 103 not in closed_hwnds)
        check("PostMessage WM_CLOSE sent", len(posted) == 2)
        check("WM_CLOSE opcode", all(msg == nw_mod.WM_CLOSE for _, msg in posted))
        check("DestroyWindow not used for live orphan", len(destroyed) == 0)
    finally:
        nw_mod._iter_auxiliary_windows = old_iter
        nw_mod._pid_alive = old_alive
        ctypes.windll.user32.PostMessageW = old_post
        ctypes.windll.user32.DestroyWindow = old_destroy


def test_reclaim_dead_pid():
    """Dead-owner orphans go straight to DestroyWindow."""
    import ctypes

    destroyed = []
    keep_pid = os.getpid()
    dead_pid = keep_pid + 88888
    old_iter = nw_mod._iter_auxiliary_windows
    old_destroy = ctypes.windll.user32.DestroyWindow
    old_alive = nw_mod._pid_alive

    nw_mod._iter_auxiliary_windows = lambda: [(201, "Nebula Toast", dead_pid)]
    nw_mod._pid_alive = lambda pid: pid == keep_pid

    def fake_destroy(hwnd):
        destroyed.append(int(hwnd))
        return 1

    ctypes.windll.user32.DestroyWindow = fake_destroy
    try:
        result = nw_mod.reclaim_orphan_windows(keep_pid=keep_pid)
        check("dead pid orphan reclaimed", result == [(201, "Nebula Toast", dead_pid)])
        check("DestroyWindow used", destroyed == [201])
    finally:
        nw_mod._iter_auxiliary_windows = old_iter
        nw_mod._pid_alive = old_alive
        ctypes.windll.user32.DestroyWindow = old_destroy


def test_liveness_teardown():
    host = StubHost()
    windows = nw_mod.NebulaWindows.__new__(nw_mod.NebulaWindows)
    windows._host = host
    windows._teardown_lock = threading.Lock()
    windows._teardown_done = False
    windows.toast = nw_mod.ToastController(host)
    windows.overlay = nw_mod.OverlayController(host, {})
    created, fake_create = with_fake_webview()
    old_create = nw_mod.webview.create_window
    nw_mod.webview.create_window = fake_create
    try:
        windows.toast._ready.set()
        windows.toast.replace("start", "Game")
        toast_win = created[0]
        host._quitting = True
        check("host marked quitting", not nw_mod._host_process_alive(host, os.getpid()))
        windows._teardown_without_host()
        check("liveness destroys toast", toast_win.destroyed)
        check("liveness clears toast handle", windows.toast._window is None)
        check("teardown idempotent", windows._teardown_done)
        windows._teardown_without_host()
        check("second teardown is noop", windows.toast._window is None)
    finally:
        nw_mod.webview.create_window = old_create


if __name__ == "__main__":
    test_replace_one_slot()
    test_pending_before_ready()
    test_gui_dispatch_from_worker()
    test_string_details()
    test_expired_clears_slot()
    test_reclaim_orphans()
    test_reclaim_dead_pid()
    test_liveness_teardown()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
    print("ALL PASS")
