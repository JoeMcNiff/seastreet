"""Receive an iPhone camera stream over WebRTC."""

import asyncio
import socket
import ssl
import subprocess
import threading
from collections import deque
from pathlib import Path

from aiohttp import web
from aiortc import MediaStreamError, RTCPeerConnection, RTCSessionDescription


ROOT = Path(__file__).resolve().parents[2]
CERT_DIR = ROOT / ".camera-feed"
PHONE_PAGE = Path(__file__).with_name("phone.html")


def local_hostname():
    name = socket.gethostname().removesuffix(".local")
    return f"{name}.local"


class WebRTCCamera:
    def __init__(self, host="0.0.0.0", https_port=8443, setup_port=8080):
        self.host = host
        self.https_port = https_port
        self.setup_port = setup_port
        self.frames = deque(maxlen=1)
        self._peers = set()
        self._alerts = None
        self._ready = threading.Event()
        self._loop = None
        self._stop = None
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

    def notify_match(self):
        if self._loop:
            self._loop.call_soon_threadsafe(self._send_match_alert)

    def _send_match_alert(self):
        if self._alerts and self._alerts.readyState == "open":
            self._alerts.send("match")

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
            await web.TCPSite(runner, self.host, self.https_port, ssl_context=context).start()
            await web.TCPSite(runner, self.host, self.setup_port).start()
            self._loop = asyncio.get_running_loop()
            self._stop = asyncio.Event()
            self._ready.set()
            await self._stop.wait()
        finally:
            await asyncio.gather(*(peer.close() for peer in tuple(self._peers)))
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

        await asyncio.gather(*(peer.close() for peer in tuple(self._peers)))
        self._peers.clear()
        self._alerts = None
        peer = RTCPeerConnection()
        self._peers.add(peer)

        @peer.on("track")
        def on_track(track):
            if track.kind == "video":
                asyncio.create_task(self._receive(track))

        @peer.on("datachannel")
        def on_data_channel(channel):
            if channel.label == "alerts":
                self._alerts = channel

        @peer.on("connectionstatechange")
        async def on_connection_state_change():
            if peer.connectionState in ("failed", "closed"):
                await peer.close()
                self._peers.discard(peer)

        await peer.setRemoteDescription(description)
        answer = await peer.createAnswer()
        await peer.setLocalDescription(answer)
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
