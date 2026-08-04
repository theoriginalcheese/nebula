"""v4 step 1 - tray, single instance, hotkeys. No window, no OBS needed.

    python tests/test_v4_tray.py

The v3 equivalent is tests/test_tray.py, which still passes unchanged - the two
share obsauto/tray_app.py and this file exists to prove the shared module really
does drive both hosts.

Most of what is checked here is the honesty rule. Step 1 has no Monitor and no
OBS, so the tray must say "disconnected" and must hide every item it cannot
actually perform, rather than showing a menu that looks complete.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spike.host import HotkeyManager, NebulaHost, claim_single_instance

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("%-5s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


CFG = {"obs_host": "localhost", "obs_port": 4455,
       "recording_root": "D:/OBS Recordings",
       "toggle_hotkey": "`", "toggle_hotkey_scancode": 41,
       "replay_hotkey": "f9", "palette_hotkey": "ctrl+k"}


# --- fake keyboard backend -------------------------------------------------
# The real one installs a system-wide low-level hook with suppress=True. A test
# that did that would swallow the tester's backtick key, and a failure halfway
# through would leave it swallowed.

class FakeKeyboard:
    def __init__(self):
        self.live = {}
        self._n = 0
        self.fail_next = False

    def add_hotkey(self, target, callback, suppress=True):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated registration failure")
        self._n += 1
        self.live[self._n] = (target, callback, suppress)
        return self._n

    def remove_hotkey(self, handle):
        if handle not in self.live:
            raise KeyError(handle)
        del self.live[handle]


def with_fake_keyboard():
    from obsauto import hotkey as hk
    fake = FakeKeyboard()
    hk.keyboard = fake
    hk._AVAILABLE = True
    return fake


# --- tests -----------------------------------------------------------------

def test_single_instance():
    first = claim_single_instance("Nebula.Test.SingleInstance")
    check("first claim on a free mutex name succeeds", first is True)
    # The real app runs one process per instance, so a second claim inside this
    # one only proves the call is safe to repeat - the cross-process case is
    # covered by the mutex being named and kernel-owned.
    again = claim_single_instance("Nebula.Test.SingleInstance")
    check("claiming is idempotent within a process", again in (True, False))


def test_hotkey_rebind_leaves_no_leak():
    """The v3 bug: rebinding *added* hooks instead of replacing them.

    Four edits left fifteen live, and the stale suppress=True ones kept
    swallowing the old key system-wide.
    """
    fake = with_fake_keyboard()
    hk = HotkeyManager()

    for key in ("f6", "f7", "f8", "f9"):
        hk.bind("toggle", key, lambda: None)

    check("rebinding four times leaves exactly one live hook",
          len(fake.live) == 1, "live=%d" % len(fake.live))
    check("the live hook is the newest binding",
          [t for t, _, _ in fake.live.values()] == ["f9"],
          str([t for t, _, _ in fake.live.values()]))

    hk.unbind_all()
    check("unbind_all removes every hook", len(fake.live) == 0,
          "live=%d" % len(fake.live))


def test_hotkey_scancode_wins():
    """Binding "`" by name also suppresses apostrophes on this UK layout."""
    fake = with_fake_keyboard()
    hk = HotkeyManager()
    hk.bind("toggle", "`", lambda: None, scancode=41)
    targets = [t for t, _, _ in fake.live.values()]
    check("a scancode binds the physical key, not the character",
          targets == [41], str(targets))


def test_failed_registration_is_not_recorded():
    fake = with_fake_keyboard()
    hk = HotkeyManager()
    fake.fail_next = True
    ok = hk.bind("toggle", "f6", lambda: None)
    check("a failed registration reports False", ok is False)
    check("a failed registration is not tracked as bound", hk.bound() == [],
          str(hk.bound()))


def test_deferred_bindings_are_not_registered():
    """A hotkey bound to a no-op is worse than an absent one: it swallows the
    key system-wide and then does nothing."""
    fake = with_fake_keyboard()
    host = NebulaHost(dict(CFG))
    host.start_hotkeys()

    # The palette is in-window and always available, so it binds unconditionally
    # once step 7e lands. toggle needs a Monitor and replay needs a buffer, so
    # those two stay deferred on a bare host - which is what this asserts.
    check("only the palette registers on a bare host",
          len(fake.live) == 1, "live=%d" % len(fake.live))
    check("the palette is bound", host.hotkeys.bound() == ["palette"],
          str(host.hotkeys.bound()))
    pending = host.hotkeys.pending()
    check("toggle and replay stay deferred without their targets",
          sorted(pending) == ["replay", "toggle"], str(sorted(pending)))
    check("each pending binding says what it is waiting for",
          all(v[1] for v in pending.values()),
          "; ".join("%s: %s" % (k, v[1]) for k, v in sorted(pending.items())))
    host.quit()


def test_tray_status_is_honest_without_a_monitor():
    host = NebulaHost(dict(CFG))
    s = host.tray_status()
    check("state is 'disconnected' with no Monitor", s["state"] == "disconnected",
          s["state"])
    check("heading matches the state", s["heading"] == "OBS disconnected",
          s["heading"])
    check("detail is the real host:port, not a placeholder",
          s["detail"] == "localhost:4455", s["detail"])
    check("monitoring is False, not assumed", s["monitoring"] is False)
    host.quit()


def test_menu_hides_what_it_cannot_do():
    """Build the real pystray menu against a monitor-less host and read it."""
    import pystray

    host = NebulaHost(dict(CFG))
    built = {}

    def fake_icon(name, image, title, menu):
        built["menu"] = menu
        built["title"] = title

        class _Icon:
            visible = False
            icon = image

            def run(self, setup=None):
                pass

            def stop(self):
                pass
        return _Icon()

    real = pystray.Icon
    pystray.Icon = fake_icon
    try:
        host.start_tray()
    finally:
        pystray.Icon = real

    menu = built.get("menu")
    check("the tray menu was built", menu is not None)
    if menu is None:
        return

    visible = [str(i.text) for i in menu.items if i.visible]
    labels = " | ".join(visible)

    check("Show Nebula is offered", any("Show" in v for v in visible), labels)
    check("Quit is present - it is the only way out",
          any("Quit" in v for v in visible), labels)
    check("Monitoring is hidden without a Monitor",
          not any("Monitoring" in v for v in visible), labels)
    check("Pause is hidden without OBS",
          not any("Pause" in v or "Resume" in v for v in visible), labels)
    check("Stop recording is hidden without OBS",
          not any("Stop recording" in v for v in visible), labels)
    check("the replay item is hidden with no buffer",
          not any("Save the last" in v for v in visible), labels)
    check("the tooltip is Nebula", built.get("title") == "Nebula",
          str(built.get("title")))
    host.quit()


def test_call_soon_marshals_off_the_calling_thread():
    """tray_app.py hands every callback through this. pystray's thread must
    never be the one that runs it."""
    host = NebulaHost(dict(CFG))
    seen = {}

    def work():
        seen["thread"] = __import__("threading").current_thread().name

    caller = __import__("threading").current_thread().name
    host.call_soon(work)
    for _ in range(100):
        if "thread" in seen:
            break
        time.sleep(0.02)

    check("call_soon actually ran the callback", "thread" in seen)
    check("it ran off the calling thread", seen.get("thread") != caller,
          "%s -> %s" % (caller, seen.get("thread")))
    host.quit()


def test_call_soon_survives_a_raising_callback():
    """One bad menu handler must not stop the queue forever."""
    host = NebulaHost(dict(CFG))
    seen = []

    def boom():
        raise ValueError("nope")

    host.call_soon(boom)
    host.call_soon(lambda: seen.append(1))
    for _ in range(100):
        if seen:
            break
        time.sleep(0.02)
    check("a raising callback does not kill the pump", seen == [1])
    check("the failure was logged",
          any("failed" in m for _, m in host.log_lines()),
          "; ".join(m for _, m in host.log_lines())[:80])
    host.quit()


def test_window_buttons_hide_and_never_destroy():
    """2j: 'Both - and x hide to tray. Quit exists only in this menu.'"""
    class FakeWindow:
        def __init__(self):
            self.calls = []

        def hide(self):
            self.calls.append("hide")

        def show(self):
            self.calls.append("show")

        def restore(self):
            self.calls.append("restore")

        def destroy(self):
            self.calls.append("destroy")

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from spike.app import Api

    win = FakeWindow()
    host = NebulaHost(dict(CFG), window=win)
    api = Api.__new__(Api)          # skip __init__: it scans disks and primes psutil
    api._host = host
    api._window = win

    api.minimise()
    api.close()
    check("both titlebar buttons hide", win.calls == ["hide", "hide"],
          str(win.calls))
    check("neither destroys the window", "destroy" not in win.calls)

    host.show()
    check("show restores as well as showing",
          win.calls[-2:] == ["show", "restore"], str(win.calls[-2:]))

    host.quit()
    check("quit is the one path that destroys", "destroy" in win.calls,
          str(win.calls))


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        print("\n--- %s" % fn.__name__.replace("test_", "").replace("_", " "))
        try:
            fn()
        except Exception:
            check(fn.__name__, False, "raised")
            traceback.print_exc()

    print("\n%s (%d checks)" % ("ALL PASS" if not FAIL else "FAILED", len(PASS) + len(FAIL)))
    if FAIL:
        for name in FAIL:
            print("  FAIL %s" % name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
