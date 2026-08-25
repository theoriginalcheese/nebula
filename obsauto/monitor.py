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

Exception: while Discord has an *active voice/video call* (see
``discord_detect.discord_voice_active``), a game switch does **not** stop the
recording. Capture is retargeted in place and ``SetRecordDirectory`` points at
the new game's folder for any subsequent segment OBS opens. When the call ends
and no game is in focus, idle/stop behaviour resumes as usual.
"""

import ctypes
import os
import re
import subprocess
import threading
import time

import psutil

from . import app_icons
from . import profiles
from . import session_log

try:
    import win32gui
    import win32process
except ImportError:  # pragma: no cover
    win32gui = None
    win32process = None

from .obs_client import OBSError
from . import discord_detect
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


def obs_launch_task_exists():
    """True when the one-time NebulaLaunchOBS task is registered."""
    try:
        from .silent_proc import run_kwargs
        result = subprocess.run(
            ["schtasks", "/query", "/tn", OBS_LAUNCH_TASK_NAME],
            capture_output=True, text=True, timeout=8,
            **run_kwargs(),
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


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
        from .silent_proc import run_kwargs
        result = subprocess.run(
            ["schtasks", "/run", "/tn", OBS_LAUNCH_TASK_NAME],
            capture_output=True, text=True, timeout=10,
            **run_kwargs(),
        )
        if result.returncode == 0:
            return True
        err = (result.stderr or result.stdout or "").strip().replace("\n", " ")
        if err:
            log("[OBS] Scheduled task %s did not run: %s"
                % (OBS_LAUNCH_TASK_NAME, err[:240]))
        return False
    except (OSError, subprocess.TimeoutExpired) as exc:
        log("[OBS] Scheduled task %s: %s" % (OBS_LAUNCH_TASK_NAME, exc))
        return False


def _wait_for_obs(timeout, log):
    """OBS's process can take several seconds to appear after schtasks / Popen."""
    deadline = time.monotonic() + max(0.5, float(timeout))
    while time.monotonic() < deadline:
        if is_obs_running():
            return True
        time.sleep(0.35)
    return is_obs_running()


def ensure_obs_running(obs_path, log=lambda msg: None, wait=20.0):
    """Launch OBS if it isn't already running. Used both for the initial
    connection (in case OBS isn't set to autostart with Windows) and for
    recovering after OBS crashes/closes mid-session.

    Prefers the elevated scheduled task (no UAC). Falls back to a normal
    ``Popen`` only if that task is missing — that path is not admin and
    will UAC or fail with WinError 740 if OBS is set to run as admin.
    """
    if is_obs_running():
        return True
    launched = False
    if _launch_via_scheduled_task(log):
        log("[OBS] Asked scheduled task %s to start OBS (elevated, no UAC)."
            % OBS_LAUNCH_TASK_NAME)
        launched = True
    elif not obs_launch_task_exists():
        log("[OBS] Scheduled task %s is missing — OBS cannot start elevated "
            "without a UAC prompt. Run scripts/setup-obs-elevated-task.ps1 "
            "once (approve UAC that one time)." % OBS_LAUNCH_TASK_NAME)
    if not launched:
        if not obs_path or not os.path.exists(obs_path):
            log("[OBS] obs_path is missing or not a file: %r" % (obs_path,))
            return False
        try:
            # --minimize-to-tray is OBS's own supported flag for this - more
            # reliable than fighting window state externally via CreateProcess
            # show flags, which OBS's own startup routine can just override.
            subprocess.Popen(
                [obs_path, "--minimize-to-tray"],
                cwd=os.path.dirname(obs_path),
            )
            log("[OBS] Launched OBS (minimized, not elevated) from %s" % obs_path)
            launched = True
        except OSError as e:
            log("[OBS] Failed to launch OBS: %s" % e)
            if getattr(e, "winerror", None) == 740:
                log("[OBS] Windows refused a non-elevated start (error 740). "
                    "Run scripts/setup-obs-elevated-task.ps1 once so Nebula "
                    "can start OBS as admin without a prompt.")
            return False
    if launched and _wait_for_obs(wait, log):
        return True
    if launched:
        log("[OBS] OBS did not appear within %.0fs; websocket connect will retry."
            % wait)
    return is_obs_running()


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
    # Nebula's own windows, and the OBS it drives. Never worth reporting as
    # "the foreground that isn't a game".
    SELF_PROCESSES = {"nebula.exe", "python.exe", "pythonw.exe",
                      "obs64.exe", "obs32.exe"}

    # After a manual Stop, wait this long before offering "record again?" for
    # the same game. A different game prompts as soon as it debounces in.
    HOLDOFF_SAME_GAME_SECONDS = 60
    # After a natural game-process exit, quiet window before auto-recording
    # that same basename again. Other games are unaffected.
    REOPEN_COOLDOWN_SECONDS = 30

    def __init__(self, obs_client, classifier, config, on_log=None, on_state=None, on_notify=None,
                 on_connection_change=None, offloader=None, on_record_prompt=None):
        self.obs = obs_client
        self.classifier = classifier
        self.config = config
        self.offloader = offloader  # optional NAS offloader; None = feature off
        self.on_log = on_log or (lambda msg: None)
        self.on_state = on_state or (lambda **kwargs: None)  # game, folder, idle
        self.on_notify = on_notify or (lambda event, display_name, details=None: None)  # event: "start"|"stop"|"pause"|"resume"
        self.on_connection_change = on_connection_change or (lambda connected: None)
        # Fired when hold-off wants the UI to ask "Record again?" / "Record X?".
        # Args: basename, display_name, reason ("same"|"switch"), target tuple.
        self.on_record_prompt = on_record_prompt or (lambda *a, **k: None)
        self._running = False
        self._thread = None
        self._recording_target = None  # (pid, basename, display_name, folder, window_id) or None
        self._pending_target = _UNSET
        self._pending_count = 0
        self._recording_started_at = None
        self._last_reconnect_attempt = 0.0
        self._was_disconnected = False
        self._auto_paused = False
        # Manual-stop hold-off: suppress auto StartRecord until the user
        # confirms via toast, starts recording manually, or the held games exit.
        self._hold_off = False
        self._hold_off_since = 0.0
        self._hold_off_basename = None   # game that was recording when Stop hit
        self._hold_off_skip = set()      # basenames the user said "Not now" to
        self._hold_off_prompted = None   # basename we last prompted for
        self._hold_off_pending = None    # full target tuple awaiting Accept
        # Natural close: same-game reopen quiet window (no prompt).
        self._reopen_cooldown_basename = None
        self._reopen_cooldown_until = 0.0
        self._last_foreground = None   # so the hero's foreground line only fires on change
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
        self.clear_hold_off()
        self.clear_reopen_cooldown()
        self.log("[Monitor] Stopped.")

    def clear_reopen_cooldown(self):
        was = self._reopen_cooldown_basename
        self._reopen_cooldown_basename = None
        self._reopen_cooldown_until = 0.0
        if was:
            self.log(f"[Monitor] Same-game reopen cooldown cleared ({was}).")

    def _arm_reopen_cooldown(self, basename):
        needle = (basename or "").lower()
        if not needle:
            return
        wait = float(self.config.get(
            "same_game_reopen_cooldown_seconds", self.REOPEN_COOLDOWN_SECONDS))
        if wait <= 0:
            return
        self._reopen_cooldown_basename = needle
        self._reopen_cooldown_until = time.time() + wait
        self.log(f"[Monitor] Same-game reopen cooldown {wait:.0f}s for {needle}.")

    def _reopen_cooldown_active(self, basename):
        needle = (basename or "").lower()
        if not needle or not self._reopen_cooldown_basename:
            return False
        if needle != self._reopen_cooldown_basename:
            return False
        if time.time() >= self._reopen_cooldown_until:
            self.clear_reopen_cooldown()
            return False
        return True

    def note_manual_stop(self, basename=None, display_name=None):
        """UI clicked Stop. Suppress auto-restart until confirm / exit / clear."""
        if not basename:
            # Runs on the Tk thread (marshalled from the Stop button), so the
            # lookup must be cache-only: peek() never triggers the lazy Steam
            # scan whose synchronous Store request would freeze the UI.
            hinted = self._find_new_game_target(peek_only=True)
            if hinted is not None:
                basename, display_name = hinted[1], hinted[2]
        self._hold_off = True
        self._hold_off_since = time.time()
        self._hold_off_basename = (basename or "").lower() or None
        self._hold_off_skip.clear()
        self._hold_off_prompted = None
        self._hold_off_pending = None
        self._pending_target = _UNSET
        self._pending_count = 0
        label = display_name or basename or "manual"
        self.log(f"[Monitor] Hold-off after manual stop ({label}).")

    def clear_hold_off(self):
        was = self._hold_off
        self._hold_off = False
        self._hold_off_since = 0.0
        self._hold_off_basename = None
        self._hold_off_skip.clear()
        self._hold_off_prompted = None
        self._hold_off_pending = None
        if was:
            self.log("[Monitor] Hold-off cleared.")

    def accept_record_prompt(self):
        """User tapped Record on the hold-off toast — start the pending game."""
        target = self._hold_off_pending
        self.clear_hold_off()
        self.clear_reopen_cooldown()
        if target is None:
            return False
        self._pending_target = _UNSET
        self._pending_count = 0
        if target == self._recording_target:
            self._recording_target = None
        self._apply_target(target)
        return True

    def dismiss_record_prompt(self, basename=None):
        """User tapped Not now — don't re-ask for this game until it exits."""
        needle = (basename or (self._hold_off_pending[1] if self._hold_off_pending else "")
                  or "").lower()
        if needle:
            self._hold_off_skip.add(needle)
            self.log(f"[Monitor] Hold-off: skipped {needle} until it exits.")
        self._hold_off_prompted = needle or self._hold_off_prompted
        self._hold_off_pending = None

    @staticmethod
    def _basename_running(basename):
        needle = (basename or "").lower()
        if not needle:
            return False
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info.get("name") or ""
                if name.lower() == needle:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def _refresh_hold_off(self):
        """Drop exited skip entries; resume normal auto-record when nothing left."""
        if not self._hold_off:
            return
        self._hold_off_skip = {b for b in self._hold_off_skip if self._basename_running(b)}
        if self._hold_off_basename and not self._basename_running(self._hold_off_basename):
            self._hold_off_basename = None
        if not self._hold_off_basename and not self._hold_off_skip:
            self.clear_hold_off()

    def _maybe_prompt_hold_off(self, target):
        """Ask the UI once per game whether to start recording under hold-off."""
        if target is None:
            return
        basename = (target[1] or "").lower()
        display = target[2]
        if not basename or basename in self._hold_off_skip:
            return
        same = self._hold_off_basename and basename == self._hold_off_basename
        if same:
            wait = float(self.config.get(
                "holdoff_same_game_seconds", self.HOLDOFF_SAME_GAME_SECONDS))
            if time.time() - self._hold_off_since < wait:
                return
            reason = "same"
        else:
            reason = "switch"
        if self._hold_off_prompted == basename:
            return
        self._hold_off_prompted = basename
        self._hold_off_pending = target
        try:
            self.on_record_prompt(basename, display, reason, target)
        except Exception as e:
            self.log(f"[Monitor] Record prompt failed: {e}")

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
        # One rec_stop either way, flagged with whether the clip survived. The
        # dashboard's "Auto-culled" tile counts the flagged ones (6.3), and 7c's
        # forecast needs the sizes of the ones that didn't get culled.
        session_log.append("rec_stop", game=prev_name, path=output_path,
                           duration=elapsed, size=file_size,
                           culled=True if too_short else None)

        if not too_short and output_path and self.offloader is not None:
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
        # The one place a full path and a basename are both in hand. The Games
        # pane needs the path to draw the app's real icon, and it deliberately
        # cannot live in games.json - that file syncs across machines and a
        # path does not. See obsauto/app_icons.py.
        app_icons.remember(exe_path)
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

    def _find_new_game_target(self, peek_only=False):
        """Pick a game to lock onto: prefer the foreground window, falling
        back to scanning all visible windows if the foreground one isn't a
        classified game (e.g. a launcher briefly has focus while the game
        itself is still loading). A session-gated app (Moonlight) is only
        picked up once its session is actually live, so we don't start
        recording its idle host-list menu.

        ``peek_only`` (UI thread): classify from cache only — no Steam scan,
        no network, and no manual-review queueing.
        """
        classify = self.classifier.peek if peek_only else self.classifier.classify
        fg = get_foreground_window_info()
        if fg:
            pid, exe_path, proc_name, title, cls = fg
            result, display_name = classify(exe_path, proc_name)
            if result == "game" and self._recording_gate_open(os.path.basename(exe_path).lower()):
                return self._make_target(pid, exe_path, display_name)
            # Nothing to record here, but the idle hero says what it is looking
            # at rather than a bare "no game detected" (6.6). Reported only when
            # it changes - this loop runs once a second.
            # Never report ourselves. Alt-tabbing to Nebula makes Nebula the
            # foreground window, and "Foreground: Nebula.exe - classified as
            # not a game" is both useless and slightly absurd: the line is
            # meant to explain what Nebula is looking at instead of a game.
            # OBS is excluded for the same reason - Nebula launched it.
            if (proc_name and proc_name != self._last_foreground
                    and proc_name.lower() not in self.SELF_PROCESSES):
                self._last_foreground = proc_name
                self.on_state(foreground=(proc_name, result))

        for pid, exe_path, proc_name, title, cls in list_visible_windows():
            result, display_name = classify(exe_path, proc_name)
            if result == "game":
                if self._recording_gate_open(os.path.basename(exe_path).lower()):
                    return self._make_target(pid, exe_path, display_name)
            elif result == "unknown":
                if peek_only:
                    continue
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
                self.on_notify("pause", name, {"reason": reason})
                session_log.append("idle_in", game=name, reason=reason)
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
                session_log.append("idle_out", game=name)
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

    def _retarget_live(self, target):
        """Keep the current recording open; point capture + directory at a new game.

        Used only while Discord has an active call. Does not stop/start OBS, so
        friends on the call don't hear a hard cut. The open file stays where it
        was started; SetRecordDirectory affects any later segment OBS opens.
        """
        if target is None or target == self._recording_target:
            return
        prev = self._recording_target
        prev_name = prev[2] if prev else "unknown"
        basename, display_name, folder = target[1], target[2], target[3]
        os.makedirs(folder, exist_ok=True)
        try:
            exe_path, _ = _process_info(target[0])
            if not exe_path:
                for _pid, path, _proc, _title, _cls in list_visible_windows():
                    if path and os.path.basename(path).lower() == basename:
                        exe_path = path
                        break
            if exe_path:
                self._retarget_game_capture(exe_path)
        except Exception as e:
            self.log(f"[OBS] Live retarget capture failed: {e}")
        try:
            self.obs.set_record_directory(folder)
        except OBSError as e:
            self.log(f"[OBS] Live retarget directory failed: {e}")
        self._recording_target = target
        self.on_state(game=display_name, folder=folder)
        self.log(
            f"[OBS] Held recording across game switch (Discord call): "
            f"{prev_name} -> {display_name}"
        )

    def _output_active(self):
        """True when OBS is mid-recording (paused counts as still open)."""
        try:
            status = self.obs.get_record_status()
            return bool(status.get("outputActive"))
        except OBSError:
            return False

    def _apply_target(self, target, *, hold_recording=False):
        if target == self._recording_target:
            return

        if (hold_recording and target is not None
                and self._recording_target is not None
                and self._output_active()):
            self._retarget_live(target)
            return

        prev = self._recording_target
        prev_name = prev[2] if prev else "unknown"
        prev_basename = (prev[1] or "").lower() if prev else None
        if not self._stop_current_recording(prev_name):
            return  # still out of sync with OBS - don't touch _recording_target, retry next tick

        # Natural close: previous game process is gone → quiet same-game reopen.
        # Manual Stop clears _recording_target first, so prev is None there.
        if (prev_basename and not hold_recording
                and not self._basename_running(prev_basename)):
            self._arm_reopen_cooldown(prev_basename)

        if target is not None:
            _, _, display_name, folder = target
            os.makedirs(folder, exist_ok=True)

            # 7d's apply sequence: the profile goes on *before* StartRecord.
            # "Never apply mid-recording" is satisfied by construction here -
            # the previous recording was stopped above, and the new one hasn't
            # started yet, which is the one safe window there is.
            exe = os.path.basename(target[1] or "").lower()
            game_profile = profiles.for_game(self.classifier, exe)
            if game_profile:
                profiles.apply(self.obs, game_profile, is_recording=False,
                               on_log=self.log)

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
                if exe == self._reopen_cooldown_basename:
                    self.clear_reopen_cooldown()
                # No appid field: the classifier has no lookup from an exe back
                # to a Steam AppID yet. The event shape allows one, and 7d adds
                # the source; writing a guess in the meantime would be exactly
                # the fabricated data the spec forbids.
                session_log.append("rec_start", game=display_name)
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
                # Active Discord *call* (not merely Discord open). Holds stop
                # across game switches and suppresses idle pause while true.
                in_discord_call = discord_detect.discord_voice_active()
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
                # Active-call signal is stronger than peaks: a muted call with
                # nobody talking still shouldn't idle-pause mid-session.
                if should_pause and in_discord_call:
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

                hold_recording = False
                if in_discord_call and self._recording_target is not None:
                    # Prefer the foreground game so a focus switch to Roblox
                    # while Minecraft is still open actually retargets.
                    candidate = self._find_new_game_target()
                    if candidate is not None:
                        target = candidate
                        hold_recording = True
                    elif game_still_running:
                        target = self._recording_target
                        hold_recording = True
                    else:
                        # Call still live, no game in focus — hold the open
                        # recording until the call ends (do not stop).
                        target = self._recording_target
                        hold_recording = True
                elif game_still_running:
                    target = self._recording_target
                elif is_idle:
                    target = None  # idle and the game actually closed - stop for real
                else:
                    target = self._find_new_game_target()

                self._refresh_hold_off()

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
                        if (self._hold_off and target is not None
                                and self._recording_target is None):
                            # Manual stop is sticky: never auto-StartRecord.
                            # Prompt for a different game immediately, or the
                            # same game after HOLDOFF_SAME_GAME_SECONDS.
                            self._maybe_prompt_hold_off(target)
                            self.on_state(game=target[2], folder=None,
                                          idle=should_pause)
                            self._pending_target = _UNSET
                            self._pending_count = 0
                        elif (target is not None
                                and self._recording_target is None
                                and self._reopen_cooldown_active(target[1])):
                            # Natural close quiet window: same game stays quiet;
                            # other games fall through to _apply_target above.
                            self.on_state(game=target[2], folder=None,
                                          idle=should_pause)
                            self._pending_target = _UNSET
                            self._pending_count = 0
                        else:
                            self._apply_target(target, hold_recording=hold_recording)
                            self._pending_target = _UNSET
                            self._pending_count = 0
            except Exception as e:  # keep the loop alive no matter what
                self.log(f"[Monitor] Error: {e}")
            time.sleep(self.config["poll_interval_seconds"])
