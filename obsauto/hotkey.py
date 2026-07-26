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
    """Register a global hotkey. Returns an opaque handle (truthy) while the
    hook is active, or False if it isn't - pass the handle to unregister() to
    take the hook down again, which the Settings view does when the binding
    changes. An empty/None binding quietly does nothing (feature not configured).

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
        handle = keyboard.add_hotkey(target, callback, suppress=suppress)
        on_log(f"[Hotkey] Registered global hotkey: {binding or target} (key {target})")
        return handle
    except Exception as e:
        on_log(f"[Hotkey] Failed to register '{target}': {e}")
        return False


def unregister(handle, on_log=lambda msg: None):
    """Take down a hook returned by register(). Safe with None/False, so a
    caller can rebind unconditionally without tracking whether the previous
    registration actually took. Returns True if a hook was removed.

    This matters for `suppress=True` hooks: leaving the old one in place while
    binding a new key would keep swallowing the old keystroke system-wide,
    which is exactly the failure mode the scancode note above describes."""
    if not handle or not _AVAILABLE:
        return False
    try:
        keyboard.remove_hotkey(handle)
        return True
    except Exception as e:
        on_log(f"[Hotkey] Failed to remove the previous hotkey: {e}")
        return False
