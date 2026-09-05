import socket
import unittest

import numpy

from app.capture.camera_feed import _read
from app.detection.face_detection import full_face
from app.providers.face_recognition import FacialRecognitionService


class CoreTests(unittest.TestCase):
    def test_socket_reader_collects_a_complete_frame(self):
        reader, writer = socket.socketpair()
        self.addCleanup(reader.close)
        self.addCleanup(writer.close)
        writer.sendall(b"frame")
        self.assertEqual(_read(reader, 5), b"frame")

    def test_blank_image_has_no_face(self):
        result = full_face(numpy.zeros((480, 640, 3), dtype=numpy.uint8))
        self.assertEqual(result, (False, [], "NO FACE"))

    def test_recognition_requires_five_snapshots(self):
        service = FacialRecognitionService()
        self.assertEqual(service.recognize([object()] * 5).snapshot_count, 5)
        with self.assertRaises(ValueError):
            service.recognize([object()] * 4)


if __name__ == "__main__":
    unittest.main()
