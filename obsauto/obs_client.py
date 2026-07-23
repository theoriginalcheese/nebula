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

    def log(self, msg):
        self.on_log(msg)

    # ---- connection lifecycle ----
    def connect(self, timeout=5):
        url = f"ws://{self.host}:{self.port}"
        self._ws = websocket.create_connection(url, timeout=timeout)
        self._stop = False
        self._identified.clear()

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
                req_id = msg["d"].get("requestId")
                with self._lock:
                    ev = self._pending.get(req_id)
                if ev:
                    ev["response"] = msg["d"]
                    ev["event"].set()
            elif op == OP_REEVENT:
                pass  # events (RecordStateChanged etc.) not currently consumed
        self._identified.clear()

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
