"""Instant replay - spec 7a.

    "A rolling buffer OBS already keeps in RAM. One key writes the last N
     seconds to disk with no session recording running. Nebula's job is to arm
     the buffer when a game is detected, name the saved file, and confirm it."

The division of labour matters: OBS owns the video the whole time. This module
arms and disarms the buffer, asks for a save, and then *moves* what OBS wrote
into the right per-game folder. It never copies (the spec is explicit) and never
holds a frame itself.

Replays deliberately bypass `min_clip_seconds` - "they are intentional by
definition" - so the auto-cull that discards a six-second accident can't touch
one you asked for.
"""

import os
import shutil
import threading
import time

from . import session_log
from .obs_client import OBSError

DEFAULTS = {
    "replay_enabled": True,
    "replay_seconds": 30,               # 10-300
    "replay_hotkey": "f9",
    "replay_hotkey_scancode": 67,
    "replay_subfolder": "Replays",
    "replay_arm_with_monitoring": True,
    "replay_only_for_games": True,
}

SECONDS_RANGE = (10, 300)
RAM_WARN_MB = 2048                      # "Warn above 2 GB"


def ram_estimate_mb(bitrate_mbps, seconds):
    """"MB ≈ (bitrate_mbps / 8) × seconds × 1.1"  - the spec's formula, exactly.

    Shown live beside the duration so that raising the buffer has a visible
    cost rather than being a number that quietly eats a couple of gigabytes.
    """
    if not bitrate_mbps or not seconds:
        return None
    return (bitrate_mbps / 8.0) * seconds * 1.1


def clamp_seconds(value):
    lo, hi = SECONDS_RANGE
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return DEFAULTS["replay_seconds"]


class ReplayBuffer:
    """Arms OBS's replay buffer and files what it saves.

    `on_saved(path, game)` and `on_state(armed)` are called from whichever
    thread the event arrived on - both callers marshal onto Tk themselves.
    """

    def __init__(self, obs, config, on_log=None, on_saved=None, on_state=None):
        self.obs = obs
        self.config = config
        self.log = on_log or (lambda msg: None)
        self.on_saved = on_saved or (lambda path, game: None)
        self.on_state = on_state or (lambda armed: None)
        self.armed = False
        self.saved_this_session = []     # [(path, when)] newest last
        self._game = None
        self._lock = threading.Lock()
        self._last_error = None
        # Set by handle_event when OBS announces a finished file. save() waits
        # on it before restoring a lifted recording pause - see _save_around_pause.
        self._saved_event = threading.Event()

    # ---- configuration -----------------------------------------------------
    @property
    def enabled(self):
        return bool(self.config.get("replay_enabled", DEFAULTS["replay_enabled"]))

    @property
    def seconds(self):
        return clamp_seconds(self.config.get("replay_seconds",
                                             DEFAULTS["replay_seconds"]))

    @property
    def subfolder(self):
        return (self.config.get("replay_subfolder")
                or DEFAULTS["replay_subfolder"])

    def push_length_to_obs(self):
        """Tell OBS how long the buffer should be.

        SetProfileParameter on SimpleOutput/RecRBTime, per the spec's table.
        Only meaningful before the buffer starts - OBS allocates the ring on
        StartReplayBuffer - so this runs first in arm().
        """
        try:
            self.obs.set_profile_parameter("SimpleOutput", "RecRB", "true")
            self.obs.set_profile_parameter("SimpleOutput", "RecRBTime", self.seconds)
            return True
        except OBSError as exc:
            self._last_error = str(exc)
            return False

    # ---- arming ------------------------------------------------------------
    # OBS answers "Replay buffer is not available" when the output doesn't
    # exist at all - i.e. it isn't enabled in the profile. That is a different
    # thing from a transient failure, and 7a gives it its own UI: "Replay
    # buffer is off in OBS / Nebula can switch it on for you / [Enable]".
    UNAVAILABLE = "not available"

    @property
    def unavailable(self):
        """True when OBS has no replay-buffer output to arm."""
        return bool(self._last_error and self.UNAVAILABLE in self._last_error.lower())

    def arm(self, game=None):
        """"StartReplayBuffer on game detected, or with monitoring"."""
        if not self.enabled or not self.obs.connected:
            return False
        with self._lock:
            self._game = game or self._game
            if self.armed:
                return True
            self.push_length_to_obs()
            try:
                if not self.obs.get_replay_buffer_status():
                    self.obs.start_replay_buffer()
                self.armed = True
                self._last_error = None
            except OBSError as exc:
                # Bind before the closure/logging - `exc` is unbound once this
                # block exits (CLAUDE.md).
                error = str(exc)
                self._last_error = error
                self.armed = False
        if not self.armed:
            if self.unavailable:
                self.log("[Replay] OBS has no replay buffer enabled. Turn it on "
                         "from the dashboard, or in OBS: Settings -> Output -> "
                         "Recording -> Enable Replay Buffer.")
            else:
                self.log(f"[Replay] Couldn't arm the buffer: {self._last_error}")
        self.on_state(self.armed)
        if self.armed:
            self.log(f"[Replay] Buffer armed - last {self.seconds}s held in RAM.")
        return self.armed

    def enable_in_obs(self):
        """Turn the replay buffer on in OBS's profile, then arm it.

        7a's inline fix. SetProfileParameter alone isn't enough - OBS only
        creates the output when the profile setting is applied, which is why
        arming right after a fresh RecRB=true still reports "not available".
        Both Simple and Advanced output modes are set, since which one is live
        depends on the user's OBS configuration and neither costs anything.
        """
        if not self.obs.connected:
            return False
        try:
            self.obs.set_profile_parameter("SimpleOutput", "RecRB", "true")
            self.obs.set_profile_parameter("SimpleOutput", "RecRBTime", self.seconds)
            self.obs.set_profile_parameter("AdvOut", "RecRB", "true")
            self.obs.set_profile_parameter("AdvOut", "RecRBTime", self.seconds)
        except OBSError as exc:
            error = str(exc)
            self.log(f"[Replay] Couldn't enable the buffer in OBS: {error}")
            return False
        self._last_error = None
        if self.arm():
            return True
        # The profile is set but OBS hasn't instantiated the output yet; it
        # picks it up on the next profile load. Say so rather than silently
        # failing, because from the outside the button just wouldn't work.
        self.log("[Replay] Enabled in OBS's profile. OBS needs a restart before "
                 "the buffer actually exists.")
        return False

    def disarm(self):
        """"StopReplayBuffer: monitoring off, or non-game focus"."""
        with self._lock:
            if not self.armed:
                return
            self.armed = False
            try:
                self.obs.stop_replay_buffer()
            except OBSError as exc:
                self.log(f"[Replay] Couldn't stop the buffer: {exc}")
        self.on_state(False)
        self.log("[Replay] Buffer disarmed.")

    def refresh_from_obs(self):
        """"GetReplayBufferStatus: poll on connect to set the badge"."""
        if not self.obs.connected:
            return False
        try:
            self.armed = self.obs.get_replay_buffer_status()
        except OBSError:
            self.armed = False
        self.on_state(self.armed)
        return self.armed

    def set_game(self, game):
        self._game = game

    # ---- saving ------------------------------------------------------------
    # How long to wait for OBS to announce the written file before restoring a
    # pause we lifted. The ReplayBufferSaved event is the expected route; this
    # is the fallback for when it never comes, so the recording can't be left
    # running because one event went missing.
    SAVE_FLUSH_S = 5.0

    def save(self):
        """One key, one clip. Returns True if OBS accepted the request.

        The file itself lands later, via handle_event - OBS finishes writing
        before it announces the path.
        """
        if not self.armed:
            self.log("[Replay] Nothing to save - the buffer isn't armed.")
            return False
        # OBS refuses SaveReplayBuffer outright while the recording is paused:
        # in Simple output mode the buffer shares the recording's encoder, and a
        # paused encoder has nothing to hand it. That is exactly when you want a
        # replay, though - you pressed the key, and 7a calls replays
        # "intentional by definition" - so the pause is lifted for the write and
        # then put back exactly as it was.
        #
        # Restoring it is what keeps this honest with the monitor: an idle
        # auto-pause leaves `Monitor._auto_paused` set, and if the recording
        # came back unpaused behind its back, _ensure_paused() would see the
        # flag already true and never pause again for the rest of the session.
        if self._recording_paused():
            threading.Thread(target=self._save_around_pause, daemon=True).start()
            return True
        return self._request_save()

    def _recording_paused(self):
        """True only if a recording is live AND paused."""
        try:
            status = self.obs.get_record_status()
        except OBSError:
            return False
        return bool(status.get("outputActive") and status.get("outputPaused"))

    def _request_save(self):
        try:
            self.obs.save_replay_buffer()
            return True
        except OBSError as exc:
            error = str(exc)
            self.log(f"[Replay] Save failed: {error}")
            return False

    def _save_around_pause(self):
        """Resume, save, wait for the file, re-pause.

        On a worker thread rather than inline: the callers are the hotkey, the
        tray and the mini overlay, all on the Tk thread, and this deliberately
        blocks for as long as OBS takes to write the clip.
        """
        self._saved_event.clear()
        try:
            self.obs.resume_record()
        except OBSError as exc:
            error = str(exc)
            self.log(f"[Replay] Couldn't lift the recording pause to save: {error}")
            return
        self.log("[Replay] Recording was paused - resumed to write the buffer.")
        saved = self._request_save()
        if saved:
            self._saved_event.wait(self.SAVE_FLUSH_S)
        try:
            self.obs.pause_record()
            self.log("[Replay] Recording paused again.")
        except OBSError as exc:
            error = str(exc)
            self.log(f"[Replay] Saved, but couldn't restore the recording pause: {error}")

    def handle_event(self, event_type, data):
        """OBS event hook. Only ReplayBufferSaved is interesting."""
        if event_type == "ReplayBufferSaved":
            # Before _file(), so a slow move can't hold the pause open.
            self._saved_event.set()
            self._file(data.get("savedReplayPath"))
        elif event_type == "ReplayBufferStateChanged":
            active = bool(data.get("outputActive"))
            if active != self.armed:
                self.armed = active
                self.on_state(active)

    def target_dir(self, game=None):
        root = self.config.get("recording_root", "")
        return os.path.join(root, game or self._game or "Unsorted", self.subfolder)

    def _file(self, source):
        """Move OBS's output into <recording_root>/<Game>/Replays/.

        "Move, never copy - OBS writes to its own output dir first." A copy
        would leave a duplicate behind and double the disk cost of every
        replay, and the offloader would then see two files for one clip.
        """
        if not source or not os.path.exists(source):
            self.log("[Replay] OBS reported a save but the file wasn't there.")
            return None
        game = self._game or "Unsorted"
        folder = self.target_dir(game)
        stamp = time.strftime("%Y-%m-%d %H-%M-%S")
        target = os.path.join(folder, stamp + os.path.splitext(source)[1])
        try:
            os.makedirs(folder, exist_ok=True)
            # os.replace won't cross a volume; shutil.move falls back to a copy
            # plus unlink, which still leaves one file at the end.
            shutil.move(source, target)
        except OSError as exc:
            error = str(exc)
            self.log(f"[Replay] Couldn't file the replay: {error}")
            return None
        self.saved_this_session.append((target, time.time()))
        self.log(f"[Replay] Saved the last {self.seconds}s -> {target}")
        # Replays bypass min_clip_seconds, so this is always a kept clip.
        session_log.append("rec_stop", game=game, path=target,
                           duration=self.seconds, replay=True,
                           size=_size_of(target))
        self.on_saved(target, game)
        return target


def _size_of(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None
