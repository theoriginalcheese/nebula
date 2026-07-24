"""Main polling loop: figures out which (if any) game should be recording
right now, and drives OBS accordingly.

State model: once locked onto a game, we stay locked onto it (sticky) even if
you alt-tab to Discord/a browser/whatever - only releasing when that game's
process actually exits. Picking a *new* game to lock onto prefers whichever
window currently has focus, falling back to scanning all visible windows only
if the foreground window isn't a classified game (e.g. a launcher window is
briefly focused while the game itself loads in the background).

On a change, we stop whatever OBS is currently recording and, if there's a
new target, create its folder, retarget the shared dynamic Game Capture
source at the right window, and start a fresh recording. This covers
game-switch, game-close, and idle-pause/resume with one piece of logic.
"""

import ctypes
import os
import re
import subprocess
import threading
import time

import psutil

try:
    import win32gui
    import win32process
except ImportError:  # pragma: no cover
    win32gui = None
    win32process = None

from .obs_client import OBSError
from . import session_detect
from .audio_detect import AudioKeepAlive

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')
_UNSET = object()

GAME_CAPTURE_INPUT_NAME = "Game Capture (Auto)"

# Apps whose recording should track a live *session*, not just the process
# being open. For a normal game, "process has a window" == "should record".
# For a streaming client like Moonlight, the app stays open at its host-list
# screen between streams, so recording is instead gated on whether a stream
# is actually live. Each value returns True (record) / False (pause) / None
# (can't tell - treated as record). Keyed by lowercase exe basename.
SESSION_GATES = {
    "moonlight.exe": session_detect.moonlight_session_active,
}


def sanitize_folder_name(name):
    return _INVALID_CHARS.sub("_", name).strip() or "Unknown"


def encode_obs_window_id(title, cls, exe):
    """Build the "Title:Class:Exe" string OBS's game/window capture sources
    use to identify a window, matching OBS's own escaping (escape '#' first,
    then ':' - reversing the order would mangle the '#' just introduced by
    the colon escape). Verified against a real captured string from this
    OBS install: 'Honkai#3A Star Rail:UnityWndClass:StarRail.exe' decodes to
    title 'Honkai: Star Rail'.
    """
    def encode(part):
        return part.replace("#", "#23").replace(":", "#3A")

    return f"{encode(title)}:{encode(cls)}:{encode(exe)}"


def get_idle_duration():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0
    return 0.0


def _process_info(pid):
    try:
        proc = psutil.Process(pid)
        return proc.exe(), proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None, None


def is_obs_running():
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == "obs64.exe":
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


OBS_LAUNCH_TASK_NAME = "NebulaLaunchOBS"


def _launch_via_scheduled_task(log):
    """This OBS install is set to always run as Administrator (needed for
    fullscreen capture of some games, e.g. Genshin/ZZZ) - a normal
    subprocess.Popen from this non-elevated app can't silently elevate a
    child process (fails with WinError 740). A pre-created Scheduled Task
    ("run with highest privileges") launches it elevated with no UAC
    prompt, since the one-time admin consent needed to *create* that task
    was already granted separately. No-ops (returns False) if the task
    doesn't exist on this machine - callers should fall back to a normal
    launch attempt."""
    try:
        result = subprocess.run(
            ["schtasks", "/run", "/tn", OBS_LAUNCH_TASK_NAME],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_obs_running(obs_path, log=lambda msg: None):
    """Launch OBS if it isn't already running. Used both for the initial
    connection (in case OBS isn't set to autostart with Windows) and for
    recovering after OBS crashes/closes mid-session."""
    if is_obs_running():
        return
    if _launch_via_scheduled_task(log):
        log("[OBS] Launched OBS (elevated, via scheduled task).")
        return
    if not obs_path or not os.path.exists(obs_path):
        return
    try:
        # --minimize-to-tray is OBS's own supported flag for this - more
        # reliable than fighting window state externally via CreateProcess
        # show flags, which OBS's own startup routine can just override.
        subprocess.Popen([obs_path, "--minimize-to-tray"], cwd=os.path.dirname(obs_path))
        log(f"[OBS] Launched OBS (minimized) from {obs_path}")
    except OSError as e:
        log(f"[OBS] Failed to launch OBS: {e}")


def _window_info(hwnd):
    """(pid, exe_path, proc_name, title, class_name) for a single hwnd, or
    None if the process behind it can no longer be inspected."""
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    exe_path, proc_name = _process_info(pid)
    if exe_path is None:
        return None
    return (pid, exe_path, proc_name, win32gui.GetWindowText(hwnd), win32gui.GetClassName(hwnd))


def list_visible_windows():
    """Return [(pid, exe_path, proc_name, title, class_name)] for every
    process owning a visible, titled top-level window - i.e. things a person
    could actually be sitting in front of, as opposed to every background
    service."""
    if win32gui is None:
        return []

    hwnds = []

    def _callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if not win32gui.GetWindowText(hwnd):
            return True
        if win32gui.GetParent(hwnd) != 0:
            return True
        hwnds.append(hwnd)
        return True

    win32gui.EnumWindows(_callback, None)

    results = []
    seen_pids = set()
    for hwnd in hwnds:
        info = _window_info(hwnd)
        if info and info[0] not in seen_pids:
            seen_pids.add(info[0])
            results.append(info)
    return results


def get_foreground_window_info():
    if win32gui is None:
        return None
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd or not win32gui.GetWindowText(hwnd):
        return None
    return _window_info(hwnd)


class Monitor:
    def __init__(self, obs_client, classifier, config, on_log=None, on_state=None, on_notify=None,
                 on_connection_change=None, offloader=None):
        self.obs = obs_client
        self.classifier = classifier
        self.config = config
        self.offloader = offloader  # optional NAS offloader; None = feature off
        self.on_log = on_log or (lambda msg: None)
        self.on_state = on_state or (lambda **kwargs: None)  # game, folder, idle
        self.on_notify = on_notify or (lambda event, display_name, details=None: None)  # event: "start"|"stop"|"pause"|"resume"
        self.on_connection_change = on_connection_change or (lambda connected: None)
        self._running = False
        self._thread = None
        self._recording_target = None  # (pid, basename, display_name, folder, window_id) or None
        self._pending_target = _UNSET
        self._pending_count = 0
        self._recording_started_at = None
        self._last_reconnect_attempt = 0.0
        self._was_disconnected = False
        self._auto_paused = False
        self._audio_keep_alive = AudioKeepAlive(
            config.get("keep_alive_audio_processes", ["discord.exe"]), on_log=self.log,
        )

    def log(self, msg):
        self.on_log(msg)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.log("[Monitor] Started.")

    def stop(self):
        self._running = False
        if self.obs.connected:
            prev_name = self._recording_target[2] if self._recording_target else "unknown"
            self._stop_current_recording(prev_name)
        self._recording_target = None
        self._pending_target = _UNSET
        self._pending_count = 0
        self._auto_paused = False
        self.log("[Monitor] Stopped.")

    def _stop_current_recording(self, prev_name):
        """Stop whatever's currently recording (retrying once if OBS briefly
        rejects it), then discard the clip if it turned out too short to be
        worth keeping - e.g. a game window that flickered open and shut
        rather than an actual play session."""
        if not self.obs.is_recording():
            return True

        response = None
        for attempt in range(2):
            try:
                response = self.obs.stop_record()
                break
            except OBSError as e:
                self.log(f"[OBS] Stop failed (attempt {attempt + 1}): {e}")
                time.sleep(0.5)
        if response is None:
            self.log("[OBS] Giving up on stop; leaving current recording in place.")
            return False

        self.log(f"[OBS] Stopped recording ({prev_name}).")
        elapsed = (time.time() - self._recording_started_at) if self._recording_started_at else None
        output_path = response.get("outputPath")
        file_size = None
        if output_path:
            # OBS still holds the file open for a moment after StopRecord
            # returns (finalizing the container) - reading the size too
            # early gives 0 rather than the real final size.
            for attempt in range(6):
                try:
                    size = os.path.getsize(output_path)
                except OSError:
                    size = 0
                if size > 0:
                    file_size = size
                    break
                time.sleep(0.2)
        self.on_notify("stop", prev_name, {"duration": elapsed, "size": file_size})

        min_seconds = self.config.get("min_clip_seconds", 0)
        too_short = elapsed is not None and output_path and elapsed < min_seconds
        if too_short:
            # OBS still holds the file open for a moment after StopRecord
            # returns (finalizing the container), so an immediate delete can
            # fail with "file in use" - retry briefly before giving up.
            deleted = False
            last_error = None
            for attempt in range(5):
                try:
                    os.remove(output_path)
                    deleted = True
                    break
                except OSError as e:
                    last_error = e
                    time.sleep(0.5)
            if deleted:
                self.log(f"[Monitor] Discarded clip under {min_seconds}s: {output_path}")
            else:
                self.log(f"[Monitor] Failed to discard tiny clip {output_path}: {last_error}")
        elif output_path and self.offloader is not None:
            # A real clip that we're keeping: hand it to the NAS offloader (a
            # no-op unless nas_offload_root is configured). This only queues -
            # the copy/verify/delete happens on the offloader's own thread, so
            # it never delays the monitor loop.
            self.offloader.queue(output_path, prev_name)

        self._recording_started_at = None
        self._auto_paused = False  # a stop finalizes the file; any pause state is moot
        time.sleep(0.3)  # OBS needs a moment to fully settle after stopping
        return True

    def _make_target(self, pid, exe_path, display_name):
        basename = os.path.basename(exe_path).lower()
        folder = os.path.join(self.config["recording_root"], sanitize_folder_name(display_name))
        return (pid, basename, display_name, folder)

    def _current_target_still_running(self):
        """Sticky check: is the game we're currently locked onto still
        alive? Compares exe path too, not just PID, since Windows can reuse
        a PID after the original process exits."""
        if not self._recording_target:
            return False
        pid, basename, _, _ = self._recording_target
        exe_path, _ = _process_info(pid)
        return exe_path is not None and os.path.basename(exe_path).lower() == basename

    def _recording_gate_open(self, basename):
        """For session-gated apps (Moonlight), recording should only start/
        continue while a session is actually live - not just because the app
        is open at its menu. Returns True (record) for all normal games."""
        gate = SESSION_GATES.get(basename)
        if gate is None:
            return True
        result = gate()
        return True if result is None else result  # None == "can't tell", assume live

    def _find_new_game_target(self):
        """Pick a game to lock onto: prefer the foreground window, falling
        back to scanning all visible windows if the foreground one isn't a
        classified game (e.g. a launcher briefly has focus while the game
        itself is still loading). A session-gated app (Moonlight) is only
        picked up once its session is actually live, so we don't start
        recording its idle host-list menu."""
        fg = get_foreground_window_info()
        if fg:
            pid, exe_path, proc_name, title, cls = fg
            result, display_name = self.classifier.classify(exe_path, proc_name)
            if result == "game" and self._recording_gate_open(os.path.basename(exe_path).lower()):
                return self._make_target(pid, exe_path, display_name)

        for pid, exe_path, proc_name, title, cls in list_visible_windows():
            result, display_name = self.classifier.classify(exe_path, proc_name)
            if result == "game":
                if self._recording_gate_open(os.path.basename(exe_path).lower()):
                    return self._make_target(pid, exe_path, display_name)
            elif result == "unknown":
                basename = os.path.basename(exe_path).lower()
                if self.classifier.queue_for_manual_review(basename):
                    self.log(f"[Monitor] Unrecognized app awaiting review: {basename}")
        return None

    def _ensure_paused(self, reason="idle"):
        """The game's still open but recording should pause in place rather
        than stop (you went idle, or a session-gated app like Moonlight
        dropped its stream) - resuming continues the same file instead of
        starting a fresh clip."""
        if self._auto_paused:
            return
        self._auto_paused = True
        try:
            status = self.obs.get_record_status()
            if status.get("outputActive") and not status.get("outputPaused"):
                self.obs.pause_record()
                name = self._recording_target[2] if self._recording_target else "unknown"
                detail = "idle" if reason == "idle" else "session ended"
                self.log(f"[OBS] Paused recording ({name}) - {detail}.")
                self.on_notify("pause", name)
        except OBSError as e:
            self.log(f"[OBS] Failed to pause: {e}")

    def _ensure_resumed(self):
        if not self._auto_paused:
            return
        self._auto_paused = False
        try:
            status = self.obs.get_record_status()
            if status.get("outputActive") and status.get("outputPaused"):
                self.obs.resume_record()
                name = self._recording_target[2] if self._recording_target else "unknown"
                self.log(f"[OBS] Resumed recording ({name}).")
                self.on_notify("resume", name)
        except OBSError as e:
            self.log(f"[OBS] Failed to resume: {e}")

    def _retarget_game_capture(self, exe_path):
        """Point the shared dynamic Game Capture source at this window, so
        OBS's video output shows the right game without needing a
        hand-maintained source per game."""
        info = None
        for pid, path, proc_name, title, cls in list_visible_windows():
            if path == exe_path:
                info = (title, cls, os.path.basename(path))
                break
        if not info:
            return
        title, cls, exe = info
        window_id = encode_obs_window_id(title, cls, exe)
        try:
            self.obs.set_input_settings(
                GAME_CAPTURE_INPUT_NAME, {"capture_mode": "window", "window": window_id},
            )
        except OBSError as e:
            self.log(f"[OBS] Failed to retarget game capture: {e}")

    def _apply_target(self, target):
        if target == self._recording_target:
            return

        prev_name = self._recording_target[2] if self._recording_target else "unknown"
        if not self._stop_current_recording(prev_name):
            return  # still out of sync with OBS - don't touch _recording_target, retry next tick

        if target is not None:
            _, _, display_name, folder = target
            os.makedirs(folder, exist_ok=True)
            started = False
            last_error = None
            for attempt in range(3):
                try:
                    self._retarget_game_capture(_process_info(target[0])[0])
                    self.obs.set_record_directory(folder)
                    self.obs.start_record()
                    started = True
                    break
                except OBSError as e:
                    last_error = e
                    self.log(f"[OBS] Start failed (attempt {attempt + 1}): {e}")
                    time.sleep(0.5)
            if started:
                self._recording_started_at = time.time()
                self.log(f"[OBS] Recording started: {display_name} -> {folder}")
                self.on_state(game=display_name, folder=folder)
                self.on_notify("start", display_name)
            else:
                self.log(f"[OBS] Giving up on start after retries: {last_error}")
                target = None
        else:
            self.on_state(game=None, folder=None)

        self._recording_target = target

    # A target change only takes effect once it's been seen this many
    # consecutive polls in a row. Closing a game (especially Unity ones with
    # a crash-handler process) can leave its window flickering in and out of
    # existence for a couple of seconds during teardown; without this, that
    # flicker caused several rapid stop/start cycles - and several tiny
    # leftover clips - for what should have been one clean stop.
    DEBOUNCE_TICKS = 2

    def _maybe_reconnect(self):
        """If OBS crashes/closes mid-session, the websocket recv loop
        detects it and self.obs.connected goes False - but nothing
        previously tried to get it back. This recovers automatically
        instead of requiring the user to restart the app."""
        if self.obs.connected:
            if self._was_disconnected:
                self._was_disconnected = False
                self.on_connection_change(True)
                self.log("[OBS] Connection restored.")
            return True

        if not self._was_disconnected:
            self._was_disconnected = True
            self._recording_target = None  # OBS lost whatever it was doing; don't assume state
            self.on_connection_change(False)
            self.log("[OBS] Connection lost - will keep trying to reconnect.")

        now = time.time()
        interval = self.config.get("reconnect_interval_seconds", 10)
        if now - self._last_reconnect_attempt < interval:
            return False
        self._last_reconnect_attempt = now

        ensure_obs_running(self.config.get("obs_path"), log=self.log)
        try:
            self.obs.connect()
        except Exception as e:
            self.log(f"[OBS] Reconnect attempt failed: {e}")
        return self.obs.connected

    def _loop(self):
        while self._running:
            try:
                if not self._maybe_reconnect():
                    time.sleep(self.config["poll_interval_seconds"])
                    continue

                idle_for = get_idle_duration()
                is_idle = idle_for >= self.config["idle_timeout_seconds"]
                game_still_running = self._current_target_still_running()
                is_gated = (
                    game_still_running
                    and self._recording_target is not None
                    and self._recording_target[1] in SESSION_GATES
                )

                if is_gated:
                    # For a session-gated app (Moonlight) local idle is
                    # meaningless - your keyboard/mouse input is being sent to
                    # the remote host, so GetLastInputInfo reports you idle
                    # even while you're actively playing. So ignore idle
                    # entirely and pause ONLY when the stream itself drops.
                    should_pause = not self._recording_gate_open(self._recording_target[1])
                    pause_reason = "session"
                else:
                    should_pause = is_idle
                    pause_reason = "idle"

                # Discord (or any configured app) producing audio is a
                # keep-alive: if friends are talking in a voice call, don't
                # auto-pause even when otherwise idle. Grace-windowed so gaps
                # between words don't flicker it off.
                if should_pause and self._audio_keep_alive.active():
                    should_pause = False

                # The GUI "Idle" pill reflects whether recording is actually
                # being held idle, not just the raw local input timer - so it
                # won't read "idle" while a stream or a voice call keeps it live.
                self.on_state(idle=should_pause)

                if game_still_running and should_pause:
                    # Pause in place rather than stopping - the game's still
                    # open. Resuming continues the same file instead of
                    # starting a new clip. Skip target resolution this tick.
                    self._ensure_paused(reason=pause_reason)
                    self._pending_target = _UNSET
                    self._pending_count = 0
                    time.sleep(self.config["poll_interval_seconds"])
                    continue

                if self._auto_paused:
                    self._ensure_resumed()

                if game_still_running:
                    target = self._recording_target
                elif is_idle:
                    target = None  # idle and the game actually closed - stop for real
                else:
                    target = self._find_new_game_target()

                if target == self._recording_target:
                    self._pending_target = _UNSET
                    self._pending_count = 0
                else:
                    if target == self._pending_target:
                        self._pending_count += 1
                    else:
                        self._pending_target = target
                        self._pending_count = 1
                    if self._pending_count >= self.DEBOUNCE_TICKS:
                        self._apply_target(target)
                        self._pending_target = _UNSET
                        self._pending_count = 0
            except Exception as e:  # keep the loop alive no matter what
                self.log(f"[Monitor] Error: {e}")
            time.sleep(self.config["poll_interval_seconds"])
