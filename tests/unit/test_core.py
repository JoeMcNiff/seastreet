import json
import unittest
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy

from app.capture.camera_feed import (
    ContinuityCamera,
    _profile_message,
    local_hostname,
)
from app.detection.face_detection import (
    DetectedFace,
    FaceDetectionWorker,
    FaceTracker,
    detect_faces,
)
from app.providers.face_recognition import FacialRecognitionService
from app.ui.demo import PersonState, SAMPLE_WINDOW_SECONDS, select_face_sample
from app.ui.live_panel import render_live_window


class Detector:
    def __init__(self, faces):
        self.faces = numpy.array(faces, dtype=numpy.float32) if faces else None

    def setInputSize(self, _size):
        pass

    def detect(self, _frame):
        return 0, self.faces


def detection(x, y, width, height):
    return (x, y, width, height, *([0] * 10), 0.9)


class CoreTests(unittest.TestCase):
    @patch("app.capture.camera_feed.socket.gethostname", return_value="Demo-Mac.local")
    def test_camera_url_uses_local_hostname(self, _hostname):
        self.assertEqual(local_hostname(), "Demo-Mac.local")

    def test_continuity_camera_reads_split_frame_data(self):
        class Connection:
            chunks = iter((b"jp", b"e", b"g"))

            def recv(self, _size):
                return next(self.chunks)

        self.assertEqual(ContinuityCamera._read(Connection(), 4), b"jpeg")

    def test_criminal_profile_message_contains_form_fields(self):
        photo = numpy.zeros((80, 60, 3), dtype=numpy.uint8)
        message = json.loads(
            _profile_message(
                "Jane Doe",
                0.81,
                {
                    "id": 4,
                    "active_warrant": True,
                    "primary_offense": "Aggravated assault",
                    "ignored": "private metadata",
                },
                photo,
            )
        )

        self.assertEqual(message["type"], "criminal_profile")
        self.assertEqual(message["name"], "Jane Doe")
        self.assertTrue(message["record"]["active_warrant"])
        self.assertNotIn("ignored", message["record"])
        self.assertTrue(message["photo"])

    def test_blank_image_has_no_face(self):
        self.assertEqual(detect_faces(numpy.zeros((480, 640, 3), dtype=numpy.uint8)), ())

    def test_multiple_faces_are_assessed_independently(self):
        frame = numpy.zeros((480, 640, 3), dtype=numpy.uint8)

        with patch(
            "app.detection.face_detection.DETECTOR",
            Detector((detection(100, 100, 100, 100), detection(300, 100, 100, 100))),
        ):
            results = detect_faces(frame)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(face.ready for face in results))

    def test_face_is_ready_without_eye_landmarks(self):
        with patch(
            "app.detection.face_detection.DETECTOR",
            Detector((detection(100, 100, 100, 100),)),
        ):
            face = detect_faces(numpy.zeros((480, 640, 3), dtype=numpy.uint8))[0]

        self.assertTrue(face.ready)

    def test_detector_preserves_confidence_and_landmarks(self):
        values = (100, 100, 100, 100, 120, 130, 180, 130, 150, 155, 125, 180, 175, 180, 0.9)
        with patch("app.detection.face_detection.DETECTOR", Detector((values,))):
            face = detect_faces(numpy.zeros((480, 640, 3), dtype=numpy.uint8))[0]

        self.assertAlmostEqual(face.confidence, 0.9)
        self.assertEqual(len(face.landmarks), 5)

    def test_face_box_is_clamped_to_frame(self):
        with patch(
            "app.detection.face_detection.DETECTOR",
            Detector((detection(-10, -5, 60, 50),)),
        ):
            face = detect_faces(numpy.zeros((1080, 1920, 3), dtype=numpy.uint8))[0]

        self.assertEqual(face.rect, (0, 0, 100, 90))

    def test_face_crop_is_padded_clamped_and_independent(self):
        frame = numpy.zeros((100, 100, 3), dtype=numpy.uint8)
        crop = DetectedFace((0, 0, 20, 20), True, "SEARCHING...").crop(
            frame, padding=0.5
        )

        self.assertEqual(crop.shape, (30, 30, 3))
        crop[:] = 1
        self.assertFalse(frame.any())

    def test_face_sample_has_a_crop_relative_rectangle(self):
        frame = numpy.zeros((100, 100, 3), dtype=numpy.uint8)

        crop, rect = DetectedFace((10, 20, 20, 30), True, "SEARCHING...").sample(
            frame, padding=0.5
        )

        self.assertEqual(crop.shape, (60, 40, 3))
        self.assertEqual(rect, (10, 15, 20, 30))

    def test_face_detection_worker_returns_results(self):
        with patch(
            "app.detection.face_detection.DETECTOR",
            Detector((detection(100, 100, 100, 100),)),
        ):
            worker = FaceDetectionWorker()
            try:
                worker.submit(numpy.zeros((480, 640, 3), dtype=numpy.uint8))
                deadline = time.monotonic() + 1
                result = None
                while result is None and time.monotonic() < deadline:
                    result = worker.poll()
                    time.sleep(0.001)
            finally:
                worker.close()

        self.assertEqual(result[1][0][1].rect, (100, 100, 100, 100))

    def test_face_id_survives_camera_motion_and_occlusion(self):
        tracker = FaceTracker()
        ready = lambda rect: DetectedFace(rect, True, "SEARCHING...")

        first_id = tracker.update((ready((100, 100, 100, 100)),))[0][0]
        for _ in range(20):
            tracker.update(())
        second_id = tracker.update((ready((180, 130, 100, 100)),))[0][0]

        self.assertEqual(first_id, second_id)

    def test_distant_face_does_not_inherit_an_occluded_track(self):
        tracker = FaceTracker()
        ready = lambda rect: DetectedFace(rect, True, "SEARCHING...")

        first_id = tracker.update((ready((100, 100, 100, 100)),))[0][0]
        for _ in range(20):
            tracker.update(())
        distant_id = tracker.update((ready((1000, 100, 100, 100)),))[0][0]

        self.assertNotEqual(first_id, distant_id)

    def test_tracking_smooths_display_but_preserves_current_detection(self):
        tracker = FaceTracker()
        ready = lambda rect: DetectedFace(rect, True, "SEARCHING...")
        tracker.update((ready((100, 100, 100, 100)),))

        _track_id, face = tracker.update((ready((120, 110, 100, 100)),))[0]

        self.assertEqual(face.rect, (120, 110, 100, 100))
        self.assertEqual(face.display_rect, (113, 106, 100, 100))

    def test_best_face_sample_is_selected_from_short_window(self):
        state = PersonState()
        face = DetectedFace((20, 20, 60, 60), True, "SEARCHING...", confidence=0.9)
        blurred = numpy.full((100, 100, 3), 127, dtype=numpy.uint8)
        sharp = blurred.copy()
        sharp[20:80:2, 20:80] = 0
        sharp[21:80:2, 20:80] = 255

        self.assertIsNone(select_face_sample(state, face, blurred, 10.0))
        self.assertIsNone(select_face_sample(state, face, sharp, 10.15))
        selected = select_face_sample(state, face, blurred, 10.01 + SAMPLE_WINDOW_SECONDS)

        sample, quality = selected
        self.assertGreater(quality, face.quality(blurred))
        self.assertTrue(numpy.array_equal(sample.frame, face.crop(sharp)))

    def test_unconfigured_face_recognition_skips_providers(self):
        service = FacialRecognitionService()
        self.assertEqual(service.recognize_face(object()).status, "pending_provider")

    def test_live_panel_is_added_without_changing_the_camera_frame(self):
        frame = numpy.zeros((720, 1080, 3), dtype=numpy.uint8)
        state = SimpleNamespace(
            name="Synthetic Person",
            similarity=0.82,
            status="candidates_found",
            records_status="records_found",
            records=(
                {
                    "record_status": "active",
                    "wanted_level": 2,
                    "active_warrant": True,
                    "primary_offense": "Synthetic offense",
                },
            ),
        )

        result = render_live_window(frame, {1: state}, 1, (), (1400, 600))

        self.assertEqual(result.shape, (600, 1400, 3))
        self.assertFalse(frame.any())
        self.assertTrue(result[:, 1050:].any())


if __name__ == "__main__":
    unittest.main()
