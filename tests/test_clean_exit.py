"""Clean OBS exit via norihiro's shutdown-plugin (CallVendorRequest).

The request shape is the contract: vendor name, request type and a
requestData with reason + support_url required. force must NOT be set and
no exit_timeout may be sent - this wrapper is for quitting politely or not
at all; killing an active recording to win an argument is exactly what it
must never do.

    python tests/test_clean_exit.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.obs_client import OBSClient, OBSError

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class FakeWS:
    """Records sends; replies like obs-websocket would over recv()."""

    def __init__(self, result=True, comment=""):
        import threading
        self.sent = []
        self.result = result
        self.comment = comment
        self.client = None
        self._reply = None
        self._lock = threading.Lock()
        self.closed = False

    def send(self, text):
        import json
        payload = json.loads(text)
        self.sent.append(payload)
        req_id = payload["d"]["requestId"]
        with self._lock:
            self._reply = json.dumps({
                "op": 7,  # OP_REQUEST_RESPONSE (client constant)
                "d": {
                    "requestId": req_id,
                    "requestStatus": {"result": self.result,
                                      "comment": self.comment},
                    "responseData": {},
                },
            })

    def recv(self):
        # Block like a real socket would - the receive thread must still be
        # alive when call() waits on the response.
        while True:
            with self._lock:
                if self._reply is not None:
                    reply, self._reply = self._reply, None
                    return reply
                if self.closed:
                    raise ConnectionError("fake socket closed")
            time.sleep(0.01)

    def close(self):
        self.closed = True


def make_client(ws):
    import threading
    c = OBSClient.__new__(OBSClient)
    c._ws = ws
    ws.client = c
    c._lock = threading.Lock()
    c._pending = {}
    c._stop = False
    c._identified = threading.Event()
    c._identified.set()   # connected property reads this
    c.log = lambda msg: None
    # The real receive loop, alive for the whole test like in production.
    threading.Thread(target=c._recv_loop, daemon=True).start()
    time.sleep(0.05)
    return c


REASON = "Nebula is closing and started this OBS session"
URL = "https://github.com/theoriginalcheese/nebula/issues"

ws = FakeWS()
c = make_client(ws)
c.request_clean_exit(REASON, URL)

check("one request sent", len(ws.sent) == 1, len(ws.sent))
req = ws.sent[0]["d"]
check("wraps in CallVendorRequest",
      req["requestType"] == "CallVendorRequest", req["requestType"])
data = req["requestData"]
check("vendor name is shutdown-plugin (0.3.0+)",
      data["vendorName"] == "shutdown-plugin", data["vendorName"])
check("inner type is shutdown",
      data["requestType"] == "shutdown", data["requestType"])
check("reason travels", data["requestData"]["reason"] == REASON)
check("support url travels",
      data["requestData"]["support_url"] == URL)
check("force is never sent", "force" not in data["requestData"],
      sorted(data["requestData"]))
check("exit_timeout is never sent",
      "exit_timeout" not in data["requestData"], sorted(data["requestData"]))

# A refusal surfaces as OBSError - callers must see it, not swallow it.
ws2 = FakeWS(result=False, comment="shutdown-plugin is not loaded")
c2 = make_client(ws2)
raised = None
try:
    c2.request_clean_exit(REASON, URL)
except OBSError as exc:
    raised = exc
check("plugin missing -> honest error",
      raised is not None and "not loaded" in str(raised), raised)

passed_all = all(p for _, p, _ in results)
for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name:<42} {detail}")
print(f"\n{'ALL PASS' if passed_all else 'FAILURES PRESENT'} "
      f"({len(results)} checks)")
sys.exit(0 if passed_all else 1)
