"""Receive Continuity Camera frames from the native viewer."""

import socket
import struct
import time

HOST = "127.0.0.1"
PORT = 8765
MAX_FRAME_BYTES = 5_000_000


def _read(socket_, size):
    data = bytearray()
    while len(data) < size:
        chunk = socket_.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Camera viewer disconnected")
        data.extend(chunk)
    return bytes(data)


def jpeg_frames(host=HOST, port=PORT):
    """Yield complete JPEG frames, reconnecting when the viewer restarts."""
    while True:
        try:
            with socket.create_connection((host, port)) as connection:
                while True:
                    size = struct.unpack("!I", _read(connection, 4))[0]
                    if not 0 < size <= MAX_FRAME_BYTES:
                        raise ConnectionError("Invalid frame size")
                    yield _read(connection, size)
        except (ConnectionError, OSError):
            time.sleep(0.5)


def opencv_frames():
    """Yield frames as OpenCV BGR arrays (requires opencv-python and numpy)."""
    import cv2
    import numpy

    for jpeg in jpeg_frames():
        frame = cv2.imdecode(numpy.frombuffer(jpeg, dtype=numpy.uint8), cv2.IMREAD_COLOR)
        if frame is not None:
            yield frame
