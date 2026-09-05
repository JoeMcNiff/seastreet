"""Command-screen demo: live iPhone feed, mock alert, and human review."""

import subprocess
import threading
import time
from math import cos, pi, sin
from collections import deque
from pathlib import Path

import cv2
import numpy

from app.capture.camera_feed import opencv_frames
from app.detection.face_detection import full_face
from app.providers.face_recognition import FacialRecognitionService

ROOT = Path(__file__).resolve().parents[2]
print("Starting Continuity Camera helper (first launch can take about 30 seconds)…", flush=True)
subprocess.run(
    ["/usr/bin/arch", "-arm64", "/bin/bash", str(ROOT / "scripts" / "run.sh")],
    check=True,
)

window = "ID Assist Demo — iPhone Camera"
cv2.namedWindow(window, cv2.WINDOW_NORMAL)
cv2.resizeWindow(window, 960, 640)

state = {"frame": None, "seen": 0.0, "number": 0}
lock = threading.Lock()
face_snapshots = deque(maxlen=5)
recognition = FacialRecognitionService()


def receive():
    for frame in opencv_frames(startup_timeout=None):
        with lock:
            state["frame"] = frame
            state["seen"] = time.monotonic()
            state["number"] += 1


def play_alert():
    """Play one built-in macOS sound without blocking the camera loop."""
    subprocess.Popen(
        ["/usr/bin/afplay", "/System/Library/Sounds/Glass.aiff"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def centered_card(image, headline, detail, color):
    """Draw a high-contrast status card that is readable from a TV."""
    height, width = image.shape[:2]
    left, top = int(width * 0.12), int(height * 0.34)
    right, bottom = int(width * 0.88), int(height * 0.66)
    overlay = image.copy()
    cv2.rectangle(overlay, (left, top), (right, bottom), (10, 10, 10), -1)
    cv2.addWeighted(overlay, 0.88, image, 0.12, 0, image)
    cv2.rectangle(image, (left, top), (right, bottom), color, 4)
    cv2.putText(
        image, headline, (left + 34, top + 100), cv2.FONT_HERSHEY_SIMPLEX,
        1.02, color, 3, cv2.LINE_AA,
    )
    cv2.putText(
        image, detail, (left + 34, top + 165), cv2.FONT_HERSHEY_SIMPLEX,
        0.62, (240, 240, 240), 2, cv2.LINE_AA,
    )


def alert_border(image, started):
    """Flash red and blue three times, then retain an amber review border."""
    elapsed = time.monotonic() - started
    if elapsed < 1.8:
        color = (255, 80, 30) if int(elapsed / 0.3) % 2 == 0 else (30, 30, 255)
    else:
        color = (0, 190, 255)
    height, width = image.shape[:2]
    cv2.rectangle(image, (5, 5), (width - 6, height - 6), color, 14)
    return color


def draw_star(image, center, outer_radius=25):
    """Draw one filled five-point wanted-level star."""
    points = []
    inner_radius = outer_radius * 0.46
    for index in range(10):
        radius = outer_radius if index % 2 == 0 else inner_radius
        angle = -pi / 2 + index * pi / 5
        points.append(
            (
                int(center[0] + radius * cos(angle)),
                int(center[1] + radius * sin(angle)),
            )
        )
    polygon = numpy.array(points, dtype=numpy.int32)
    cv2.fillPoly(image, [polygon], (0, 195, 255))
    cv2.polylines(image, [polygon], True, (20, 20, 20), 3, cv2.LINE_AA)


def wanted_stars(image, count=5):
    """Render the visual-only five-star alert level for a possible match."""
    height, width = image.shape[:2]
    spacing = max(50, min(68, width // 14))
    start_x = width - spacing * count - 24
    center_y = min(94, height - 42)
    for index in range(count):
        draw_star(image, (start_x + spacing * index, center_y))


threading.Thread(target=receive, daemon=True).start()
print("Waiting for Continuity Camera… Press Q or Escape to close; F toggles fullscreen.")

streak = 0
last_number = -1
recognition_started = False
review_state = "WAITING_FOR_FACE"
alert_started = None
last_boxes = []
last_reason = "WAITING FOR FACE"
fullscreen = False
display = numpy.zeros((720, 1080, 3), dtype=numpy.uint8)

try:
    while True:
        with lock:
            frame = state["frame"]
            seen = state["seen"]
            number = state["number"]

        if frame is None or time.monotonic() - seen > 2:
            display[:] = 12
            cv2.putText(
                display, "WAITING FOR IPHONE CAMERA...", (250, 350),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 180, 255), 2, cv2.LINE_AA,
            )
            cv2.putText(
                display, "Keep the iPhone nearby and locked", (305, 395),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1, cv2.LINE_AA,
            )
        else:
            if number != last_number:
                last_number = number
                detected, last_boxes, last_reason = full_face(frame)
                streak = min(streak + 1, 5) if detected else 0
                if detected:
                    face_snapshots.append(frame.copy())
                else:
                    face_snapshots.clear()
                    recognition_started = False
                    review_state = "WAITING_FOR_FACE"
                    alert_started = None

                if streak == 5 and not recognition_started:
                    result = recognition.recognize(list(face_snapshots))
                    recognition_started = True
                    if result.status == "mock_candidate_returned" and result.candidates:
                        review_state = "REVIEW_REQUIRED"
                        alert_started = time.monotonic()
                        play_alert()

            display = frame.copy()
            face_color = (70, 220, 120) if streak == 5 else (0, 180, 255)
            for x, y, width, height in last_boxes:
                cv2.rectangle(display, (x, y), (x + width, y + height), face_color, 3)
            cv2.rectangle(display, (0, 0), (display.shape[1], 54), (20, 20, 20), -1)
            label = "FULL FACE READY" if streak == 5 else last_reason
            cv2.putText(
                display, label, (18, 37), cv2.FONT_HERSHEY_SIMPLEX,
                0.85, face_color, 2, cv2.LINE_AA,
            )

            if review_state == "REVIEW_REQUIRED":
                card_color = alert_border(display, alert_started)
                wanted_stars(display)
                centered_card(
                    display,
                    "POSSIBLE MATCH - REVIEW REQUIRED",
                    "Synthetic demo candidate  |  [C] Confirm  [R] Reject",
                    card_color,
                )
            elif review_state == "CONFIRMED":
                centered_card(
                    display,
                    "MOCK REVIEW CONFIRMED",
                    "Synthetic demo only - records view is not connected.",
                    (70, 220, 120),
                )
            elif review_state == "REJECTED":
                centered_card(
                    display,
                    "MOCK REVIEW REJECTED",
                    "No records were requested. Move the subject away to reset.",
                    (0, 180, 255),
                )

        cv2.imshow(window, display)
        key = cv2.waitKey(30) & 0xFF
        if review_state == "REVIEW_REQUIRED" and key in (ord("c"), ord("C")):
            review_state = "CONFIRMED"
        elif review_state == "REVIEW_REQUIRED" and key in (ord("r"), ord("R")):
            review_state = "REJECTED"
        elif key in (ord("f"), ord("F")):
            fullscreen = not fullscreen
            mode = cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL
            cv2.setWindowProperty(window, cv2.WND_PROP_FULLSCREEN, mode)
        elif key in (27, ord("q")):
            break
except KeyboardInterrupt:
    pass
finally:
    cv2.destroyAllWindows()
