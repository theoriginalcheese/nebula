"""Detect whether a given app (Discord) is currently *producing* audio, used
as a keep-alive: if your friends are talking in a voice call, recording
shouldn't auto-pause even if you're locally idle.

Uses the Windows Core Audio (WASAPI) per-session peak meter via pycaw - the
same value the volume mixer shows bouncing next to each app. A peak above a
small threshold means that app is actively playing sound right now. A short
grace window smooths over the natural gaps between words/sentences so a live
conversation doesn't flicker the keep-alive off mid-sentence.
"""

import time

try:
    import comtypes
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
    _PYCAW_AVAILABLE = True
except Exception:  # pragma: no cover - pycaw/comtypes missing or import failure
    _PYCAW_AVAILABLE = False


class AudioKeepAlive:
    def __init__(self, process_names, grace_seconds=25, threshold=0.0009, on_log=None):
        # store lowercased for case-insensitive matching
        self.process_names = {n.lower() for n in process_names}
        self.grace_seconds = grace_seconds
        self.threshold = threshold
        self.on_log = on_log or (lambda msg: None)
        self._last_heard = 0.0
        self._com_ready = False

    def _ensure_com(self):
        # The monitor loop runs in a daemon thread; COM must be initialized
        # in that thread before enumerating audio sessions.
        if not self._com_ready:
            try:
                comtypes.CoInitialize()
            except Exception:
                pass
            self._com_ready = True

    def _audio_playing_now(self):
        if not _PYCAW_AVAILABLE:
            return False
        self._ensure_com()
        try:
            sessions = AudioUtilities.GetAllSessions()
        except Exception as e:
            self.on_log(f"[Audio] Session enumeration failed: {e}")
            return False
        for session in sessions:
            proc = session.Process
            if not proc:
                continue
            try:
                name = proc.name().lower()
            except Exception:
                continue
            if name not in self.process_names:
                continue
            try:
                meter = session._ctl.QueryInterface(IAudioMeterInformation)
                if meter.GetPeakValue() >= self.threshold:
                    return True
            except Exception:
                continue
        return False

    def active(self):
        """True if the watched app is producing sound now, or did within the
        recent grace window (so gaps between spoken words don't drop it)."""
        if self._audio_playing_now():
            self._last_heard = time.time()
            return True
        return (time.time() - self._last_heard) < self.grace_seconds
