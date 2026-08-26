"""Local UDP replay trigger - one datagram saves the buffer.

For buttons that live outside Nebula: a Stream Deck, a home-automation
scene, the future QMK macropad. Anything that can send a UDP packet can now
request exactly what the F9 hotkey does.

Security posture: bound to 127.0.0.1 only, never a wildcard address, so the
exposure is "other processes on this PC can save a replay" - the same power
as pressing the hotkey. No payload is parsed; any datagram triggers. Off by
default (port 0); a bind failure logs clearly and disables rather than
retrying forever.
"""
import socket
import threading
import time

# Minimum seconds between accepted triggers: a stray flood of packets must
# not spam OBS's SaveReplayBuffer (each one writes a clip to disk).
_MIN_GAP_S = 2.0


class UdpTrigger:
    def __init__(self, on_trigger, on_log=None):
        self._on_trigger = on_trigger or (lambda: None)
        self._log = on_log or (lambda msg: None)
        self._sock = None
        self._thread = None
        self._stop = threading.Event()
        self._last_fired = 0.0

    def start(self, port):
        port = int(port or 0)
        if port <= 0:
            return False  # feature off; not an error
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.bind(("127.0.0.1", port))
        except OSError as exc:
            error = str(exc)
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
            self._log(f"[Udp] Replay trigger disabled - can't bind "
                      f"127.0.0.1:{port}: {error}")
            return False
        self._thread = threading.Thread(
            target=self._loop, name="NebulaUdpTrigger", daemon=True)
        self._thread.start()
        self._log(f"[Udp] Replay trigger listening on 127.0.0.1:{port} "
                  "- any packet saves.")
        return True

    def stop(self):
        self._stop.set()
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def _loop(self):
        while not self._stop.is_set() and self._sock is not None:
            try:
                data, _addr = self._sock.recvfrom(64)
            except OSError:
                break  # socket closed by stop()
            now = time.monotonic()
            if now - self._last_fired < _MIN_GAP_S:
                continue
            self._last_fired = now
            try:
                self._on_trigger()
            except Exception as exc:  # noqa: BLE001 - listener must survive
                self._log(f"[Udp] Trigger failed: {exc}")
