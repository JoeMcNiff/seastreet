import unittest
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy
import zxingcpp

from app.capture.camera_feed import WebRTCCamera, local_hostname
from app.detection.face_detection import (
    DetectedFace,
    FaceDetectionWorker,
    FaceTracker,
    detect_faces,
)
from app.detection.license_detection import (
    LicenseData,
    LicenseResult,
    LicenseScanner,
    parse_aamva,
    scan_license,
)
from app.providers.face_recognition import FacialRecognitionService
from app.ui.demo import ALERT_STATUSES
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
    LICENSE_PAYLOAD = (
        "@\n\x1e\rANSI 636026080102DL00410288ZA03290015DLDAQD1234567\n"
        "DCSDOE\nDACJANE\nDBB01021990\nDBA01022030\n"
        "DBD01022025\nDBC2\nDAJMA\n"
    )

    @patch("app.capture.camera_feed.socket.gethostname", return_value="Demo-Mac.local")
    def test_camera_url_uses_local_hostname(self, _hostname):
        self.assertEqual(local_hostname(), "Demo-Mac.local")

    def test_actionable_alert_is_sent_to_the_phone(self):
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
        camera.notify_alert()

        self.assertEqual(camera._alerts.messages, ["alert"])

    def test_only_records_and_bad_licenses_trigger_alerts(self):
        self.assertIn("records_found", ALERT_STATUSES)
        self.assertIn("license_not_found", ALERT_STATUSES)
        self.assertIn("license_mismatch", ALERT_STATUSES)
        self.assertIn("license_expired", ALERT_STATUSES)
        self.assertNotIn("no_records", ALERT_STATUSES)
        self.assertNotIn("license_found", ALERT_STATUSES)

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

    def test_aamva_driver_license_is_parsed(self):
        license_data = parse_aamva(self.LICENSE_PAYLOAD)

        self.assertEqual(license_data.number, "D1234567")
        self.assertEqual(license_data.first_name, "JANE")
        self.assertEqual(license_data.date_of_birth, "1990-01-02")
        self.assertEqual(license_data.sex, "F")

    def test_pdf417_driver_license_is_decoded(self):
        barcode = zxingcpp.create_barcode(
            self.LICENSE_PAYLOAD, zxingcpp.BarcodeFormat.PDF417
        )
        image = numpy.asarray(barcode.to_image(scale=3))

        license_data = scan_license(image)

        self.assertEqual(license_data.number, "D1234567")
        self.assertGreater(license_data.rect[2], 0)

    @patch("app.detection.license_detection._decode")
    def test_license_scan_retries_with_an_enhanced_image(self, decode):
        expected = LicenseData("D1234567")
        decode.side_effect = (None, expected)

        result = scan_license(numpy.zeros((100, 200, 3), dtype=numpy.uint8))

        self.assertIs(result, expected)
        self.assertEqual(decode.call_count, 2)
        self.assertEqual(decode.call_args_list[1].kwargs, {"scale": 1.5})

    def test_license_lookup_runs_off_the_calling_thread(self):
        scan = LicenseData("D1234567", first_name="JANE", state="MA", rect=(1, 2, 3, 4))

        class DMV:
            def licenses_by_number(self, _number):
                time.sleep(0.05)
                return ({"number": "D1234567", "first_name": "JANE", "state": "MA"},)

        scanner = LicenseScanner(DMV(), interval=0, scanner=lambda _frame: scan)
        try:
            started = time.monotonic()
            scanner.submit(object())
            self.assertLess(time.monotonic() - started, 0.01)
            deadline = time.monotonic() + 1
            results = []
            while time.monotonic() < deadline and not any(
                result.status == "license_found" for result in results
            ):
                result = scanner.poll()
                if result:
                    results.append(result)
                time.sleep(0.001)
        finally:
            scanner.close()

        self.assertEqual([result.status for result in results], ["searching", "license_found"])

    def test_face_id_survives_camera_motion_and_occlusion(self):
        tracker = FaceTracker()
        ready = lambda rect: DetectedFace(rect, True, "SEARCHING...")

        first_id = tracker.update((ready((100, 100, 100, 100)),))[0][0]
        for _ in range(20):
            tracker.update(())
        second_id = tracker.update((ready((180, 130, 100, 100)),))[0][0]

        self.assertEqual(first_id, second_id)

    def test_tracked_face_box_is_smoothed(self):
        tracker = FaceTracker()
        ready = lambda rect: DetectedFace(rect, True, "SEARCHING...")
        tracker.update((ready((100, 100, 100, 100)),))

        _track_id, face = tracker.update((ready((120, 110, 100, 100)),))[0]

        self.assertEqual(face.rect, (113, 106, 100, 100))

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

        license_result = LicenseResult(
            "license_found",
            LicenseData("D1234567", first_name="JANE", last_name="DOE", state="MA"),
            {"number": "D1234567", "first_name": "JANE", "last_name": "DOE"},
        )
        result = render_live_window(
            frame, {1: state}, 1, (), (1400, 600), license_result
        )
        self.assertEqual(result.shape, (600, 1400, 3))


if __name__ == "__main__":
    unittest.main()
