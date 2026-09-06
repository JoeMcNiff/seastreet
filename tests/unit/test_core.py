import unittest
from unittest.mock import patch

import numpy

from app.capture.camera_feed import WebRTCCamera, local_hostname
from app.detection.face_detection import DetectedFace, FaceTracker, detect_faces
from app.providers.face_recognition import FacialRecognitionService


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

    def test_match_alert_is_sent_to_the_phone(self):
        class Loop:
            def call_soon_threadsafe(self, callback):
                callback()

        class Alerts:
            readyState = "open"
            messages = []

            def send(self, message):
                self.messages.append(message)

        camera = WebRTCCamera()
        camera._loop = Loop()
        camera._alerts = Alerts()
        camera.notify_match()

        self.assertEqual(camera._alerts.messages, ["match"])

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

    def test_face_box_is_clamped_to_frame(self):
        with patch(
            "app.detection.face_detection.DETECTOR",
            Detector((detection(-10, -5, 60, 50),)),
        ):
            face = detect_faces(numpy.zeros((480, 640, 3), dtype=numpy.uint8))[0]

        self.assertEqual(face.rect, (0, 0, 67, 60))

    def test_face_crop_is_padded_clamped_and_independent(self):
        frame = numpy.zeros((100, 100, 3), dtype=numpy.uint8)
        crop = DetectedFace((0, 0, 20, 20), True, "SEARCHING...").crop(
            frame, padding=0.5
        )

        self.assertEqual(crop.shape, (30, 30, 3))
        crop[:] = 1
        self.assertFalse(frame.any())

    def test_face_id_survives_camera_motion_and_occlusion(self):
        tracker = FaceTracker()
        ready = lambda rect: DetectedFace(rect, True, "SEARCHING...")

        first_id = tracker.update((ready((100, 100, 100, 100)),))[0][0]
        for _ in range(20):
            tracker.update(())
        second_id = tracker.update((ready((180, 130, 100, 100)),))[0][0]

        self.assertEqual(first_id, second_id)

    def test_unconfigured_face_recognition_skips_providers(self):
        service = FacialRecognitionService()
        self.assertEqual(service.recognize_face(object()).status, "pending_provider")


if __name__ == "__main__":
    unittest.main()
