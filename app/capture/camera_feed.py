"""Receive iPhone camera frames over WebRTC or Continuity Camera."""

import asyncio
import base64
import json
import socket
import ssl
import struct
import subprocess
import threading
from collections import deque
from pathlib import Path

import cv2
import numpy
from aiohttp import web
from aiortc import (
    MediaStreamError,
    RTCConfiguration,
    RTCPeerConnection,
    RTCSessionDescription,
)


ROOT = Path(__file__).resolve().parents[2]
CERT_DIR = ROOT / ".camera-feed"
PHONE_PAGE = Path(__file__).with_name("phone.html")
CONTINUITY_RUNNER = ROOT / "scripts/run_continuity.sh"
MAX_FRAME_BYTES = 10_000_000
MAX_LICENSE_BYTES = 8_000
PROFILE_FIELDS = (
    "id",
    "record_status",
    "wanted_level",
    "arrest_count",
    "active_warrant",
    "conviction_count",
    "primary_offense",
    "warrant_number",
    "last_arrest_date",
    "warrant_issue_date",
)


def local_hostname():
    name = socket.gethostname().removesuffix(".local")
    return f"{name}.local"


class WebRTCCamera:
    name = "iPhone WebRTC"

    def __init__(self, host="0.0.0.0", https_port=8443, setup_port=8080):
        self.host = host
        self.https_port = https_port
        self.setup_port = setup_port
        self.frames = deque(maxlen=1)
        self.license_scans = deque(maxlen=4)
        self._peers = set()
        self._channel = None
        self._ready = threading.Event()
        self._loop = None
        self._stop = None
        self._offer_lock = None
        self._thread = None
        self._error = None

    @property
    def camera_url(self):
        return f"https://{local_hostname()}:{self.https_port}"

    @property
    def certificate_url(self):
        return f"http://{local_hostname()}:{self.setup_port}/ca.crt"

    def start(self):
        subprocess.run(["/bin/bash", str(ROOT / "scripts/setup_webrtc_cert.sh")], check=True)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("WebRTC camera server did not start")
        if self._error:
            raise RuntimeError(f"WebRTC camera server failed: {self._error}") from self._error

    def stop(self):
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread:
            self._thread.join(timeout=5)

    def notify_profile(self, name, similarity, record, photo=None):
        threading.Thread(
            target=self._queue_profile,
            args=(name, similarity, record, photo),
            daemon=True,
        ).start()

    def notify_license(self, result):
        self._queue_message({"type": "license_result", **result.payload()})

    def _queue_profile(self, name, similarity, record, photo):
        message = _profile_message(name, similarity, record, photo)
        if self._loop:
            self._loop.call_soon_threadsafe(lambda: self._send(message))

    def _queue_message(self, payload):
        message = json.dumps(payload, separators=(",", ":"))
        if self._loop:
            self._loop.call_soon_threadsafe(lambda: self._send(message))

    def _send(self, message):
        if self._channel and self._channel.readyState == "open":
            self._channel.send(message)

    def _run(self):
        try:
            asyncio.run(self._serve())
        except Exception as error:
            self._error = error
            self._ready.set()

    async def _serve(self):
        app = web.Application()
        app.router.add_get("/", self._index)
        app.router.add_get("/ca.crt", self._certificate)
        app.router.add_post("/offer", self._offer)

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(CERT_DIR / "server.crt", CERT_DIR / "server.key")
        runner = web.AppRunner(app)
        await runner.setup()
        try:
            self._loop = asyncio.get_running_loop()
            self._stop = asyncio.Event()
            self._offer_lock = asyncio.Lock()
            await web.TCPSite(runner, self.host, self.https_port, ssl_context=context).start()
            await web.TCPSite(runner, self.host, self.setup_port).start()
            self._ready.set()
            await self._stop.wait()
        finally:
            await asyncio.gather(
                *(peer.close() for peer in tuple(self._peers)),
                return_exceptions=True,
            )
            self._peers.clear()
            await runner.cleanup()

    async def _index(self, _request):
        return web.FileResponse(PHONE_PAGE, headers={"Cache-Control": "no-store"})

    async def _certificate(self, _request):
        return web.FileResponse(
            CERT_DIR / "ca.crt",
            headers={
                "Content-Disposition": 'attachment; filename="seastreet-camera-ca.crt"',
                "Content-Type": "application/x-x509-ca-cert",
            },
        )

    async def _offer(self, request):
        try:
            offer = await request.json()
            description = RTCSessionDescription(sdp=offer["sdp"], type=offer["type"])
        except (KeyError, TypeError, ValueError) as error:
            raise web.HTTPBadRequest(text="Invalid WebRTC offer") from error

        async with self._offer_lock:
            await asyncio.gather(
                *(peer.close() for peer in tuple(self._peers)),
                return_exceptions=True,
            )
            self._peers.clear()
            self._channel = None

            # The phone reaches this server over the LAN, so public STUN adds
            # latency and can leave retry timers behind during reconnects.
            peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            self._peers.add(peer)

            @peer.on("track")
            def on_track(track):
                if track.kind == "video":
                    asyncio.create_task(self._receive(track))

            @peer.on("datachannel")
            def on_data_channel(channel):
                if channel.label == "alerts":
                    self._channel = channel

                    @channel.on("message")
                    def on_message(message):
                        barcode = _license_barcode(message)
                        if barcode:
                            self.license_scans.append(barcode)

            @peer.on("connectionstatechange")
            async def on_connection_state_change():
                if peer.connectionState == "failed":
                    await peer.close()
                if peer.connectionState in ("failed", "closed"):
                    self._peers.discard(peer)

            try:
                await peer.setRemoteDescription(description)
                answer = await peer.createAnswer()
                await peer.setLocalDescription(answer)
            except Exception:
                self._peers.discard(peer)
                await peer.close()
                raise

            return web.json_response(
                {"sdp": peer.localDescription.sdp, "type": peer.localDescription.type}
            )

    async def _receive(self, track):
        try:
            while True:
                frame = await track.recv()
                self.frames.append(frame.to_ndarray(format="bgr24"))
        except (MediaStreamError, asyncio.CancelledError):
            pass

class ContinuityCamera:
    """Receive JPEG frames from the native macOS Continuity Camera helper."""

    name = "Continuity Camera"

    def __init__(self, host="127.0.0.1", port=8765):
        self.host = host
        self.port = port
        self.frames = deque(maxlen=1)
        self.license_scans = deque(maxlen=1)
        self._stop = threading.Event()
        self._connection = None
        self._thread = None

    def start(self):
        subprocess.run(["/bin/bash", str(CONTINUITY_RUNNER)], check=True)
        self._thread = threading.Thread(target=self._receive, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._connection:
            self._connection.close()
        if self._thread:
            self._thread.join(timeout=2)
        subprocess.run(["pkill", "-x", "PhoneCamera"], check=False)

    def notify_profile(self, _name, _similarity, _record, _photo=None):
        pass

    def notify_license(self, _result):
        pass

    def _receive(self):
        while not self._stop.is_set():
            try:
                with socket.create_connection((self.host, self.port), timeout=1) as connection:
                    self._connection = connection
                    while not self._stop.is_set():
                        size = struct.unpack("!I", self._read(connection, 4))[0]
                        if not 0 < size <= MAX_FRAME_BYTES:
                            raise ConnectionError("Invalid Continuity Camera frame size")
                        jpeg = self._read(connection, size)
                        frame = cv2.imdecode(
                            numpy.frombuffer(jpeg, dtype=numpy.uint8), cv2.IMREAD_COLOR
                        )
                        if frame is not None:
                            self.frames.append(frame)
            except (ConnectionError, OSError, struct.error):
                self._stop.wait(0.25)
            finally:
                self._connection = None

    @staticmethod
    def _read(connection, size):
        data = bytearray()
        while len(data) < size:
            chunk = connection.recv(size - len(data))
            if not chunk:
                raise ConnectionError("Continuity Camera helper disconnected")
            data.extend(chunk)
        return data


def _profile_message(name, similarity, record, photo=None):
    payload = {
        "type": "criminal_profile",
        "name": name,
        "similarity": similarity,
        "record": {key: record.get(key) for key in PROFILE_FIELDS},
    }
    if photo is not None:
        image = (
            photo
            if isinstance(photo, numpy.ndarray)
            else cv2.imdecode(numpy.frombuffer(photo, numpy.uint8), cv2.IMREAD_COLOR)
        )
        if image is not None:
            height, width = image.shape[:2]
            scale = min(1, 360 / max(width, height))
            if scale < 1:
                image = cv2.resize(
                    image,
                    (round(width * scale), round(height * scale)),
                    interpolation=cv2.INTER_AREA,
                )
            encoded, jpeg = cv2.imencode(
                ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 78]
            )
            if encoded:
                payload["photo"] = base64.b64encode(jpeg).decode("ascii")
    return json.dumps(payload, separators=(",", ":"))


def _license_barcode(message):
    if not isinstance(message, str) or len(message.encode("utf-8")) > MAX_LICENSE_BYTES:
        return None
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        return None
    barcode = payload.get("raw") if payload.get("type") == "license_scan" else None
    return barcode if isinstance(barcode, str) and barcode.strip() else None
