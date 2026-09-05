"""Receive Continuity Camera frames from the native viewer."""

import socket
import struct
import time


def _read(socket_, size):
    data = bytearray()
    while len(data) < size:
        chunk = socket_.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Camera viewer disconnected")
        data.extend(chunk)
    return bytes(data)


def jpeg_frames(host="127.0.0.1", port=8765):
    """Yield complete JPEG frames, reconnecting when the viewer restarts."""
    while True:
        try:
            with socket.create_connection((host, port)) as connection:
                while True:
                    size = struct.unpack("!I", _read(connection, 4))[0]
                    if size > 5_000_000:
                        raise ConnectionError("Invalid frame size")
                    yield _read(connection, size)
        except (ConnectionError, OSError):
            time.sleep(0.5)


def opencv_frames():
    """Yield frames as OpenCV BGR arrays (requires opencv-python and numpy)."""
    import cv2
    import numpy

    for jpeg in jpeg_frames():
        yield cv2.imdecode(numpy.frombuffer(jpeg, dtype=numpy.uint8), cv2.IMREAD_COLOR)
