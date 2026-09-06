"""Live camera preview with face detection and candidate matching."""

import argparse
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from uuid import uuid4

import cv2
import numpy

from app.audit.evidence_log import EvidenceLog
from app.capture.camera_feed import ContinuityCamera, WebRTCCamera
from app.detection.face_detection import FaceDetectionWorker
from app.detection.license_detection import LicenseScanner
from app.providers.face_recognition import FaceSample, FacialRecognitionService
from app.records.criminal_records import CriminalRecordsService
from app.ui.live_panel import render_live_window

WINDOW = "Camera - Face Detection"
SEARCH_RETRY_SECONDS = 1.0
ALERT_STATUSES = {
    "records_found",
    "license_expired",
    "license_mismatch",
    "license_not_found",
}
BRAND_BLUE = (138, 74, 0)  # OpenCV uses BGR: #004A8A


@dataclass
class PersonState:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    generation: int = 0
    running: bool = False
    status: str = None
    name: str = None
    identity_id: str = None
    similarity: float = None
    retry_at: float = 0
    recognition_request_id: str = None
    records_query_id: str = None
    records_status: str = None
    records: tuple = ()
    photo: object = None
    active: bool = True


def recognize_face(service, sample, track_id, generation, results):
    results.append((track_id, generation, service.recognize_face(sample)))


def find_records(service, identity_id, track_id, generation, results):
    results.append((track_id, generation, service.lookup(identity_id)))


def show_waiting(display):
    display[:] = 0
    cv2.putText(display, "WAITING FOR CAMERA...", (220, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.8, BRAND_BLUE, 2, cv2.LINE_AA)


def main(camera_kind="webrtc"):
    session_id = str(uuid4())
    audit = EvidenceLog.from_environment()
    context = {
        "session_id": session_id,
        "operator": os.environ.get("OPERATOR_ID", "demo-operator"),
        "agency_unit": os.environ.get("AGENCY_UNIT", "demo"),
        "encounter_id": os.environ.get("ENCOUNTER_ID"),
        "search_predicate": os.environ.get("SEARCH_PREDICATE", "demo"),
    }

    def log(event_type, message, **fields):
        audit.append(event_type, message, **context, **fields)

    camera = ContinuityCamera() if camera_kind == "continuity" else WebRTCCamera()
    detector = None
    license_scanner = None
    try:
        camera.start()
        log("camera_session_started", "Field camera session activated")
        if camera_kind == "webrtc":
            print(f"First time only, install the certificate from {camera.certificate_url}")
            print(f"On the iPhone, open {camera.camera_url}")
        else:
            print("The native Continuity Camera helper is open on the Mac.")
        print(f"Audit log: {audit.path}")
        print(f"Waiting for {camera.name}… Press Q or Escape to close.")
        frames = camera.frames
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL | cv2.WINDOW_FREERATIO)
        cv2.resizeWindow(WINDOW, 1400, 600)
        display = numpy.zeros((720, 1080, 3), dtype=numpy.uint8)
        detector = FaceDetectionWorker()
        tracked_faces = ()
        recognition = FacialRecognitionService.from_environment()
        records = CriminalRecordsService(recognition.supabase)
        license_scanner = LicenseScanner(recognition.supabase)
        recognition_results = deque()
        records_results = deque()
        license_result = None
        license_result_at = 0
        states = {}
        selected_track_id = None
        stream_connected = False
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
                    message = {
                        "retry_face": "provider requested another face image",
                        "no_match": "no identity match returned",
                        "provider_error": "recognition provider unavailable",
                    }[result.status]
                    log(
                        "recognition_result",
                        f"Subject {track_id} {message}",
                        event_id=state.event_id,
                        track_id=track_id,
                        provider_request_id=state.recognition_request_id,
                        provider_status=result.status,
                        error=result.error,
                        retry_scheduled=True,
                    )
                    state.status = None
                    state.retry_at = time.monotonic() + (
                        0.75 if result.status == "retry_face" else SEARCH_RETRY_SECONDS
                    )
                    continue
                state.status = result.status
                if result.candidates:
                    candidate = result.candidates[0]
                    state.name = candidate.get("display_name") or "Unknown person"
                    state.identity_id = candidate["identity_id"]
                    state.similarity = candidate["similarity"]
                    selected_track_id = track_id
                    log(
                        "identity_matched",
                        f"Subject {track_id} matched {state.name}",
                        event_id=state.event_id,
                        track_id=track_id,
                        identity_id=state.identity_id,
                        display_name=state.name,
                        provider_request_id=state.recognition_request_id,
                        similarity=float(state.similarity),
                    )
                    state.records_status = "searching"
                    state.records_query_id = str(uuid4())
                    log(
                        "records_query_submitted",
                        f"Subject {track_id} records query submitted",
                        event_id=state.event_id,
                        track_id=track_id,
                        identity_id=state.identity_id,
                        records_query_id=state.records_query_id,
                    )
                    threading.Thread(
                        target=find_records,
                        args=(
                            records,
                            state.identity_id,
                            track_id,
                            state.generation,
                            records_results,
                        ),
                        daemon=True,
                    ).start()

            while records_results:
                track_id, generation, result = records_results.popleft()
                state = states.get(track_id)
                if state is None or generation != state.generation:
                    continue
                state.records_status = result.status
                state.records = result.records
                if result.error:
                    print(f"Records error for face {track_id}: {result.error}")
                event_type = {
                    "records_found": "records_returned",
                    "no_records": "records_empty",
                    "records_unavailable": "records_error",
                }[result.status]
                message = {
                    "records_found": f"Subject {track_id} records returned",
                    "no_records": f"Subject {track_id} has no records",
                    "records_unavailable": f"Subject {track_id} records unavailable",
                }[result.status]
                log(
                    event_type,
                    message,
                    event_id=state.event_id,
                    track_id=track_id,
                    identity_id=state.identity_id,
                    records_query_id=state.records_query_id,
                    record_count=len(result.records),
                    record_ids=[record.get("id") for record in result.records],
                    active_warrant=any(
                        record.get("active_warrant") is True for record in result.records
                    ),
                    error=result.error,
                    disposition={
                        "records_found": "matched_with_records",
                        "no_records": "matched_no_records",
                        "records_unavailable": "records_unavailable",
                    }[result.status],
                )
                if result.status == "records_found":
                    camera.notify_profile(
                        state.name,
                        state.similarity,
                        result.records[0],
                        state.photo,
                    )

            while True:
                result = license_scanner.poll()
                if result is None:
                    break
                license_result = result
                license_result_at = time.monotonic()
                if result.status == "searching":
                    log(
                        "license_scanned",
                        f"Driver license {result.scan.number} scanned",
                        license_number=result.scan.number,
                        license_state=result.scan.state,
                    )
                else:
                    record = result.record or {}
                    log(
                        "license_lookup_result",
                        f"Driver license lookup returned {result.status.replace('_', ' ')}",
                        license_number=result.scan.number,
                        license_state=result.scan.state,
                        lookup_status=result.status,
                        license_record_id=record.get("id"),
                        identity_id=record.get("identity_id"),
                        mismatches=result.mismatches,
                        error=result.error,
                    )
                    if result.status in ALERT_STATUSES:
                        camera.notify_alert()

            if frame is not None:
                if not stream_connected:
                    stream_connected = True
                    log("camera_stream_connected", f"{camera.name} stream connected")
                last_frame_at = time.monotonic()
                detector.submit(frame)
                license_scanner.submit(frame)

            detection = detector.poll()
            if detection is not None:
                detected_frame, tracked_faces, active_ids = detection
                for track_id, state in states.items():
                    if state.active and track_id not in active_ids:
                        state.active = False
                        if state.running:
                            state.generation += 1
                            state.running = False
                            state.status = None
                        log(
                            "subject_track_closed",
                            f"Subject {track_id} left the frame",
                            event_id=state.event_id,
                            track_id=track_id,
                        )

                for track_id, face in tracked_faces:
                    if track_id not in states:
                        states[track_id] = PersonState()
                        log(
                            "subject_detected",
                            f"Subject {track_id} detected",
                            event_id=states[track_id].event_id,
                            track_id=track_id,
                        )
                    state = states[track_id]
                    state.active = True
                    if state.name:
                        continue
                    now = time.monotonic()
                    if (
                        face.ready
                        and state.status is None
                        and not state.running
                        and now >= state.retry_at
                    ):
                        sample_frame, sample_rect = face.sample(detected_frame)
                        sample = FaceSample(sample_frame, sample_rect, face.rect)
                        state.photo = sample_frame.copy()
                        state.generation += 1
                        state.running = True
                        state.status = "searching"
                        state.recognition_request_id = str(uuid4())
                        log(
                            "recognition_submitted",
                            f"Subject {track_id} recognition submitted",
                            event_id=state.event_id,
                            track_id=track_id,
                            face_rect=sample.source_rect,
                            crop_rect=sample.rect,
                            generation=state.generation,
                            provider_request_id=state.recognition_request_id,
                        )
                        threading.Thread(
                            target=recognize_face,
                            args=(
                                recognition,
                                sample,
                                track_id,
                                state.generation,
                                recognition_results,
                            ),
                            daemon=True,
                        ).start()

            if frame is not None:
                display = frame.copy()
                label = "ROBIN INTELLIGENCE."
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
                        box_color if face.ready or state.name else BRAND_BLUE,
                        2,
                        cv2.LINE_AA,
                    )
                cv2.rectangle(display, (0, 0), (display.shape[1], 54), (20, 20, 20), -1)
                cv2.putText(display, label, (18, 37), cv2.FONT_HERSHEY_SIMPLEX, 0.85, BRAND_BLUE, 2, cv2.LINE_AA)
                if license_rect := license_scanner.visible_rect():
                    x, y, width, height = license_rect
                    cv2.rectangle(display, (x, y), (x + width, y + height), BRAND_BLUE, 3)
                    cv2.putText(
                        display,
                        "ID BARCODE",
                        (x, max(24, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        BRAND_BLUE,
                        2,
                        cv2.LINE_AA,
                    )
            elif time.monotonic() - last_frame_at > 2:
                if stream_connected:
                    stream_connected = False
                    log("camera_stream_disconnected", f"{camera.name} stream disconnected")
                detector.reset()
                tracked_faces = ()
                for track_id, state in states.items():
                    if state.active:
                        state.active = False
                        if state.running:
                            state.generation += 1
                            state.running = False
                            state.status = None
                        log(
                            "subject_track_closed",
                            f"Subject {track_id} left the frame",
                            event_id=state.event_id,
                            track_id=track_id,
                        )
                show_waiting(display)

            matched_ids = [track_id for track_id, state in states.items() if state.name]
            if selected_track_id not in matched_ids:
                selected_track_id = matched_ids[-1] if matched_ids else None
            _, _, window_width, window_height = cv2.getWindowImageRect(WINDOW)
            screen = render_live_window(
                display,
                states,
                selected_track_id,
                audit.recent(8),
                (window_width, window_height),
                license_result
                if time.monotonic() - license_result_at < 8
                else None,
            )
            cv2.imshow(WINDOW, screen)
            key = cv2.waitKey(30) & 0xFF
            if key == 9 and matched_ids:
                index = matched_ids.index(selected_track_id) if selected_track_id in matched_ids else -1
                selected_track_id = matched_ids[(index + 1) % len(matched_ids)]
            elif key in (27, ord("q")):
                break
    except KeyboardInterrupt:
        pass
    finally:
        log("camera_session_ended", "Field camera session ended")
        if detector:
            detector.close()
        if license_scanner:
            license_scanner.close()
        cv2.destroyAllWindows()
        camera.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", choices=("webrtc", "continuity"), default="webrtc")
    main(parser.parse_args().camera)
