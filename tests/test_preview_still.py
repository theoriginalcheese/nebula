"""WebView hero scene still — GetSourceScreenshot wiring (no live OBS).

    python tests/test_preview_still.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsauto.obs_client import OBSClient
from spike.host import NebulaHost

results = []


def check(name, passed, detail=""):
    results.append((name, bool(passed), str(detail)))


class _FakeObs:
    connected = True

    def __init__(self):
        self.calls = []
        self.scene = "Game Capture"
        self.uri = "data:image/jpg;base64,abc"

    def get_current_program_scene(self):
        return self.scene

    def get_source_screenshot(self, source_name, **kwargs):
        self.calls.append((source_name, kwargs))
        return self.uri


# --- OBSClient request shape -------------------------------------------
captured = {}


def _fake_call(self, request_type, request_data=None, timeout=5):
    captured["type"] = request_type
    captured["data"] = request_data
    return {"imageData": "data:image/jpg;base64,xx"}


OBSClient.call = _fake_call  # type: ignore[method-assign]
client = OBSClient("127.0.0.1", 4455, "")
client._identified.set()
client._ws = object()
got = client.get_source_screenshot("Scene A", image_width=320, image_height=180)
check("screenshot request type", captured.get("type") == "GetSourceScreenshot")
check("screenshot source name", captured.get("data", {}).get("sourceName") == "Scene A")
check("screenshot returns data uri", got.startswith("data:image/"))
check("empty source short-circuits", client.get_source_screenshot("") == "")

# --- Host cache / seq --------------------------------------------------
host = NebulaHost({"obs_host": "127.0.0.1", "obs_port": 4455})
fake = _FakeObs()
host.obs = fake
host._visible = True
host._is_recording = True
host._scene_name = "Game Capture"
host._preview_last_fetch = 0.0

host._refresh_preview_still()
still = host.preview_still()
check("first still has uri", still["uri"].startswith("data:image/"), still)
check("first still bumps seq", host.preview_still_seq() == 1, host.preview_still_seq())
check("OBS called once", len(fake.calls) == 1, fake.calls)

host._refresh_preview_still()  # throttled
check("throttle skips second grab", len(fake.calls) == 1)

host._preview_last_fetch = time.monotonic() - 3.0
host._refresh_preview_still()
check("after interval grabs again", len(fake.calls) == 2)
check("seq bumps again", host.preview_still_seq() == 2)

host._is_recording = False
host._refresh_preview_still()
check("idle clears uri", host.preview_still()["uri"] == "")
check("idle clears seq", host.preview_still_seq() == 0)

# --- summary -----------------------------------------------------------
failed = [r for r in results if not r[1]]
for name, ok, detail in results:
    print(("%s  %s" % ("PASS" if ok else "FAIL", name))
          + ((" — " + detail) if detail and not ok else ""))
print("%d/%d passed" % (len(results) - len(failed), len(results)))
sys.exit(1 if failed else 0)
