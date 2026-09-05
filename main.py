"""Show the iPhone feed and report when one full frontal face is ready."""

import subprocess
import threading
import time
from pathlib import Path

import cv2
import numpy

from camera_feed import opencv_frames
from face_detection import full_face

ROOT = Path(__file__).parent
subprocess.run(
    ["/usr/bin/arch", "-arm64", "/bin/bash", str(ROOT / "run.sh")],
    check=True,
)

window = "iPhone Camera - Full Face Detection"
cv2.namedWindow(window, cv2.WINDOW_NORMAL)
cv2.resizeWindow(window, 960, 640)

state = {"frame": None, "seen": 0.0, "number": 0}
lock = threading.Lock()


def receive():
    for frame in opencv_frames(startup_timeout=None):
        with lock:
            state["frame"] = frame
            state["seen"] = time.monotonic()
            state["number"] += 1


threading.Thread(target=receive, daemon=True).start()
print("Waiting for Continuity Camera… Press Q or Escape to close.")

streak = 0
last_number = -1
display = numpy.zeros((720, 1080, 3), dtype=numpy.uint8)

try:
    while True:
        with lock:
            frame = state["frame"]
            seen = state["seen"]
            number = state["number"]

        if frame is None or time.monotonic() - seen > 2:
            display[:] = 12
            cv2.putText(display, "WAITING FOR IPHONE CAMERA...", (250, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 180, 255), 2, cv2.LINE_AA)
            cv2.putText(display, "Keep the iPhone nearby and locked", (305, 395), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1, cv2.LINE_AA)
        elif number != last_number:
            display = frame.copy()
            last_number = number
            detected, boxes, reason = full_face(display)
            streak = min(streak + 1, 5) if detected else 0
            ready = streak == 5
            color = (70, 220, 120) if ready else (0, 180, 255)
            label = "FULL FACE READY" if ready else reason

            for x, y, width, height in boxes:
                cv2.rectangle(display, (x, y), (x + width, y + height), color, 3)
            cv2.rectangle(display, (0, 0), (display.shape[1], 54), (20, 20, 20), -1)
            cv2.putText(display, label, (18, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2, cv2.LINE_AA)

        cv2.imshow(window, display)
        if cv2.waitKey(30) & 0xFF in (27, ord("q")):
            break
except KeyboardInterrupt:
    pass
finally:
    cv2.destroyAllWindows()
