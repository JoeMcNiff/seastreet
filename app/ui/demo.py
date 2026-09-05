"""Continuity Camera preview with full-face readiness detection."""

import subprocess
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy

from app.capture.camera_feed import opencv_frames
from app.detection.face_detection import full_face
from app.providers.face_recognition import FaceSample, FacialRecognitionService

ROOT = Path(__file__).resolve().parents[2]
WINDOW = "Camera - Face Detection"


def receive_frames(frames):
    for frame in opencv_frames(startup_timeout=None):
        frames.append(frame)


def recognize_burst(service, snapshots, generation, results):
    results.append((generation, service.recognize(snapshots)))


def show_waiting(display):
    display[:] = 12
    cv2.putText(display, "WAITING FOR CAMERA...", (220, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 180, 255), 2, cv2.LINE_AA)


def main():
    subprocess.run(
        ["/usr/bin/arch", "-arm64", "/bin/bash", str(ROOT / "scripts/run.sh")],
        check=True,
    )

    frames = deque(maxlen=1)
    threading.Thread(target=receive_frames, args=(frames,), daemon=True).start()
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, 960, 640)

    display = numpy.zeros((720, 1080, 3), dtype=numpy.uint8)
    snapshots = deque(maxlen=5)
    recognition = FacialRecognitionService.from_environment()
    recognition_results = deque(maxlen=1)
    recognition_status = None
    recognition_running = False
    recognition_generation = 0
    last_frame_at = 0.0

    print("Waiting for Camera… Press Q or Escape to close.")
    try:
        while True:
            try:
                frame = frames.pop()
            except IndexError:
                frame = None

            try:
                generation, result = recognition_results.pop()
            except IndexError:
                pass
            else:
                recognition_running = False
                if generation == recognition_generation:
                    recognition_status = f"BURST SENT - {result.status.upper()}"
                    if result.error:
                        print(f"Recognition error: {result.error}")

            if frame is not None:
                last_frame_at = time.monotonic()
                display = frame.copy()
                detected, boxes, reason = full_face(display)

                if detected:
                    if recognition_status is None:
                        snapshots.append(FaceSample(frame, boxes[0]))
                else:
                    if snapshots:
                        recognition_generation += 1
                    snapshots.clear()
                    recognition_status = None

                ready = len(snapshots) == 5
                if ready and recognition_status is None and not recognition_running:
                    recognition_generation += 1
                    recognition_running = True
                    recognition_status = "SEARCHING..."
                    threading.Thread(
                        target=recognize_burst,
                        args=(recognition, tuple(snapshots), recognition_generation, recognition_results),
                        daemon=True,
                    ).start()

                color = (70, 220, 120) if ready else (0, 180, 255)
                label = recognition_status or ("FULL FACE READY" if ready else reason)
                for x, y, width, height in boxes:
                    cv2.rectangle(display, (x, y), (x + width, y + height), color, 3)
                cv2.rectangle(display, (0, 0), (display.shape[1], 54), (20, 20, 20), -1)
                cv2.putText(display, label, (18, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2, cv2.LINE_AA)
            elif time.monotonic() - last_frame_at > 2:
                if snapshots:
                    recognition_generation += 1
                snapshots.clear()
                recognition_status = None
                show_waiting(display)

            cv2.imshow(WINDOW, display)
            if cv2.waitKey(30) & 0xFF in (27, ord("q")):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        subprocess.run(["pkill", "-x", "PhoneCamera"], check=False)


if __name__ == "__main__":
    main()
