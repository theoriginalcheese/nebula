"""K762 dial menu: knob policy and the one open/close pose.

The window lives in ``spike/windows.py``. This module stays free of WebView
so the swallow rules can be tested without a desktop session.

Volume keys pass through while the menu is closed. The mute press that opens
it is swallowed, and so are the notches while it is open, so Windows volume
does not move under the highlight. Numpad 0 does the same job when Num Lock
is off: Windows reports that face as insert with ``is_keypad`` set. The
dedicated Insert key is left alone, and Num Lock on still types 0.
``note_closed`` is what releases the swallowed keys.
"""
from __future__ import annotations

import threading

# keyboard package names, and the scan codes it reports for these VKs.
# 0xAF / 0xAE / 0xAD. The name tables use the extended scans (57392 and
# friends). The K762 sends scan code 0, and the package rewrites that to
# -vk, so a live notch arrives as -175 / -174 / -173.
VOLUME_UP_SCAN = 57392
VOLUME_DOWN_SCAN = 57390
VOLUME_MUTE_SCAN = 57376
_LIVE_UP = -0xAF
_LIVE_DOWN = -0xAE
_LIVE_MUTE = -0xAD
_SCAN_VK = {
    VOLUME_UP_SCAN: 0xAF,
    VOLUME_DOWN_SCAN: 0xAE,
    VOLUME_MUTE_SCAN: 0xAD,
    _LIVE_UP: 0xAF,
    _LIVE_DOWN: 0xAE,
    _LIVE_MUTE: 0xAD,
}
_BY_NAME = {
    "volume up": "volume_up",
    "volume down": "volume_down",
    "volume mute": "mute",
    "esc": "esc",
    "escape": "esc",
}
_BY_SCAN = {
    VOLUME_UP_SCAN: "volume_up",
    VOLUME_DOWN_SCAN: "volume_down",
    VOLUME_MUTE_SCAN: "mute",
    _LIVE_UP: "volume_up",
    _LIVE_DOWN: "volume_down",
    _LIVE_MUTE: "mute",
}

# Nebula Dial Menu v4.dc.html. Opacity finishes first (180ms). The 8px
# rise finishes at 220ms. Close is both, in 200ms. No overshoot, no row stagger.
OPEN_FADE_MS = 180
OPEN_TRAVEL_MS = 220
OPEN_TOTAL_MS = OPEN_TRAVEL_MS
CLOSE_MS = 200
HIGHLIGHT_MS = 260
ROW_TRAVEL_PX = 38
OPEN_RISE_PX = 8
CLOSE_LEAVE_PX = 8
# Clear the toast, then come back. Same curve as the panel. Long enough
# that an 84px lift (toast plus the corner margin) reads as one glide.
DODGE_MS = 320

# Round 5 likes. One is kept across opens, then a different one is rolled.
# Keys match the canvas painter.
BG_HOLD_S = 10 * 60
POOL = (
    "trail",
    "twin",
    "twinTR",
    "hpatches",
    "hrose",
    "hdusk",
)

# Five, not six. Stop keeps the file. Delete bins the one being recorded,
# and only after a second press. A sixth row would only lengthen the menu.
ROWS = (
    ("show", "Start Nebula"),
    ("pause", "Pause recording"),
    ("stop", "Stop recording"),
    ("replay", "Save replay"),
    ("discard", "Delete this clip"),
)
ROW_COUNT = len(ROWS)
ROW_LABELS = tuple(label for _action, label in ROWS)
DELETE_ROW = next(i for i, (action, _label) in enumerate(ROWS) if action == "discard")
DELETE_CONFIRM = "Press again to delete"


def row_action(index):
    if 0 <= index < len(ROWS):
        return ROWS[index][0]
    return None


def status_word(hero_state):
    """Short live word for the header. Never a hardcoded Recording."""
    if hero_state == "recording":
        return "Recording"
    if hero_state == "paused":
        return "Paused"
    if hero_state == "disconnected":
        return "Offline"
    return "Idle"


def pause_label(output_paused):
    """Middle row. Resume only when OBS says outputPaused."""
    if output_paused:
        return "Resume recording"
    return "Pause recording"


def unit_ease(t):
    """cubic-bezier(.32, .72, 0, 1), the dial's only curve."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return _bezier_y(t, 0.32, 0.72, 0.0, 1.0)


def _bezier_y(t, x1, y1, x2, y2):
    def sample(u, a, b):
        o = 1.0 - u
        return (3.0 * o * o * u * a) + (3.0 * o * u * u * b) + (u * u * u)

    lo, hi = 0.0, 1.0
    for _ in range(20):
        mid = (lo + hi) * 0.5
        if sample(mid, x1, x2) < t:
            lo = mid
        else:
            hi = mid
    return sample((lo + hi) * 0.5, y1, y2)


def pick_background(previous, rng):
    """Avoid-repeat roll from the v4 design. ``rng`` is Math.random: [0, 1)."""
    n = len(POOL)
    if n == 0:
        return None
    try:
        prev = POOL.index(previous)
    except ValueError:
        prev = -1
    if prev < 0 or n < 2:
        choice = int(rng() * n)
        choice = min(n - 1, max(0, choice))
        return POOL[choice]
    choice = int(rng() * (n - 1))
    choice = min(n - 2, max(0, choice))
    if choice >= prev:
        choice += 1
    return POOL[choice]


def background_for_open(previous, chosen_at, now, rng, hold_s=BG_HOLD_S):
    """Keep ``previous`` until the hold has passed, then roll a different one.

    Opening the menu again inside the hold does not change the background.
    ``now`` and ``chosen_at`` are the same clock, in seconds.
    """
    if (previous in POOL and chosen_at is not None
            and (now - chosen_at) < hold_s):
        return previous, chosen_at
    return pick_background(previous, rng), now


def open_pose(ms):
    """Opacity and Y offset in CSS px. Positive Y is down.

    Fade and travel are separate clocks, the way the v4 panel transition
    is written: opacity 180ms, translate 220ms, both the same curve.
    """
    if ms <= 0:
        return 0.0, float(OPEN_RISE_PX)
    fade = unit_ease(min(1.0, ms / float(OPEN_FADE_MS)))
    travel = unit_ease(min(1.0, ms / float(OPEN_TRAVEL_MS)))
    return fade, OPEN_RISE_PX * (1.0 - travel)


def toast_clearance(height_css, margin_css):
    """CSS px to lift the dial so one margin sits between it and a toast."""
    height = float(height_css or 0)
    if height <= 0:
        return 0.0
    return height + float(margin_css or 0)


def dodge_lift(ms, origin, target, duration=DODGE_MS):
    """CSS px of clearance. Same curve as the panel, no overshoot."""
    origin = float(origin)
    target = float(target)
    if duration <= 0 or ms >= duration:
        return target
    if ms <= 0:
        return origin
    eased = unit_ease(ms / float(duration))
    return origin + (target - origin) * eased


def corner_dy(offset_css, lift_css, scale):
    """Physical pixels from the resting corner. Up is negative."""
    return int(round((float(offset_css) - float(lift_css)) * float(scale)))


def close_pose(ms, origin_y=0.0, origin_opacity=1.0):
    """Fade and an 8px leave, 200ms, from wherever the open currently sits."""
    if ms <= 0:
        return float(origin_opacity), float(origin_y)
    e = unit_ease(min(1.0, ms / float(CLOSE_MS)))
    opacity = origin_opacity * (1.0 - e)
    y = origin_y + (CLOSE_LEAVE_PX - origin_y) * e
    return opacity, y


def classify(event):
    """volume_up | volume_down | mute | esc | None.

    Name wins. A volume scan still counts when the name is missing or is
    not one of the four, so a firmware label we did not predict is logged
    and still moves the highlight. Escape is by name only: scan 1 is a
    normal key on some layouts when the name is present and isn't Esc.
    """
    name = (getattr(event, "name", None) or "").lower()
    if name in _BY_NAME:
        return _BY_NAME[name]
    # Numpad 0, Num Lock off. Same physical key types "0" when Num Lock is on,
    # and that name is not insert, so it falls through. The dedicated Insert
    # key shares the name but is not a keypad key.
    if name == "insert" and getattr(event, "is_keypad", False):
        return "mute"
    # Empty or unexpected name, but the scan is one of the three volume keys.
    scan = getattr(event, "scan_code", None)
    return _BY_SCAN.get(scan)


class DialKnob:
    """Key-down edge only. Auto-repeat is swallowed while we own the key
    and never moves the highlight a second time."""

    def __init__(self, on_log=lambda msg: None):
        self._log = on_log
        self._lock = threading.Lock()
        self.phase = "closed"  # closed | open | closing
        self.index = 0
        self._armed = None
        self._down = set()
        self._swallowed = set()
        self._seen = set()
        self._close_token = 0
        self._epoch = 0

    def handle(self, event):
        """Return ``(allow, action)``. ``allow`` False swallows the key."""
        kind = classify(event)
        self._log_first(kind, event)
        if kind is None:
            return True, None
        key = getattr(event, "scan_code", None)
        is_down = getattr(event, "event_type", None) == "down"
        with self._lock:
            if not is_down:
                self._down.discard(key)
                if key in self._swallowed:
                    self._swallowed.discard(key)
                    return False, None
                return True, None
            if key in self._down:
                if key in self._swallowed or self._owns_repeat(kind):
                    return False, None
                return True, None
            self._down.add(key)
            swallow, action = self._edge(kind)
            if swallow:
                self._swallowed.add(key)
            return (not swallow), action

    def note_closed(self, token):
        """Release volume keys. A late call from an older close does not
        shut a menu that has already opened again."""
        with self._lock:
            if token != self._close_token:
                return
            if self.phase == "closing":
                self.phase = "closed"

    def abandon(self, epoch=None):
        """No window to show. Do not leave volume keys swallowed.

        A later open has a newer epoch. Abandoning the old one must not
        shut that menu, and a close already in progress is left to finish.
        """
        with self._lock:
            if epoch is not None and epoch != self._epoch:
                return
            if self.phase != "open":
                return
            self.phase = "closed"

    def _owns_repeat(self, kind):
        if self.phase == "closed":
            return kind == "mute"
        return kind in ("volume_up", "volume_down", "mute", "esc")

    def _edge(self, kind):
        if self.phase == "closing":
            if kind in ("volume_up", "volume_down", "mute", "esc"):
                return True, None
            return False, None
        if self.phase == "closed":
            if kind == "mute":
                self.phase = "open"
                self.index = 0
                self._armed = None
                self._epoch += 1
                return True, {
                    "type": "open", "index": 0, "epoch": self._epoch,
                }
            return False, None
        if kind == "volume_up":
            was = self._armed
            self._armed = None
            if self.index < ROW_COUNT - 1:
                self.index += 1
                return True, {"type": "move", "index": self.index}
            if was is not None:
                return True, {"type": "move", "index": self.index}
            return True, None
        if kind == "volume_down":
            was = self._armed
            self._armed = None
            if self.index > 0:
                self.index -= 1
                return True, {"type": "move", "index": self.index}
            if was is not None:
                return True, {"type": "move", "index": self.index}
            return True, None
        if kind == "mute":
            if self.index == DELETE_ROW and self._armed != DELETE_ROW:
                self._armed = DELETE_ROW
                return True, {"type": "arm", "index": self.index}
            index = self.index
            token = self._begin_close()
            return True, {"type": "activate", "index": index, "token": token}
        if kind == "esc":
            token = self._begin_close()
            return True, {"type": "close", "token": token}
        return False, None

    def _begin_close(self):
        self._armed = None
        self._close_token += 1
        self.phase = "closing"
        return self._close_token

    def _log_first(self, kind, event):
        if not kind or kind in self._seen:
            return
        self._seen.add(kind)
        scan = getattr(event, "scan_code", None)
        vk = _SCAN_VK.get(scan)
        vk_text = ("0x%02x" % vk) if vk is not None else "?"
        self._log("[Dial] first %s name=%r scan=%s vk=%s"
                  % (kind, getattr(event, "name", None), scan, vk_text))
