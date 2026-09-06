"""WebRTC camera preview with face detection and candidate matching."""

import threading
import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy

from app.capture.camera_feed import WebRTCCamera
from app.detection.face_detection import FaceTracker, detect_faces
from app.providers.face_recognition import FaceSample, FacialRecognitionService

WINDOW = "Camera - Face Detection"
SEARCH_RETRY_SECONDS = 4.0


@dataclass
class PersonState:
    generation: int = 0
    running: bool = False
    status: str = None
    name: str = None
    similarity: float = None
    retry_at: float = 0


def recognize_face(service, sample, track_id, generation, results):
    results.append((track_id, generation, service.recognize_face(sample)))


def show_waiting(display):
    display[:] = 12
    cv2.putText(display, "WAITING FOR CAMERA...", (220, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 180, 255), 2, cv2.LINE_AA)


def main():
    camera = WebRTCCamera()
    camera.start()
    print(f"First time only, install the certificate from {camera.certificate_url}")
    print(f"On the iPhone, open {camera.camera_url}")
    print("Waiting for iPhone… Press Q or Escape to close.")
    try:
        frames = camera.frames
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW, 960, 640)
        display = numpy.zeros((720, 1080, 3), dtype=numpy.uint8)
        tracker = FaceTracker()
        recognition = FacialRecognitionService.from_environment()
        recognition_results = deque()
        states = {}
        last_frame_at = 0.0

        while True:
            try:
                frame = frames.pop()
            except IndexError:
                frame = None

            while recognition_results:
                track_id, generation, result = recognition_results.popleft()
                state = states.get(track_id)
                if state is None:
                    continue
                if generation != state.generation:
                    continue
                state.running = False
                if result.error:
                    print(f"Recognition error for face {track_id}: {result.error}")
                if result.status in ("retry_face", "no_match", "provider_error"):
                    state.status = None
                    state.retry_at = time.monotonic() + (
                        0.75 if result.status == "retry_face" else SEARCH_RETRY_SECONDS
                    )
                    continue
                state.status = result.status
                if result.candidates:
                    candidate = result.candidates[0]
                    state.name = candidate.get("display_name") or "Unknown person"
                    state.similarity = candidate["similarity"]
                    camera.notify_match()

            if frame is not None:
                last_frame_at = time.monotonic()
                display = frame.copy()
                tracked_faces = tracker.update(detect_faces(display))
                active_ids = set(tracker.active_ids)
                for track_id in states.keys() - active_ids:
                    del states[track_id]

                for track_id, face in tracked_faces:
                    state = states.setdefault(track_id, PersonState())
                    if state.name:
                        continue
                    if face.ready:
                        now = time.monotonic()
                        if state.running and now >= state.retry_at:
                            state.running = False
                            state.status = None
                        if (
                            state.status is None
                            and not state.running
                            and now >= state.retry_at
                        ):
                            state.generation += 1
                            state.running = True
                            state.status = "searching"
                            state.retry_at = now + SEARCH_RETRY_SECONDS
                            threading.Thread(
                                target=recognize_face,
                                args=(
                                    recognition,
                                    FaceSample(frame, face.rect),
                                    track_id,
                                    state.generation,
                                    recognition_results,
                                ),
                                daemon=True,
                            ).start()
                    else:
                        if state.status is not None:
                            state.generation += 1
                        state.running = False
                        state.status = None

                matches = sum(bool(states[track_id].name) for track_id, _face in tracked_faces)
                label = f"{len(tracked_faces)} FACES | {matches} IN-FRAME MATCHES"
                color = (70, 220, 120) if matches else (0, 180, 255)
                for track_id, face in tracked_faces:
                    state = states[track_id]
                    x, y, width, height = face.rect
                    box_color = (70, 220, 120) if face.ready or state.name else (0, 180, 255)
                    cv2.rectangle(display, (x, y), (x + width, y + height), box_color, 3)
                    if state.name:
                        face_label = f"{state.name} ({state.similarity:.2f})"
                    elif state.running:
                        face_label = "SEARCHING..."
                    elif state.status:
                        face_label = state.status.replace("_", " ").upper()
                    else:
                        face_label = face.reason
                    cv2.putText(
                        display,
                        face_label,
                        (x, max(24, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        box_color,
                        2,
                        cv2.LINE_AA,
                    )
                cv2.rectangle(display, (0, 0), (display.shape[1], 54), (20, 20, 20), -1)
                cv2.putText(display, label, (18, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2, cv2.LINE_AA)
            elif time.monotonic() - last_frame_at > 2:
                tracker.clear()
                states.clear()
                show_waiting(display)

            cv2.imshow(WINDOW, display)
            if cv2.waitKey(30) & 0xFF in (27, ord("q")):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        camera.stop()


if __name__ == "__main__":
    main()
