"""WebView2 GPU/power — pin the iGPU, suspend hidden renderers, trim VRAM.

Nebula is a tray app on a hybrid laptop (Radeon 610M + RTX 4070). The 4070
belongs to the game; this module keeps Edge on the low-power adapter and
drops compositor tiles once the HWND is off-screen.

``NEBULA_GPU=dgpu`` is a measurement switch (force the discrete adapter). It
is not the default and must not be shipped as one.
"""
from __future__ import annotations

import inspect
import os
import sys
import textwrap
import threading

LOW_POWER_ARGS = "--force-low-power-gpu"
HIGH_POWER_ARGS = "--force-high-performance-gpu"
# The 610M's "dedicated" heap is ~512 MB of system RAM. Chromium otherwise
# assumes a large GPU and fills it with compositor tiles (aurora + two
# full-window star layers). Cap so DWM/Photos still have room.
GPU_MEM_CAP_ARGS = "--force-gpu-mem-available-mb=128"

# CoreWebView2MemoryUsageTargetLevel
_MEM_NORMAL = 0
_MEM_LOW = 1


def window_on_screen(host_visible, win_visible, iconic):
    """True only if we meant the HWND to be up *and* Windows still shows it.

    pywebview ``hide()`` does not always clear ``IsWindowVisible`` on a
    frameless form, and it never sets ``IsIconic``. The 1s watcher used to
    trust those bits alone, so a tray hide woke the aurora again (~44% iGPU
    with only the mini overlay on). ``host_visible`` is the hide()/show()
    latch; iconic covers taskbar minimise while the latch is still True.
    """
    return bool(host_visible) and bool(win_visible) and not bool(iconic)


def gpu_page_state(on_screen, focused):
    """Which compositor mode the main window should be in.

    Hidden/minimised → full sleep + TrySuspend (the tray/gaming case).
    On screen and focused → full motion.
    On screen but unfocused (game on the other monitor, another app in front)
    → chrome stays, aurora pauses. Suspending a visible control is refused
    by WebView2, so we never TrySuspend while the HWND is on screen.
    """
    if not on_screen:
        return {"awake": False, "quiet": False, "suspend": True}
    return {"awake": True, "quiet": (not focused), "suspend": False}


def want_high_performance():
    return os.environ.get("NEBULA_GPU", "").strip().lower() in ("dgpu", "high", "discrete")


def apply_browser_arguments():
    """Must run before the WebView2 environment is created."""
    flag = HIGH_POWER_ARGS if want_high_performance() else LOW_POWER_ARGS
    existing = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "").strip()
    extra = []
    if LOW_POWER_ARGS not in existing and HIGH_POWER_ARGS not in existing:
        extra.append(flag)
    if "--force-gpu-mem-available-mb=" not in existing:
        extra.append(GPU_MEM_CAP_ARGS)
    if not extra:
        return existing
    merged = ("%s %s" % (existing, " ".join(extra))).strip()
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = merged
    return merged


def pin_exe_gpu_preference(high_performance=None):
    """HKCU DirectX UserGpuPreferences for *this* exe only — never msedgewebview2.

    GpuPreference=1 is power-saving (iGPU); 2 is high-performance (dGPU).
    """
    if os.name != "nt":
        return None
    if high_performance is None:
        high_performance = want_high_performance()
    try:
        import winreg
    except ImportError:
        return None
    path = os.path.normcase(os.path.abspath(sys.executable))
    want = "GpuPreference=%d;" % (2 if high_performance else 1)
    try:
        key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\DirectX\UserGpuPreferences",
        )
        try:
            current, _typ = winreg.QueryValueEx(key, path)
        except FileNotFoundError:
            current = ""
        except OSError:
            current = ""
        if current != want:
            winreg.SetValueEx(key, path, 0, winreg.REG_SZ, want)
        winreg.CloseKey(key)
        return want
    except OSError:
        return None


def apply_webview_power(window, suspend, log=None, prefix="[Window]"):
    """TrySuspend + MemoryUsageTargetLevel on one pywebview window.

    Every CoreWebView2 touch, the property lookup included, has to run on the
    WinForms thread. Returns True if the COM path ran; False means retry.
    """
    if window is None or os.environ.get("NEBULA_NO_SUSPEND"):
        return False
    native = getattr(window, "native", None)
    if native is None:
        return False
    browser = getattr(native, "browser", None)
    if browser is None:
        return False

    result = {"ok": False}

    def action():
        try:
            wv = browser.webview
            core = wv.CoreWebView2
            if core is None:
                return
            if suspend:
                try:
                    native.Visible = False
                except Exception:
                    pass
                wv.Visible = False
                try:
                    core.MemoryUsageTargetLevel = _MEM_LOW
                except Exception:
                    pass
                core.TrySuspendAsync()
            else:
                try:
                    core.MemoryUsageTargetLevel = _MEM_NORMAL
                except Exception:
                    pass
                try:
                    core.Resume()
                except Exception:
                    pass
                wv.Visible = True
                try:
                    native.Visible = True
                except Exception:
                    pass
            result["ok"] = True
        except Exception as exc:
            if log:
                log("%s Renderer %s failed: %s"
                    % (prefix, "suspend" if suspend else "resume", exc))

    try:
        if getattr(native, "InvokeRequired", False):
            from System import Func, Type
            native.Invoke(Func[Type](action))
        else:
            action()
    except Exception as exc:
        if log:
            log("%s suspend marshal failed: %s" % (prefix, exc))
        return False
    return bool(result["ok"])


class SleepGate:
    """Orders a page's sleep script against TrySuspend / Resume.

    ``ExecuteScript`` resumes a suspended renderer, so a ``setAsleep(true)``
    landing after TrySuspend undid it and the flag stayed True with nothing
    to retry. Sleep runs the script first and suspends after; wake resumes
    first, since a suspended page never answers the script. ``gen`` lets a
    newer call (or ``cancel()``) void a suspend that is still in flight.
    """

    def __init__(self):
        self.asleep = False
        self.gen = 0
        self._lock = threading.Lock()

    def cancel(self):
        with self._lock:
            self.gen += 1
            self.asleep = False

    def set(self, window, asleep, script=None, log=None, prefix="[Window]",
            off_gui=None, run_on_gui=None, power=True):
        asleep = bool(asleep)
        if window is None or asleep == self.asleep:
            return
        with self._lock:
            self.gen += 1
            gen = self.gen
            self.asleep = asleep
        # power=False is the toast: hide() already took the HWND off screen,
        # and TrySuspend makes the next evaluate_js never return, so the
        # capsule stays at opacity 0 and the user sees nothing.
        if not asleep and power:
            apply_webview_power(window, False, log=log, prefix=prefix)

        def suspend_on_gui():
            if gen != self.gen:
                return
            apply_webview_power(window, True, log=log, prefix=prefix)

        def worker():
            if gen != self.gen:
                return
            if script:
                if gen != self.gen:
                    return
                try:
                    window.evaluate_js(script)
                except Exception as exc:
                    error = exc
                    if log:
                        log("%s %s failed: %s" % (prefix, script, error))
            if asleep and power and gen == self.gen:
                if run_on_gui is not None:
                    run_on_gui(suspend_on_gui)
                else:
                    suspend_on_gui()

        if off_gui is not None:
            off_gui(worker)
        else:
            threading.Thread(target=worker, daemon=True).start()


# One CoreWebView2Environment for every control in the process. pywebview
# already points them all at one user-data folder; this makes the later ones
# join the first environment explicitly instead of each asking for one.
_SHARED = {"env": None, "hooked": None, "prepared": False}
_SHARED_LOCK = threading.Lock()
_ENSURE_NONE = "self.webview.EnsureCoreWebView2Async(None)"


def _merge_args(*parts):
    seen = []
    for part in parts:
        for arg in (part or "").split():
            if arg not in seen:
                seen.append(arg)
    return " ".join(seen)


def _nebula_ensure_core(chrome):
    wv = chrome.webview
    env = _SHARED["env"]
    if env is not None:
        props = None
        try:
            props = wv.CreationProperties
        except Exception:
            pass
        try:
            # With CreationProperties set, WinForms ignores the environment.
            wv.CreationProperties = None
            wv.EnsureCoreWebView2Async(env)
            return
        except Exception:
            if props is not None:
                try:
                    wv.CreationProperties = props
                except Exception:
                    pass
    # The env var replaces the props' arguments when both are set, so carry
    # pywebview's own switches into it rather than losing them.
    try:
        props = wv.CreationProperties
        if props is not None:
            merged = _merge_args(
                props.AdditionalBrowserArguments,
                os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", ""))
            props.AdditionalBrowserArguments = merged
            os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = merged
    except Exception:
        pass
    wv.EnsureCoreWebView2Async(None)


def _install_shared_environment():
    try:
        from webview.platforms import edgechromium
    except Exception:
        return False
    cls = edgechromium.EdgeChrome
    if getattr(cls, "_nebula_shared_env", False):
        return True
    try:
        source = textwrap.dedent(inspect.getsource(cls.__init__))
    except (OSError, TypeError):
        return False
    if _ENSURE_NONE not in source:
        return False
    source = source.replace(_ENSURE_NONE, "_nebula_ensure_core(self)", 1)
    scope = dict(vars(edgechromium))
    scope["_nebula_ensure_core"] = _nebula_ensure_core
    try:
        exec(compile(source, inspect.getsourcefile(cls) or "<edgechromium>",
                     "exec"), scope)
    except Exception:
        return False
    patched_init = scope.get("__init__")
    if patched_init is None:
        return False
    original_ready = cls.on_webview_ready

    def on_webview_ready(self, sender, args):
        try:
            original_ready(self, sender, args)
        finally:
            if _SHARED["env"] is None:
                try:
                    if args.IsSuccess:
                        _SHARED["env"] = sender.CoreWebView2.Environment
                except Exception:
                    pass

    patched_init.__qualname__ = cls.__init__.__qualname__
    cls.__init__ = patched_init
    cls.on_webview_ready = on_webview_ready
    cls._nebula_shared_env = True
    return True


def prepare_webview_process():
    """Run once before the first ``webview.create_window``.

    Puts the low-power + VRAM-cap switches in place before the browser
    process exists, and makes every later WebView2 join the first one's
    environment. Returns whether the environment hook is installed.
    """
    with _SHARED_LOCK:
        if not _SHARED["prepared"]:
            _SHARED["prepared"] = True
            apply_browser_arguments()
            pin_exe_gpu_preference()
        if _SHARED["hooked"] is None:
            try:
                _SHARED["hooked"] = bool(_install_shared_environment())
            except Exception:
                _SHARED["hooked"] = False
        return _SHARED["hooked"]
