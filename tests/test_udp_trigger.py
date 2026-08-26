"""Local UDP replay trigger.

Pins: loopback-only bind, any-datagram-triggers, the flood gap, clean
shutdown, honest failure when the port is taken, and that port 0 means
"feature off" without touching sockets.

    python tests/test_udp_trigger.py
"""
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spike.udp_trigger import UdpTrigger

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    return s, port


def send(port, payload=b"go"):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(payload, ("127.0.0.1", port))


logs = []
fires = []

# ---- off by default: port 0 never opens a socket ----
t = UdpTrigger(lambda: fires.append(1), on_log=logs.append)
check("port 0 is feature-off", t.start(0) is False)
check("feature-off logs nothing scary",
      not any("disabled" in m.lower() for m in logs), logs)

# ---- basic trigger + flood gap ----
s, port = free_port()
s.close()  # hand the port back for the trigger to bind
check("binds a free port", t.start(port) is True)
time.sleep(0.15)  # let the listener enter recvfrom
send(port)
time.sleep(0.3)
check("one datagram fires once", len(fires) == 1, len(fires))
send(port); send(port); send(port)   # burst inside the gap window
time.sleep(0.4)
check("burst collapses to one save (flood gap)", len(fires) == 1, len(fires))
# After the gap passes, it fires again.
time.sleep(2.2)
send(port, b"")   # zero-length datagram still counts as "any packet"
time.sleep(0.4)
check("post-gap datagram triggers", len(fires) == 2, len(fires))

# ---- shutdown stops cleanly and releases the port ----
t.stop()
time.sleep(0.2)
fires.clear()
try:
    send(port)
except OSError:
    pass  # ICMP port-unreachable can surface as an error on some stacks
time.sleep(0.3)
check("after stop nothing fires", fires == [], fires)
s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s2.bind(("127.0.0.1", port))   # port must be free again
    check("stop releases the port", True)
finally:
    s2.close()

# ---- bind failure is honest and non-fatal ----
blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
blocker.bind(("127.0.0.1", 0))
blocked_port = blocker.getsockname()[1]
logs.clear()
t2 = UdpTrigger(lambda: fires.append(1), on_log=logs.append)
check("taken port refuses to start", t2.start(blocked_port) is False)
check("taken port explains itself in the log",
      any("can't bind" in m.lower() for m in logs), logs)
blocker.close()

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<46} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} "
      f"({len(results)} checks)")
sys.exit(0 if passed_all else 1)
