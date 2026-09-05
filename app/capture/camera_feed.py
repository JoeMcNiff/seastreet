"""Receive Continuity Camera frames from the native viewer."""

import socket
import struct
import time


class CameraUnavailable(RuntimeError):
    pass


def _read(socket_, size):
    data = bytearray()
    while len(data) < size:
        chunk = socket_.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Camera viewer disconnected")
        data.extend(chunk)
    return bytes(data)


def jpeg_frames(host="127.0.0.1", port=8765, startup_timeout=20):
    """Yield JPEG frames, failing clearly if the camera never starts."""
    deadline = float("inf") if startup_timeout is None else time.monotonic() + startup_timeout
    while True:
        try:
            with socket.create_connection((host, port), timeout=1) as connection:
                while True:
                    try:
                        size = struct.unpack("!I", _read(connection, 4))[0]
                    except socket.timeout:
                        if time.monotonic() >= deadline:
                            raise CameraUnavailable("Continuity Camera did not produce a frame within 20 seconds")
                        continue
                    if size > 5_000_000:
                        raise ConnectionError("Invalid frame size")
                    frame = _read(connection, size)
                    deadline = float("inf")
                    yield frame
        except CameraUnavailable:
            raise
        except (ConnectionError, OSError):
            if time.monotonic() >= deadline:
                raise CameraUnavailable("The native camera helper did not start within 20 seconds")
            time.sleep(0.5)


def opencv_frames(startup_timeout=20):
    """Yield frames as OpenCV BGR arrays (requires opencv-python and numpy)."""
    import cv2
    import numpy

    for jpeg in jpeg_frames(startup_timeout=startup_timeout):
        yield cv2.imdecode(numpy.frombuffer(jpeg, dtype=numpy.uint8), cv2.IMREAD_COLOR)
