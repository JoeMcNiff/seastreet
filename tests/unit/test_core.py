import socket
import unittest
from unittest.mock import patch

import numpy

from app.capture.camera_feed import _read
from app.detection.face_detection import DetectedFace, FaceTracker, detect_faces
from app.providers.face_recognition import FacialRecognitionService


class CoreTests(unittest.TestCase):
    def test_socket_reader_collects_a_complete_frame(self):
        reader, writer = socket.socketpair()
        self.addCleanup(reader.close)
        self.addCleanup(writer.close)
        writer.sendall(b"frame")
        self.assertEqual(_read(reader, 5), b"frame")

    def test_blank_image_has_no_face(self):
        self.assertEqual(detect_faces(numpy.zeros((480, 640, 3), dtype=numpy.uint8)), ())

    def test_multiple_faces_are_assessed_independently(self):
        class Detector:
            def __init__(self, results):
                self.results = results

            def detectMultiScale(self, *_args, **_kwargs):
                return self.results

        faces = Detector(((100, 100, 100, 100), (300, 100, 100, 100)))
        eyes = Detector(((20, 20, 20, 12), (65, 22, 20, 12)))
        frame = numpy.zeros((480, 640, 3), dtype=numpy.uint8)

        with patch("app.detection.face_detection.FACE", faces), patch(
            "app.detection.face_detection.EYES", eyes
        ):
            results = detect_faces(frame)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(face.ready for face in results))

    def test_unready_face_uses_neutral_status(self):
        detector = type(
            "Detector",
            (),
            {"detectMultiScale": lambda *_args, **_kwargs: ((100, 100, 40, 40),)},
        )()

        with patch("app.detection.face_detection.FACE", detector):
            face = detect_faces(numpy.zeros((480, 640, 3), dtype=numpy.uint8))[0]

        self.assertFalse(face.ready)
        self.assertEqual(face.reason, "FACE DETECTED")

    def test_face_crop_is_padded_clamped_and_independent(self):
        frame = numpy.zeros((100, 100, 3), dtype=numpy.uint8)
        crop = DetectedFace((0, 0, 20, 20), True, "FULL FACE READY").crop(
            frame, padding=0.5
        )

        self.assertEqual(crop.shape, (30, 30, 3))
        crop[:] = 1
        self.assertFalse(frame.any())

    def test_face_ids_survive_reordering_and_brief_occlusion(self):
        tracker = FaceTracker()
        ready = lambda rect: DetectedFace(rect, True, "FULL FACE READY")

        first = tracker.update((ready((100, 100, 100, 100)), ready((300, 100, 100, 100))))
        tracker.update(())
        second = tracker.update((ready((305, 100, 100, 100)), ready((105, 100, 100, 100))))

        first_ids = {face.rect[0]: track_id for track_id, face in first}
        second_ids = {face.rect[0]: track_id for track_id, face in second}
        self.assertEqual(first_ids[100], second_ids[105])
        self.assertEqual(first_ids[300], second_ids[305])

    def test_recognition_requires_three_samples(self):
        service = FacialRecognitionService()
        self.assertEqual(service.recognize([object()] * 3).status, "pending_provider")
        with self.assertRaises(ValueError):
            service.recognize([object()] * 2)


if __name__ == "__main__":
    unittest.main()
