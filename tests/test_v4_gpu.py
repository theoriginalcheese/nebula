"""GPU page state, iGPU pin, toast sleep JS — no desktop session required.

    python tests/test_v4_gpu.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spike.webview_power import (
    apply_browser_arguments,
    gpu_page_state,
    pin_exe_gpu_preference,
    want_high_performance,
    window_on_screen,
)
from spike.host import claim_single_instance, release_single_instance
from spike import windows as nw_mod

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


def test_window_on_screen():
    check("tray hide stays off-screen", not window_on_screen(False, True, False))
    check("taskbar minimise is off-screen", not window_on_screen(True, True, True))
    check("shown and mapped is on-screen", window_on_screen(True, True, False))
    check("hidden hwnd is off-screen", not window_on_screen(True, False, False))


def test_mutex_second_claim_fails():
    name = "Nebula.TestMutex.v4gpu"
    release_single_instance()
    first = claim_single_instance(name)
    check("first claim wins", first)
    # A second CreateMutex on the same name from this process still sees
    # ERROR_ALREADY_EXISTS if we go through a fresh claim after clearing
    # the module handle — simulate a second process by closing then
    # claiming while a *copy* handle is held.
    from spike import host as host_mod
    held = host_mod._INSTANCE_MUTEX
    host_mod._INSTANCE_MUTEX = None
    second = claim_single_instance(name)
    check("second claim refused", second is False)
    host_mod._INSTANCE_MUTEX = held
    release_single_instance()
    check("release lets a new claim through", claim_single_instance(name))
    release_single_instance()


def test_gpu_page_state():
    hidden = gpu_page_state(False, False)
    check("hidden sleeps", hidden == {"awake": False, "quiet": False, "suspend": True}, hidden)
    hidden_fg = gpu_page_state(False, True)
    check("hidden ignores focus", hidden_fg["suspend"] and not hidden_fg["awake"], hidden_fg)
    vis = gpu_page_state(True, True)
    check("focused is fully awake", vis == {"awake": True, "quiet": False, "suspend": False}, vis)
    quiet = gpu_page_state(True, False)
    check("unfocused is quiet not suspended",
          quiet == {"awake": True, "quiet": True, "suspend": False}, quiet)


def test_browser_arguments(monkey_env):
    os.environ.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    os.environ.pop("NEBULA_GPU", None)
    got = apply_browser_arguments()
    check("default pins low-power GPU", "--force-low-power-gpu" in got, got)
    check("default caps iGPU heap", "--force-gpu-mem-available-mb=128" in got, got)
    check("default does not force dGPU", "--force-high-performance-gpu" not in got, got)
    # Idempotent
    again = apply_browser_arguments()
    check("args not doubled", again.count("--force-low-power-gpu") == 1, again)
    check("mem cap not doubled", again.count("--force-gpu-mem-available-mb=128") == 1, again)

    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = ""
    os.environ["NEBULA_GPU"] = "dgpu"
    got = apply_browser_arguments()
    check("NEBULA_GPU=dgpu is high-performance", "--force-high-performance-gpu" in got, got)
    os.environ.pop("NEBULA_GPU", None)
    os.environ.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)


def test_pin_preference_mocked():
    recorded = {}

    class FakeKey:
        def __init__(self):
            self.store = {}

    key = FakeKey()

    class FakeWinreg:
        HKEY_CURRENT_USER = object()
        REG_SZ = 1

        @staticmethod
        def CreateKey(_root, _path):
            return key

        @staticmethod
        def QueryValueEx(_key, name):
            if name not in key.store:
                raise FileNotFoundError(name)
            return key.store[name], 1

        @staticmethod
        def SetValueEx(_key, name, _res, _typ, value):
            recorded["name"] = name
            recorded["value"] = value
            key.store[name] = value

        @staticmethod
        def CloseKey(_key):
            pass

    old = sys.modules.get("winreg")
    sys.modules["winreg"] = FakeWinreg
    try:
        os.environ.pop("NEBULA_GPU", None)
        want = pin_exe_gpu_preference(high_performance=False)
        check("pin writes GpuPreference=1", want == "GpuPreference=1;" and recorded.get("value") == want,
              recorded)
        check("pin uses this exe path", recorded.get("name") and "msedgewebview2" not in recorded["name"].lower(),
              recorded.get("name"))
        check("high-performance is GpuPreference=2",
              pin_exe_gpu_preference(high_performance=True) == "GpuPreference=2;")
    finally:
        if old is None:
            sys.modules.pop("winreg", None)
        else:
            sys.modules["winreg"] = old


def test_want_high_performance():
    os.environ.pop("NEBULA_GPU", None)
    check("default is not dGPU", not want_high_performance())
    os.environ["NEBULA_GPU"] = "dgpu"
    check("dgpu env is high-performance", want_high_performance())
    os.environ.pop("NEBULA_GPU", None)


class FakeWindow:
    def __init__(self):
        self.js = []
        self.hidden = False
        self.shown = False
        self.destroyed = False

    def show(self):
        self.shown = True
        self.hidden = False

    def hide(self):
        self.hidden = True
        self.shown = False

    def evaluate_js(self, script):
        self.js.append(script)

    def destroy(self):
        self.destroyed = True


def test_toast_sleeps_when_hidden():
    created = []

    def fake_create(title, url, **kw):
        win = FakeWindow()
        created.append(win)
        return win

    old = nw_mod.webview.create_window
    nw_mod.webview.create_window = fake_create
    try:
        host = type("H", (), {"window": type("N", (), {"native": None})(),
                              "_log": lambda self, m: None})()
        # StubHost-shaped
        class Host:
            def __init__(self):
                self.window = type("N", (), {"native": None})()
                self.log = []

            def _log(self, msg):
                self.log.append(msg)

        host = Host()
        ctl = nw_mod.ToastController(host)
        ctl._ready.set()
        ctl.replace("start", "Game")
        win = created[0]
        time.sleep(0.08)
        ctl._on_expired()
        time.sleep(0.12)
        check("expire hides toast", win.hidden and not win.destroyed)
        check("expire asks page to sleep",
              any("setAsleep(true)" in j for j in win.js), win.js[-4:])
        ctl.replace("stop", "Game")
        time.sleep(0.12)
        check("reuse wakes toast page",
              any("setAsleep(false)" in j for j in win.js), win.js[-4:])
    finally:
        nw_mod.webview.create_window = old


def test_css_quiet_and_no_dust_will_change():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = open(os.path.join(root, "spike", "web", "app.css"), encoding="utf-8").read()
    check("quiet pauses aurora", ".quiet .aurora-sheet" in css)
    check("quiet does not hide chrome", ".quiet .tray" not in css)
    toast = open(os.path.join(root, "spike", "web", "toast.css"), encoding="utf-8").read()
    # Dust must not pin compositor tiles for the page lifetime.
    dust_block = toast.split(".toast-dust span")[1].split("}")[0]
    check("toast dust has no will-change", "will-change" not in dust_block, dust_block)
    js = open(os.path.join(root, "spike", "web", "app.js"), encoding="utf-8").read()
    check("stars baked to bitmap not box-shadow", "bakeStarLayer" in js and "boxShadow" not in js.split("function buildBackdrop")[1].split("function ensureSpots")[0])
    check("asleep drops backdrop GPU tiles", "function holdBackdropGpu" in js)
    check("boot load is not awaited", "if (!bootAsleep) load();" in js)
    check("load is single-flight", "let loadPromise = null;" in js)


if __name__ == "__main__":
    test_window_on_screen()
    test_mutex_second_claim_fails()
    test_gpu_page_state()
    test_browser_arguments({})
    test_pin_preference_mocked()
    test_want_high_performance()
    test_toast_sleeps_when_hidden()
    test_css_quiet_and_no_dust_will_change()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", ", ".join(FAIL))
        sys.exit(1)
    print("ALL PASS")
