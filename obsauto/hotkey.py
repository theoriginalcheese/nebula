"""Global hotkey support: lets a single key (e.g. the laptop's fan key)
toggle monitoring on/off system-wide, even while a game has focus.

Uses the `keyboard` package's low-level hook, so it works regardless of
which window has focus. `suppress=True` swallows the keystroke so the app
that normally owns it doesn't also react - note this only suppresses the
*keyboard* event; keys that additionally signal through vendor channels
(e.g. ASUS WMI events consumed by Armoury Crate) may still trigger their
vendor behavior alongside ours.
"""

try:
    import keyboard
    _AVAILABLE = True
except Exception:  # pragma: no cover - keyboard package missing/broken
    _AVAILABLE = False


def register(binding, callback, suppress=True, on_log=lambda msg: None, scancode=None):
    """Register a global hotkey. Returns True if the hook is active.
    An empty/None binding quietly does nothing (feature not configured).

    `binding` is a `keyboard`-package name (e.g. "f6", "ctrl+alt+r") and is also
    what gets shown on the keycap in the UI. If `scancode` is given it takes
    precedence and binds that exact *physical* key instead.

    That matters because a character can resolve to several scancodes: on this
    UK layout "`" maps to both 41 (the real backtick key) and 40 - and 40 is
    also the apostrophe key. Binding by name would therefore suppress
    apostrophes system-wide. Pinning the scancode avoids that entirely."""
    if not binding and scancode is None:
        return False
    if not _AVAILABLE:
        on_log("[Hotkey] keyboard package unavailable - hotkey disabled.")
        return False
    target = scancode if scancode is not None else binding
    try:
        keyboard.add_hotkey(target, callback, suppress=suppress)
        on_log(f"[Hotkey] Registered global hotkey: {binding or target} (key {target})")
        return True
    except Exception as e:
        on_log(f"[Hotkey] Failed to register '{target}': {e}")
        return False
