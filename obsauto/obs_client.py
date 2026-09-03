"""Minimal obs-websocket v5 client (Hello/Identify/Request/RequestResponse).

The old script used obs-websocket v4 style messages ({"request-type": ...})
which modern OBS (obs-websocket 5.x, built in since OBS 28) rejects outright
because v5 requires an op-code based Hello/Identify handshake before any
request will be answered. This is a small, dependency-free client for that
protocol - just enough for what the recorder needs (Start/Stop/Directory).
"""

import base64
import hashlib
import json
import threading
import time
import uuid

import websocket

OP_HELLO = 0
OP_IDENTIFY = 1
OP_IDENTIFIED = 2
OP_REEVENT = 5
OP_REQUEST = 6
OP_REQUEST_RESPONSE = 7


class OBSError(Exception):
    pass


def is_not_ready_error(exc):
    """True when obs-websocket returned 207 (OBS frontend still loading or stuck)."""
    return isinstance(exc, OBSError) and "not ready" in str(exc).lower()


class OBSClient:
    def __init__(self, host, port, password="", on_log=None):
        self.host = host
        self.port = port
        self.password = password
        self.on_log = on_log or (lambda msg: None)
        self._ws = None
        self._recv_thread = None
        self._connected = threading.Event()
        self._identified = threading.Event()
        self._lock = threading.Lock()
        self._pending = {}
        self._stop = False
        # Wall-clock ms for the last successful Hello→Identified handshake.
        # The Settings pane and titlebar read this; never invent a figure.
        self.last_handshake_ms = None
        # Called as on_event(event_type, data) from the receive thread for every
        # OBS event. Set by whoever cares; nothing here interprets them.
        self.on_event = None

    def log(self, msg):
        self.on_log(msg)

    # ---- connection lifecycle ----
    def connect(self, timeout=5):
        url = f"ws://{self.host}:{self.port}"
        t0 = time.perf_counter()
        self._ws = websocket.create_connection(url, timeout=timeout)
        self._stop = False
        self._identified.clear()
        self.last_handshake_ms = None

        hello_raw = self._ws.recv()
        hello = json.loads(hello_raw)
        if hello.get("op") != OP_HELLO:
            raise OBSError(f"Expected Hello, got: {hello_raw}")

        identify_data = {"rpcVersion": hello["d"].get("rpcVersion", 1)}

        auth = hello["d"].get("authentication")
        if auth:
            if not self.password:
                raise OBSError("OBS requires a password but none was configured")
            secret = base64.b64encode(
                hashlib.sha256((self.password + auth["salt"]).encode()).digest()
            )
            auth_response = base64.b64encode(
                hashlib.sha256(secret + auth["challenge"].encode()).digest()
            ).decode()
            identify_data["authentication"] = auth_response

        self._ws.send(json.dumps({"op": OP_IDENTIFY, "d": identify_data}))

        identified_raw = self._ws.recv()
        identified = json.loads(identified_raw)
        if identified.get("op") != OP_IDENTIFIED:
            raise OBSError(f"Identify failed: {identified_raw}")

        self._identified.set()
        self.last_handshake_ms = max(1, int(round((time.perf_counter() - t0) * 1000)))
        self.log("[OBS] Connected and handshake complete.")

        # `timeout` above only bounds the handshake itself. If it stayed in
        # effect for the long-lived recv loop below, any 5+ second gap with
        # no server activity (completely normal - OBS only sends messages on
        # events or in response to requests) would raise a timeout, silently
        # killing the connection and breaking every future Start/StopRecord.
        self._ws.settimeout(None)

        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def disconnect(self):
        self._stop = True
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self._ws = None
        self._identified.clear()

    @property
    def connected(self):
        return self._identified.is_set()

    def _recv_loop(self):
        # `_identified.clear()` lives in the finally, not after the loop.
        # `connected` is that flag, so an exception escaping the body used to
        # kill this thread while still reporting the socket as up: every
        # later call() then hung for its whole timeout, and _maybe_reconnect
        # never fired because it only acts on connected == False.
        try:
            self._recv_forever()
        finally:
            self._identified.clear()

    def _recv_forever(self):
        while not self._stop and self._ws:
            try:
                raw = self._ws.recv()
            except Exception:
                break
            if not raw:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            op = msg.get("op")
            if op == OP_REQUEST_RESPONSE:
                # `.get("d")`, not `["d"]`: the response branch used to be the
                # one place here that could raise on an unexpected frame,
                # while the event branch beside it was already guarded.
                data = msg.get("d") or {}
                req_id = data.get("requestId")
                with self._lock:
                    ev = self._pending.get(req_id)
                if ev:
                    ev["response"] = data
                    ev["event"].set()
            elif op == OP_REEVENT:
                # 7a needs ReplayBufferSaved: OBS writes the clip to its own
                # output directory and only then tells you where, so the path
                # arrives as an event rather than as a response to the save.
                # Runs on this receive thread - handlers must marshal.
                handler = self.on_event
                if handler:
                    try:
                        handler(msg["d"].get("eventType"),
                                msg["d"].get("eventData") or {})
                    except Exception as exc:
                        self.log(f"[OBS] Event handler failed: {exc}")

    # ---- requests ----
    def call(self, request_type, request_data=None, timeout=5):
        if not self.connected or not self._ws:
            raise OBSError("Not connected to OBS")

        request_id = str(uuid.uuid4())
        payload = {
            "op": OP_REQUEST,
            "d": {
                "requestType": request_type,
                "requestId": request_id,
            },
        }
        if request_data:
            payload["d"]["requestData"] = request_data

        ev = {"event": threading.Event(), "response": None}
        with self._lock:
            self._pending[request_id] = ev

        self._ws.send(json.dumps(payload))

        if not ev["event"].wait(timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            raise OBSError(f"Timed out waiting for response to {request_type}")

        with self._lock:
            self._pending.pop(request_id, None)

        resp = ev["response"]
        status = resp.get("requestStatus", {})
        if not status.get("result"):
            raise OBSError(
                f"{request_type} failed: {status.get('comment', 'unknown error')}"
            )
        return resp.get("responseData", {})

    # ---- convenience wrappers ----
    def start_record(self):
        self.call("StartRecord")

    def request_clean_exit(self, reason, support_url, timeout=5):
        """Ask the shutdown-plugin (norihiro) to quit OBS cleanly.

        CallVendorRequest -> vendor "shutdown-plugin", type "shutdown".
        force stays False on purpose: this must stop at confirmation
        dialogs rather than kill an active recording to get its way, and
        no exit_timeout is sent so the unsafe-terminate fallback can
        never fire. Raises OBSError when the plugin isn't installed or
        refuses - callers surface that, not swallow it.
        """
        return self.call("CallVendorRequest", {
            "vendorName": "shutdown-plugin",
            "requestType": "shutdown",
            "requestData": {
                "reason": reason,
                "support_url": support_url,
            },
        }, timeout=timeout)

    def stop_record(self):
        return self.call("StopRecord")  # responseData includes 'outputPath'

    def pause_record(self):
        self.call("PauseRecord")

    def resume_record(self):
        self.call("ResumeRecord")

    def get_record_status(self):
        return self.call("GetRecordStatus")

    def is_recording(self):
        try:
            return bool(self.get_record_status().get("outputActive"))
        except OBSError:
            return False

    def set_record_directory(self, path):
        self.call("SetRecordDirectory", {"recordDirectory": path})

    def wait_until_ready(self, timeout=60.0, interval=0.5):
        """Poll until OBS accepts requests, or return False on timeout.

        The websocket handshake can succeed while ``obs_frontend_ready()``
        is still false — or while OBS is hung mid-shutdown with its socket
        still listening. Callers should treat False as "not usable yet".
        """
        deadline = time.monotonic() + max(0.0, float(timeout))
        while time.monotonic() < deadline:
            try:
                self.get_version()
                return True
            except OBSError as exc:
                if not is_not_ready_error(exc):
                    raise
            time.sleep(max(0.05, float(interval)))
        return False

    # ---- scene/source management (used for the dynamic Game Capture source) ----
    def get_scene_item_list(self, scene_name):
        return self.call("GetSceneItemList", {"sceneName": scene_name}).get("sceneItems", [])

    def get_input_list(self):
        return self.call("GetInputList").get("inputs", [])

    def create_input(self, scene_name, input_name, input_kind, input_settings=None):
        return self.call("CreateInput", {
            "sceneName": scene_name,
            "inputName": input_name,
            "inputKind": input_kind,
            "inputSettings": input_settings or {},
            "sceneItemEnabled": True,
        })

    def remove_input(self, input_name):
        self.call("RemoveInput", {"inputName": input_name})

    def set_input_settings(self, input_name, settings, overlay=True):
        self.call("SetInputSettings", {
            "inputName": input_name,
            "inputSettings": settings,
            "overlay": overlay,
        })

    def remove_scene_item(self, scene_name, scene_item_id):
        self.call("RemoveSceneItem", {"sceneName": scene_name, "sceneItemId": scene_item_id})

    def get_record_directory(self):
        return self.call("GetRecordDirectory").get("recordDirectory")

    def get_version(self):
        """OBS Studio version string from GetVersion (e.g. ``30.2.3``)."""
        return self.call("GetVersion").get("obsVersion", "")

    def get_video_settings(self):
        """Canvas size + fps from GetVideoSettings."""
        return self.call("GetVideoSettings")

    def get_current_program_scene(self):
        data = self.call("GetCurrentProgramScene")
        return data.get("currentProgramSceneName") or data.get("sceneName") or ""

    def get_source_screenshot(
        self,
        source_name,
        image_width=640,
        image_height=360,
        image_format="jpg",
        compression_quality=60,
    ):
        """Base64 data-URI still of a source/scene (GetSourceScreenshot).

        Scaled "inner" by OBS so aspect is preserved. Returns ``imageData`` as
        OBS sends it (already a ``data:image/...;base64,...`` URI), or ``""``.
        """
        if not source_name:
            return ""
        data = self.call("GetSourceScreenshot", {
            "sourceName": source_name,
            "imageFormat": image_format,
            "imageWidth": int(image_width),
            "imageHeight": int(image_height),
            "imageCompressionQuality": int(compression_quality),
        })
        return data.get("imageData") or ""

    # ---- replay buffer (spec 7a) ----
    # The buffer is OBS's own rolling window in RAM. Nebula's job is only to arm
    # it, ask for a save, and file the result - it never holds video itself.

    def start_replay_buffer(self):
        self.call("StartReplayBuffer")

    def stop_replay_buffer(self):
        self.call("StopReplayBuffer")

    def save_replay_buffer(self):
        """Ask OBS to write the buffer out.

        The path is NOT in this response - OBS finishes the file afterwards and
        announces it in a ReplayBufferSaved event, which is why on_event exists.
        """
        self.call("SaveReplayBuffer")

    def get_replay_buffer_status(self):
        return bool(self.call("GetReplayBufferStatus").get("outputActive"))

    def set_profile_parameter(self, category, name, value):
        self.call("SetProfileParameter", {
            "parameterCategory": category,
            "parameterName": name,
            "parameterValue": str(value),
        })
