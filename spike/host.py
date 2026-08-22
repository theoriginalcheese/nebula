"""v4 host — tray, hotkeys, window lifecycle, Monitor + OBS wiring.

Single instance, the tray icon and its menu, global hotkeys, and the window
lifecycle rule that frame 2j states outright:

    "Both - and x hide to tray. Quit exists only in this menu."

`tray_app.py`, `icon_art.py` and `hotkey.py` are the shipping v3 modules.
This file is the adapter that lets them drive a webview instead of Tk.
"""
import ctypes
import os
import queue
import subprocess
import threading
import time

from obsauto import design_v3 as dv
from obsauto import hotkey as hotkey_mod
from obsauto import replay as replay_mod
from spike.windows import NebulaWindows
from obsauto import tray_app
from obsauto.app_log import log_to_file
from obsauto.monitor import Monitor, ensure_obs_running, is_obs_running
from obsauto.obs_client import OBSError, OBSClient

ERROR_ALREADY_EXISTS = 183
_INSTANCE_MUTEX = None


def claim_single_instance(name="Nebula.SingleInstance"):
    """True if we are the only instance holding `name`."""
    global _INSTANCE_MUTEX
    try:
        _INSTANCE_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def _format_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.0f %s" % (n, unit) if unit == "B" else "%.1f %s" % (n, unit)
        n /= 1024
    return "%.1f GB" % n


def _short_obs_version(raw):
    if not raw:
        return ""
    parts = str(raw).strip().split(".")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return "%s.%s" % (parts[0], parts[1])
    return str(raw).strip()


def _format_video_label(settings):
    if not settings:
        return ""
    w = settings.get("baseWidth") or settings.get("outputWidth")
    h = settings.get("baseHeight") or settings.get("outputHeight")
    num = settings.get("fpsNumerator")
    den = settings.get("fpsDenominator") or 1
    if not w or not h or not num or not den:
        return ""
    fps = float(num) / float(den)
    fps_s = ("%.0f" % fps if abs(fps - round(fps)) < 0.05
             else ("%.2f" % fps).rstrip("0").rstrip("."))
    return "%d\u00d7%d \u00b7 %s fps" % (int(w), int(h), fps_s)


def compute_bitrate(prev, duration_ms, written_bytes):
    """Return an Mbps string, or None if there is not enough data yet."""
    if not prev:
        return None
    d_ms = duration_ms - prev[0]
    d_bytes = written_bytes - prev[1]
    if d_ms < 500 or d_bytes < 0:
        return None
    mbits = (d_bytes * 8.0) / (d_ms / 1000.0) / 1_000_000.0
    return "%.1f Mb/s" % mbits


class HotkeyManager:
    """Registration with matching unregistration."""

    def __init__(self, on_log=lambda m: None):
        self._handles = {}
        self._pending = {}
        self._log = on_log

    def bind(self, name, binding, callback, scancode=None, suppress=True):
        self.unbind(name)
        handle = hotkey_mod.register(binding, callback, suppress=suppress,
                                     on_log=self._log, scancode=scancode)
        if handle:
            self._handles[name] = handle
            self._pending.pop(name, None)
        return bool(handle)

    def defer(self, name, binding, waiting_for):
        self.unbind(name)
        if binding:
            self._pending[name] = (binding, waiting_for)
            self._log("[Hotkey] '%s' (%s) not bound yet - %s."
                      % (name, binding, waiting_for))

    def unbind(self, name):
        handle = self._handles.pop(name, None)
        return hotkey_mod.unregister(handle, on_log=self._log)

    def unbind_all(self):
        for name in list(self._handles):
            self.unbind(name)

    def bound(self):
        return sorted(self._handles)

    def pending(self):
        return dict(self._pending)


class NebulaHost:
    """What the tray, the hotkeys and the window lifecycle all talk to."""

    def __init__(self, config, window=None):
        self.config = config
        self.window = window
        self.replay = None
        self.obs = None
        self.monitor = None
        self.classifier = None
        self.offloader = None
        self._visible = False
        self._awake = True
        self._suspended = False
        self._suspend_seen = set()
        self._quitting = False
        self._tray = None
        self._tray_state = None
        self._log_lines = []
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()

        # OBS / hero state — one poll chain owns these.
        self._obs_connected = False
        self._is_recording = False
        self._is_paused = False
        self._pause_reason = None   # "idle" | "session" | None — monitor auto-pause
        self._monitoring_on = False
        self._connecting = False
        self._abort_connect = False
        self._transport_busy = False
        self._poll_timer = None
        self._poll_lock = threading.Lock()
        self._bitrate_sample = None
        self._bitrate_text = ""
        self._last_written_bytes = 0
        self._tray_elapsed = ""
        self._tray_game = None
        self._current_game = None
        self._obs_version = ""
        self._handshake_ms = None
        self._video_label = ""
        self._scene_name = ""
        self._offload_pending = 0
        self._offload_reachability = None
        self._taskbar_icon_stop = threading.Event()
        self._taskbar_icon_thread = None
        self._taskbar_icon_handles = []  # keep HICONs alive

        self.hotkeys = HotkeyManager(on_log=self._log)
        self._windows = NebulaWindows(self, config)

        self._calls = queue.Queue()
        self._pump = threading.Thread(target=self._drain, daemon=True)
        self._pump.start()

    # --- backend --------------------------------------------------------

    def attach_backend(self, classifier, offloader=None):
        """Wire OBSClient + Monitor. Call once before start_hotkeys/autostart."""
        self.classifier = classifier
        self.offloader = offloader
        self.obs = OBSClient(
            self.config["obs_host"], self.config["obs_port"],
            self.config.get("obs_password", ""),
            on_log=self._log,
        )
        self.monitor = Monitor(
            self.obs, classifier, self.config,
            on_log=self._log,
            on_state=self._on_monitor_state,
            on_notify=self._on_notify,
            on_connection_change=self._on_connection_change,
            offloader=offloader,
            on_record_prompt=self._on_record_prompt,
        )

    def on_offload_state(self, pending, reachability=None):
        """Offloader worker callback — pending count + Tailscale-aware code."""
        self._offload_pending = pending
        if reachability is not None:
            self._offload_reachability = reachability

    def pause_reason(self):
        return self._pause_reason

    def offload_status(self):
        """Snapshot for Settings → Offload. Prefer the offloader's full status."""
        offloader = getattr(self, "offloader", None)
        if offloader is not None:
            try:
                snap = offloader.status_snapshot()
                self._offload_pending = snap.get("pending") or 0
                reach = snap.get("reachability")
                if reach:
                    self._offload_reachability = reach
                return snap
            except Exception:
                pass
        pending = self._offload_pending
        reach = self._offload_reachability
        return {"pending": pending, "reachability": reach,
                "enabled": bool(offloader and offloader.enabled),
                "can_sync": False, "busy": False, "message": "",
                "peer": "", "reach_label": "", "mode": "", "root": "",
                "last_scan_ago": "", "last_success_ago": "",
                "interval_hours": 0, "next_scan_in_s": None}

    # --- marshalling ----------------------------------------------------

    def call_soon(self, fn):
        """Run `fn` on the host's serial queue."""
        self._calls.put(fn)

    def _drain(self):
        while True:
            fn = self._calls.get()
            if fn is None:
                return
            try:
                fn()
            except Exception as exc:
                self._log("[Host] %s failed: %s" % (getattr(fn, "__name__", fn), exc))

    # --- logging --------------------------------------------------------

    def _log(self, message):
        with self._lock:
            self._log_lines.append((time.time(), message))
            del self._log_lines[:-500]
        log_to_file(message)

    def log_lines(self):
        with self._lock:
            return list(self._log_lines)

    # --- hero state (single enum) ---------------------------------------

    def hero_state(self):
        """disconnected | idle | recording | paused — the one source of truth."""
        with self._state_lock:
            return self._hero_state_unlocked()

    def _hero_state_unlocked(self):
        if not self._obs_connected:
            return "disconnected"
        if self._is_recording and self._is_paused:
            return "paused"
        if self._is_recording:
            return "recording"
        return "idle"

    def hero_readouts(self):
        """Elapsed / size / bitrate. Empty strings when not applicable."""
        with self._state_lock:
            state = self._hero_state_unlocked()
            if state not in ("recording", "paused"):
                return {"elapsed": "", "size": "", "bitrate": ""}
            size = _format_bytes(self._last_written_bytes) if self._last_written_bytes else ""
            return {
                "elapsed": self._tray_elapsed,
                "size": size,
                "bitrate": self._bitrate_text,
            }

    def obs_meta(self):
        """Titlebar / preview metadata from the last successful connect."""
        with self._state_lock:
            return {
                "version": self._obs_version,
                "handshake_ms": self._handshake_ms,
                "video_label": self._video_label,
                "scene": self._scene_name,
            }

    # --- window lifecycle: frame 2j -------------------------------------

    def attach(self, window):
        self.window = window

    def show(self):
        if not self.window:
            return
        try:
            self.window.show()
            self.window.restore()
            self._sleep(True)
            self._visible = True
        except Exception as exc:
            self._log("[Window] Show failed: %s" % exc)

    def hide(self):
        if not self.window:
            return
        try:
            self.window.hide()
            self._visible = False
            self._sleep(False)
        except Exception as exc:
            self._log("[Window] Hide failed: %s" % exc)

    def toggle_window(self):
        self.hide() if self._visible else self.show()

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        self._abort_connect = True
        self._taskbar_icon_stop.set()
        self._stop_poll()
        self._log("[App] Quitting.")
        self.hotkeys.unbind_all()
        if self.monitor:
            try:
                self.monitor.stop()
            except Exception:
                pass
        if self.obs and self.obs.connected:
            try:
                self.obs.disconnect()
            except Exception:
                pass
        try:
            if self._tray:
                self._tray.visible = False
                self._tray.stop()
        except Exception:
            pass
        try:
            self._windows.destroy()
        except Exception:
            pass
        self._calls.put(None)
        try:
            if self.window:
                self.window.destroy()
        except Exception:
            pass

    # --- page sleep (GPU) ------------------------------------------------

    def _sleep(self, awake):
        """Pause backdrop compositing when the window is off-screen.

        CSS `.asleep` pauses animations and hides the backdrop; WebView2
        TrySuspend stops the renderer/GPU path entirely while minimised.
        """
        self._awake = bool(awake)
        if self.window:
            js = "setAwake(%s)" % ("true" if awake else "false")
            try:
                self.window.evaluate_js(js)
            except Exception as exc:
                self._log("[Window] setAwake(%s) failed: %s" % (awake, exc))
        self._suspend_webview(not awake)

    def _suspend_webview(self, suspend):
        """Suspend / resume the Edge WebView2 renderer (UI thread).

        Three things here are load-bearing, and the first two shipped wrong:

        1. ``.CoreWebView2`` is itself a COM property read and throws
           E_NOINTERFACE off the UI thread - so *every* touch of the control,
           the lookup included, has to sit inside the marshalled closure.
           Reading it before the Invoke throws before the Invoke that exists
           to prevent it, so this logged its own failure on every launch.
        2. The method is ``TrySuspendAsync``. There is no ``TrySuspend``;
           calling it raised AttributeError, which the outer catch then
           swallowed into the same generic line.
        3. WebView2 refuses to suspend a *visible* control, so the control is
           hidden first. Nothing is on screen at this point anyway - we only
           get here once the window is minimised or hidden to the tray.
        """
        if not self.window:
            return
        # Measurement switch, in the same spirit as the page's ?nowind=1 /
        # ?nosheet=1. This is how the ~115 MB in FINDINGS.md was attributed to
        # the suspend rather than to the .asleep CSS that landed alongside it:
        #   NEBULA_NO_SUSPEND=1 python tools/bench.py --launch spike --minimised
        if os.environ.get("NEBULA_NO_SUSPEND"):
            return
        # Idempotent. start_window_watch polls, so without this every tick
        # re-asks for the state it is already in - and the very first tick
        # would resume a renderer that has never suspended.
        if suspend == self._suspended:
            return
        native = self.window.native
        browser = getattr(native, "browser", None)
        if not browser:
            return

        def action():
            try:
                wv = browser.webview
                core = wv.CoreWebView2
                if core is None:
                    return
                if suspend:
                    wv.Visible = False
                    core.TrySuspendAsync()
                    note = "suspend requested"
                else:
                    # Read before resuming: this is the only direct evidence
                    # the *previous* suspend actually took, since
                    # TrySuspendAsync completes after we stop looking.
                    was = core.IsSuspended
                    core.Resume()
                    wv.Visible = True
                    note = "resumed (renderer had suspended: %s)" % bool(was)
            except Exception as exc:
                self._log("[Window] Renderer %s failed: %s"
                          % ("suspend" if suspend else "resume", exc))
                return
            self._suspended = suspend
            # Once per direction, never per minimise - silence here would be
            # ambiguous (an early return looks exactly like a success), and
            # this is the only evidence the renderer really does stop.
            if suspend not in self._suspend_seen:
                self._suspend_seen.add(suspend)
                self._log("[Window] Renderer %s." % note)

        try:
            if native.InvokeRequired:
                from System import Func, Type
                native.Invoke(Func[Type](action))
            else:
                action()
        except Exception as exc:
            self._log("[Window] suspend marshal failed: %s" % exc)

    def awake(self):
        """Last sleep state the host asked for (for tests / API polling)."""
        return self._awake

    # --- tray -----------------------------------------------------------

    def start_window_watch(self):
        """Sleep the page whenever the window is not actually on screen.

        Routing sleep through hide() alone is not enough: the window can also
        be minimised from the taskbar, by Win+D, or by any other app - none of
        which go through our code, and none of which fire `document.hidden` on
        a frameless WebView2. Measured with only the hide() path wired: 41.5%
        of the integrated GPU with the window minimised.

        So ask Windows directly, once a second. IsIconic is a cheap call and
        this only acts on a *change* of state.
        """
        import ctypes

        def watch():
            user32 = ctypes.windll.user32
            hwnd = 0
            awake = True
            last_dpi = 0
            while not self._quitting:
                time.sleep(1.0)
                try:
                    if not hwnd:
                        hwnd = user32.FindWindowW(None, "Nebula")
                        if not hwnd:
                            continue
                        on_screen = bool(user32.IsWindowVisible(hwnd)) and                             not bool(user32.IsIconic(hwnd))
                        awake = on_screen
                        self._sleep(awake)
                        continue
                    on_screen = bool(user32.IsWindowVisible(hwnd)) and                         not bool(user32.IsIconic(hwnd))
                    if on_screen != awake:
                        awake = on_screen
                        self._sleep(awake)
                        self._overlay_follow(awake)
                    dpi = self._window_dpi(hwnd)
                    if dpi and dpi != last_dpi:
                        if last_dpi:
                            self._rescale_for_dpi(hwnd, last_dpi, dpi)
                        last_dpi = dpi
                except Exception:
                    hwnd = 0

        threading.Thread(target=watch, daemon=True).start()

    @staticmethod
    def _window_dpi(hwnd):
        """Effective DPI of the monitor this window is on, or 0."""
        try:
            return int(ctypes.windll.user32.GetDpiForWindow(hwnd))
        except Exception:
            return 0

    def _rescale_for_dpi(self, hwnd, old_dpi, new_dpi):
        """Resize the window when it crosses onto a different-DPI monitor.

        Per-monitor awareness means Windows stops stretching for us and sends
        WM_DPICHANGED expecting the app to resize itself. WinForms under
        pythonnet does not, so the window kept its *physical* size: 1280x808 of
        design units is 1920x1212 physical at 150%, and dragging that onto a
        100% monitor leaves a 1920px-wide window - it "goes huge". WebView2
        rescales its own content on the DPI change, so only the frame is wrong.

        Keeping the design size constant in *logical* units is the whole fix:
        the window should always be dv.WIDTH x dv.HEIGHT of design units,
        whatever the monitor. Polling at 1s rather than handling WM_DPICHANGED
        because subclassing the WndProc through pythonnet is far more machinery
        than a resize that can lag a frame.
        """
        try:
            SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x0002, 0x0004, 0x0010
            w = int(dv.WIDTH * new_dpi / 96.0)
            h = int(dv.HEIGHT * new_dpi / 96.0)
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, w, h,
                SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
            self._log("[Window] Monitor DPI %d -> %d, resized to %dx%d."
                      % (old_dpi, new_dpi, w, h))
        except Exception as exc:
            self._log("[Window] DPI rescale failed: %s" % exc)

    def _overlay_follow(self, on_screen):
        """2k: the overlay stands in for the main window while it is away.

        The overlay's own collapse button calls ``hide(restore=True)``, which
        brings the *main window* back - so it was always designed as the
        window's stand-in, not a free-floating widget. Nothing in v4 ever
        called show_mini() though, which left the whole 2k layer unreachable
        in the shipped app even though windows.py implements it completely.

        Gate on the state here rather than letting overlay_show() refuse: it
        refuses by writing "only appears while recording" to the activity log,
        which would then land every time the window is minimised while idle.
        """
        try:
            if on_screen:
                self.hide_mini()
            elif self.hero_state() in ("recording", "paused"):
                self.show_mini()
        except Exception as exc:
            self._log("[Overlay] %s" % exc)

    def start_tray(self):
        self._tray = tray_app.build_tray_icon(self, None)
        return self._tray

    def start_taskbar_icon(self):
        """Hover-only orbit on the taskbar / Alt-Tab icon.

        Resting = static mark. Cursor on our taskbar button → orbit frames via
        Form.Icon / WM_SETICON. Constant spin is too distracting and was
        deliberately retired; see spike/taskbar_icon.py.
        """
        from spike import taskbar_icon
        taskbar_icon.start(self)

    def tray_status(self):
        """Everything the menu and tooltip need, in one snapshot."""
        state = self.hero_state()
        heading = {
            "recording": "Recording",
            "paused": ("Paused — stream ended"
                       if self._pause_reason == "session" else "Paused"),
            "idle": "Watching for a game",
            "disconnected": "OBS disconnected",
        }[state]

        game = self._current_game or self._tray_game
        elapsed = self._tray_elapsed
        if state in ("recording", "paused") and game:
            detail = "%s \u00b7 %s" % (game, elapsed) if elapsed else game
            if state == "paused" and self._pause_reason == "session":
                detail = ("%s \u00b7 stream ended" % detail) if detail else "stream ended"
        elif state == "disconnected":
            detail = "%s:%s" % (self.config.get("obs_host", "localhost"),
                                self.config.get("obs_port", 4455))
        elif game:
            detail = game
        else:
            detail = "No game in focus"

        pending = self._offload_pending
        reach = self._offload_reachability
        if pending and reach and str(reach).startswith("nas_down"):
            wait = "%d clip%s waiting on NAS" % (
                pending, "s" if pending != 1 else "")
            if state == "idle" and detail == "No game in focus":
                detail = wait
            elif state == "idle":
                detail = "%s \u00b7 %s" % (detail, wait)

        monitoring = bool(self.monitor and self.monitor._running)
        return {"state": state, "heading": heading, "detail": detail,
                "monitoring": monitoring}

    def refresh_tray_icon(self):
        if not self._tray:
            return
        state = self.tray_status()["state"]
        icon_state = ("recording" if state in ("recording", "paused") else
                      "disconnected" if state == "disconnected" else "idle")
        if icon_state == self._tray_state:
            return
        # tray_app owns the swap so the recording arc has one implementation
        # for both renderers - see set_tray_state.
        tray_app.set_tray_state(self._tray, icon_state)
        self._tray_state = icon_state

    # --- OBS connect ----------------------------------------------------

    def autostart(self):
        """Launch OBS if needed, connect on a worker, start the monitor."""
        if not self.monitor or not self.obs:
            return
        if self.monitor._running or self._connecting:
            return
        self._connecting = True
        self._abort_connect = False
        self._clear_obs_meta()

        def worker():
            meta = {}
            try:
                ensure_obs_running(self.config.get("obs_path"), log=self._log)
                self.obs.connect()
                meta = self._fetch_obs_meta()
            except Exception as exc:
                error = exc
                self.call_soon(lambda: self._connect_failed(error))
                return
            finally:
                self._connecting = False
            self.call_soon(lambda m=meta: self._connect_succeeded(m))

        threading.Thread(target=worker, daemon=True).start()

    def _fetch_obs_meta(self):
        meta = {
            "handshake_ms": self.obs.last_handshake_ms,
            "version": "",
            "video_label": "",
            "scene": "",
        }
        try:
            meta["version"] = _short_obs_version(self.obs.get_version())
        except OBSError:
            pass
        try:
            meta["video_label"] = _format_video_label(self.obs.get_video_settings())
        except OBSError:
            pass
        try:
            meta["scene"] = self.obs.get_current_program_scene() or ""
        except OBSError:
            pass
        return meta

    def _apply_obs_meta(self, meta):
        if not meta:
            return
        with self._state_lock:
            self._handshake_ms = meta.get("handshake_ms")
            self._obs_version = meta.get("version") or ""
            self._video_label = meta.get("video_label") or ""
            self._scene_name = meta.get("scene") or ""

    def _clear_obs_meta(self):
        with self._state_lock:
            self._obs_version = ""
            self._handshake_ms = None
            self._video_label = ""
            self._scene_name = ""

    def _connect_failed(self, error):
        if self._abort_connect:
            return
        if is_obs_running():
            self._log("[Monitor] OBS is running but its WebSocket server isn't "
                      "accepting connections. In OBS: Tools -> WebSocket Server "
                      "Settings -> tick 'Enable WebSocket server' (or restart OBS). "
                      "Retrying in 10s...")
        else:
            self._log("[Monitor] OBS not available yet (%s); retrying in 10s..." % error)
        self._schedule_retry(10.0)

    def _connect_succeeded(self, meta=None):
        if self._abort_connect:
            if self.obs.connected:
                self.obs.disconnect()
            self._clear_obs_meta()
            return
        self._apply_obs_meta(meta or {})
        self._monitoring_on = True
        with self._state_lock:
            self._obs_connected = True
        self.monitor.start()
        self._log("[Monitor] Auto-started.")
        self.refresh_tray_icon()
        self._poll_now()

    def _schedule_retry(self, delay):
        if self._quitting:
            return

        def retry():
            if not self._quitting:
                self.autostart()

        threading.Timer(delay, retry).start()

    def _on_connection_change(self, connected):
        with self._state_lock:
            self._obs_connected = bool(connected)
        if connected:
            def refresh():
                try:
                    meta = self._fetch_obs_meta()
                except Exception:
                    meta = {}
                self.call_soon(lambda m=meta: self._apply_obs_meta(m))
                self.call_soon(self.refresh_tray_icon)
            threading.Thread(target=refresh, daemon=True).start()
        else:
            self._clear_obs_meta()
            self.call_soon(self.refresh_tray_icon)

    def _on_monitor_state(self, **kwargs):
        def apply():
            if "game" in kwargs:
                self._current_game = kwargs["game"]
                if kwargs["game"]:
                    self._tray_game = kwargs["game"]
            self.refresh_tray_icon()
        self.call_soon(apply)

    def _on_notify(self, event, display_name, details=None):
        details = details or {}
        if event == "pause" and "reason" in details:
            self._pause_reason = details.get("reason")
        elif event in ("resume", "stop", "start"):
            self._pause_reason = None
        self._log("[Monitor] %s %s" % (event, display_name))
        # 2i: one slot for the whole process life - replace in place,
        # never stack. The window owns that rule; this only feeds it.
        try:
            self._windows.toast_replace(event, display_name, details)
        except Exception as exc:
            self._log("[Toast] %s" % exc)
        self.call_soon(self.refresh_tray_icon)

    # --- status poll ----------------------------------------------------

    def start_poll(self):
        """Begin the single self-rescheduling GetRecordStatus chain."""
        self._poll_now()

    def _stop_poll(self):
        with self._poll_lock:
            if self._poll_timer:
                self._poll_timer.cancel()
                self._poll_timer = None

    def _schedule_poll(self, delay):
        if self._quitting:
            return
        with self._poll_lock:
            if self._poll_timer:
                self._poll_timer.cancel()
            self._poll_timer = threading.Timer(delay, self._poll_tick)
            self._poll_timer.daemon = True
            self._poll_timer.start()

    def _poll_tick(self):
        if self._quitting:
            return
        self._poll_obs_status()
        delay = 1.0 if self._visible else 5.0
        self._schedule_poll(delay)

    def _poll_now(self):
        with self._poll_lock:
            if self._poll_timer:
                self._poll_timer.cancel()
                self._poll_timer = None
        self._poll_tick()

    def _poll_obs_status(self):
        is_recording = False
        is_paused = False
        if self.obs and self.obs.connected:
            try:
                status = self.obs.get_record_status()
                is_recording = bool(status.get("outputActive"))
                is_paused = bool(status.get("outputPaused"))
                if is_recording:
                    total_seconds = status.get("outputDuration", 0) // 1000
                    hh, rem = divmod(total_seconds, 3600)
                    mm, ss = divmod(rem, 60)
                    elapsed = "%02d:%02d:%02d" % (hh, mm, ss)
                    written = status.get("outputBytes", 0)
                    duration_ms = status.get("outputDuration", 0)
                    with self._state_lock:
                        self._tray_elapsed = elapsed
                        self._last_written_bytes = written
                        text = compute_bitrate(self._bitrate_sample, duration_ms, written)
                        self._bitrate_sample = (duration_ms, written)
                        if text:
                            self._bitrate_text = text
            except OBSError:
                pass

        with self._state_lock:
            was = (self._is_recording, self._is_paused, self._obs_connected)
            self._is_paused = is_paused
            self._is_recording = is_recording
            if self.obs:
                self._obs_connected = bool(self.obs.connected)
            now = (self._is_recording, self._is_paused, self._obs_connected)
            if not is_recording:
                self._bitrate_sample = None
                self._bitrate_text = ""
                self._tray_elapsed = ""
                self._last_written_bytes = 0

        if was != now:
            self.refresh_tray_icon()

    # --- transport ------------------------------------------------------
        # 2k: the overlay never shows while idle, so it is driven by the
        # same poll that owns the recording state rather than by a timer
        # of its own - one source of truth, one chain.
        try:
            self._windows.overlay_sync()
        except Exception as exc:
            self._log("[Overlay] %s" % exc)

    # --- transport ------------------------------------------------------

    def _toggle_record(self):
        self._transport("record")

    def _toggle_pause(self):
        self._transport("pause")

    def _transport(self, action):
        if not self.obs:
            return
        if self._transport_busy:
            return
        self._transport_busy = True
        prior = self.monitor._recording_target if self.monitor else None
        hold_basename = prior[1] if prior else None
        hold_name = prior[2] if prior else None

        def worker():
            result = {"action": action, "stopped": False, "event": None,
                      "outcome": None, "problem": None,
                      "hold_basename": hold_basename, "hold_name": hold_name}
            try:
                status = self.obs.get_record_status()
                recording = bool(status.get("outputActive"))
                paused = bool(status.get("outputPaused"))
                if action == "record":
                    if recording:
                        self.obs.stop_record()
                        result.update(stopped=True, event="stop",
                                      outcome="Recording stopped.")
                    elif (self.monitor and self.monitor._hold_off
                          and self.monitor._hold_off_pending is not None):
                        self.monitor.accept_record_prompt()
                        result.update(event="start",
                                      outcome="Recording started.")
                    else:
                        self.obs.start_record()
                        result.update(event="start", outcome="Recording started.")
                elif not recording:
                    result["outcome"] = "Nothing is recording - nothing to pause."
                elif paused:
                    self.obs.resume_record()
                    result.update(event="resume", outcome="Recording resumed.")
                else:
                    self.obs.pause_record()
                    result.update(event="pause", outcome="Recording paused.")
            except OBSError as exc:
                result["problem"] = str(exc)
            self.call_soon(lambda r=result: self._transport_done(r))

        threading.Thread(target=worker, daemon=True).start()

    def _transport_done(self, result):
        self._transport_busy = False
        if result["problem"]:
            verb = "start/stop" if result["action"] == "record" else "pause/resume"
            self._log("[Manual] Could not %s recording: %s" % (verb, result["problem"]))
        else:
            self._log("[Manual] %s" % result["outcome"])
            if result.get("stopped") and self.monitor:
                self.monitor._recording_target = None
                self.monitor.note_manual_stop(
                    result.get("hold_basename"), result.get("hold_name"))
                try:
                    name = result.get("hold_name") or "Recording"
                    self._windows.toast_replace("stop", name)
                except Exception as exc:
                    self._log("[Toast] %s" % exc)
            elif result.get("event") == "start" and self.monitor:
                self.monitor.clear_hold_off()
        self._poll_now()

    def _on_record_prompt(self, basename, display_name, reason, target):
        b, n, r = basename, display_name, reason

        def show():
            if reason == "same":
                title = "Record again?"
                sub = n or b or "this game"
            else:
                title = "New game detected"
                sub = "Record %s?" % (n or b)
            self._log("[Monitor] Prompt: %s (%s)" % (sub, r))

            def accept():
                if self.monitor:
                    self.monitor.accept_record_prompt()
                self._poll_now()

            def dismiss():
                if self.monitor:
                    self.monitor.dismiss_record_prompt(b)

            try:
                self._windows.toast_replace(
                    "prompt", sub, {"title": title},
                    actions=[("Record", accept), ("Not now", dismiss)],
                    on_timeout=dismiss,
                )
            except Exception as exc:
                self._log("[Toast] %s" % exc)

        self.call_soon(show)

    def _stop(self):
        self._abort_connect = True
        if self.monitor:
            self.monitor.stop()
        if self.obs and self.obs.connected:
            self.obs.disconnect()
        self._clear_obs_meta()
        self._monitoring_on = False
        with self._state_lock:
            self._obs_connected = False
            self._is_recording = False
            self._is_paused = False
        self.refresh_tray_icon()

    # --- actions the tray menu can reach --------------------------------

    def open_palette(self):
        """Global hotkey -> show the window, then open the palette in it.

        7e's palette is in-window, so a *global* binding has two jobs: surface
        the window (it is a tray app, so it is usually hidden) and then tell the
        page to open. Doing only the second silently does nothing when hidden -
        which is what an in-window keydown alone already gives you.

        Runs on `keyboard`'s hook thread, so it goes through call_soon rather
        than touching the window from there.
        """
        def run():
            was_hidden = not self._visible
            if was_hidden:
                self.show()
            if not self.window:
                return
            try:
                # Give a freshly-shown window a moment to be focusable, or the
                # palette opens behind and the input never takes the caret.
                if was_hidden:
                    time.sleep(0.15)
                self.window.evaluate_js(
                    "window.openPalette && window.openPalette()")
            except Exception as exc:
                self._log("[Palette] Could not open: %s" % exc)

        self.call_soon(run)

    def show_mini(self):
        """Show the mini overlay. Refused while idle - 2k is explicit that it
        never appears without a recording to describe."""
        try:
            self._windows.overlay_show()
        except Exception as exc:
            self._log("[Overlay] Could not show: %s" % exc)

    def hide_mini(self, restore=False):
        try:
            self._windows.overlay_hide(restore=restore)
        except Exception as exc:
            self._log("[Overlay] Could not hide: %s" % exc)

    def _open_recording_root(self):
        root = self.config.get("recording_root") or ""
        if not root or not os.path.isdir(root):
            self._log("[Tray] recording_root does not exist: %r" % root)
            return
        try:
            subprocess.Popen(["explorer", os.path.normpath(root)])
        except Exception as exc:
            self._log("[Tray] Could not open %s: %s" % (root, exc))

    def _toggle_monitoring(self):
        if not self.monitor:
            return
        if self.monitor._running:
            self._stop()
            self._log("[Hotkey] Monitoring disabled.")
        else:
            self.autostart()
            self._log("[Hotkey] Monitoring enabled.")

    def _save_replay(self):
        """Save the buffered seconds. Reachable from the tray and the hotkey."""
        if not self.replay or not self.replay.armed:
            self._log("[Replay] Nothing armed - nothing to save.")
            return
        try:
            self.replay.save()
        except Exception as exc:
            self._log("[Replay] Save failed: %s" % exc)

    def start_replay(self):
        """Attach the buffer. Armed only if the user asked for it.

        v3 armed the buffer whenever monitoring started, so OBS held the last
        N seconds in RAM for the whole session whether or not anyone ever
        pressed the key. `replay.ram_estimate_mb()` puts that at ~33 MB at this
        machine's measured ~7.8 Mb/s (a 633 MB clip over 10:52) - real, but far
        from the memory sink it looked like. Still: it is a side feature, so it
        is now opt-in.

        `replay_arm_with_monitoring` is the switch and already exists in
        config.json. False means the buffer is only armed when explicitly
        asked for, via the tray or the hotkey.
        """
        if not self.obs:
            return None
        self.replay = replay_mod.ReplayBuffer(
            self.obs, self.config, on_log=self._log,
            on_saved=lambda path, game: self._log(
                "[Replay] Saved %s%s" % (path, " (%s)" % game if game else "")),
            on_state=lambda armed: self._log(
                "[Replay] Buffer %s." % ("armed" if armed else "disarmed")))

        if not self.replay.enabled:
            self._log("[Replay] Disabled in config - not attaching.")
            return self.replay

        seconds = self.replay.seconds
        est = replay_mod.ram_estimate_mb(self._bitrate_mbps() or 8.0, seconds)
        if self.config.get("replay_arm_with_monitoring"):
            self._log("[Replay] Arming with monitoring - OBS will hold ~%.0f MB "
                      "for the last %ds." % (est, seconds))
        else:
            self._log("[Replay] Available but not armed (~%.0f MB when armed). "
                      "Arm it from the tray or press the replay hotkey."
                      % est)
        return self.replay

    def toggle_replay_arm(self):
        """Arm or disarm on demand - what makes this a side feature."""
        if not self.replay or not self.replay.enabled:
            self._log("[Replay] Not available.")
            return
        try:
            if self.replay.armed:
                self.replay.disarm()
            else:
                self.replay.arm()
        except Exception as exc:
            self._log("[Replay] Could not toggle: %s" % exc)

    def _bitrate_mbps(self):
        """Last measured encoder rate, or None. Never a guessed default."""
        text = getattr(self, "_bitrate_text", "") or ""
        try:
            return float(text.split()[0])
        except (ValueError, IndexError):
            return None

    def _on_toggle_hotkey(self):
        self.call_soon(self._toggle_monitoring)

    # --- hotkeys ---------------------------------------------------------

    def start_hotkeys(self):
        cfg = self.config
        if self.monitor is not None:
            self.hotkeys.bind(
                "toggle", cfg.get("toggle_hotkey"),
                self._on_toggle_hotkey,
                scancode=cfg.get("toggle_hotkey_scancode"))
        else:
            self.hotkeys.defer("toggle", cfg.get("toggle_hotkey"),
                               "monitoring arrives in v4 step 2")
        if self.replay is not None and self.replay.enabled:
            self.hotkeys.bind("replay", cfg.get("replay_hotkey"),
                              self._save_replay,
                              scancode=cfg.get("replay_hotkey_scancode"))
        else:
            self.hotkeys.defer("replay", cfg.get("replay_hotkey"),
                               "replay is disabled in config")
        self.hotkeys.bind("palette", cfg.get("palette_hotkey"),
                          self.open_palette)
        return self.hotkeys
