import json
import unittest

import cv2
import numpy

from app.providers.clearview import ClearviewClient, ClearviewError, ClearviewNoFace
from app.providers.face_recognition import FaceSample, FacialRecognitionService
from app.records.criminal_records import CriminalRecordsService
from app.records.supabase import SupabaseClient
from scripts.update_mock_criminal_records import OFFENSES, details_for, update_all


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        return self.payload


class IntegrationsTests(unittest.TestCase):
    def test_clearview_embed_request_and_validation(self):
        requests = []
        embedding = [1.0] + [0.0] * 511

        def open_request(request, timeout):
            requests.append(request)
            return Response({"data": {"embedding": embedding}})

        client = ClearviewClient("secret", opener=open_request)
        result = client.embed_bytes(b"jpeg", (1, 2, 30, 40))

        self.assertEqual(result, tuple(embedding))
        self.assertEqual(requests[0].get_header("Authorization"), "Bearer secret")
        self.assertIn(b'name="rect"', requests[0].data)
        self.assertIn(b"1,2,30,40", requests[0].data)

    def test_clearview_rejects_wrong_embedding_size(self):
        client = ClearviewClient(
            "secret",
            opener=lambda *_args, **_kwargs: Response({"data": {"embedding": [1.0]}}),
        )
        with self.assertRaises(ClearviewError):
            client.embed_bytes(b"jpeg", (1, 2, 30, 40))

    def test_camera_face_is_uploaded_as_a_padded_crop(self):
        client = ClearviewClient("secret")
        uploaded = {}

        def embed(image, rect):
            uploaded["image"] = image
            return rect

        client.embed_bytes = embed

        rect = client.embed_frame(numpy.zeros((100, 100, 3), dtype=numpy.uint8), (10, 10, 20, 20))
        crop = cv2.imdecode(
            numpy.frombuffer(uploaded["image"], dtype=numpy.uint8), cv2.IMREAD_COLOR
        )

        self.assertEqual(crop.shape[:2], (34, 34))
        self.assertEqual(rect, (7, 7, 20, 20))

    def test_clearview_detects_and_embeds_faces(self):
        requests = []
        embedding = [1.0] + [0.0] * 511

        def open_request(request, timeout):
            requests.append(request)
            return Response(
                {
                    "data": {
                        "faces": [
                            {
                                "rect": "1,2,30,40",
                                "confidence": 0.9,
                                "embedding": embedding,
                            }
                        ]
                    }
                }
            )

        faces = ClearviewClient("secret", opener=open_request).detect_and_embed_bytes(b"jpeg")

        self.assertEqual(faces[0].rect, (1.0, 2.0, 30.0, 40.0))
        self.assertEqual(faces[0].embedding, tuple(embedding))
        self.assertTrue(requests[0].full_url.endswith("/mlapi/v1/detect_and_embed"))
        self.assertNotIn(b'name="rect"', requests[0].data)

    def test_supabase_match_rpc(self):
        requests = []

        def open_request(request, timeout):
            requests.append(request)
            return Response(
                [
                    {
                        "identity_id": "person-1",
                        "display_name": "Person One",
                        "image_id": "image-1",
                        "similarity": 0.8,
                    }
                ]
            )

        client = SupabaseClient("https://example.supabase.co", "key", opener=open_request)
        matches = client.match_embedding([0.0] * 512)

        self.assertEqual(matches[0]["identity_id"], "person-1")
        self.assertEqual(matches[0]["display_name"], "Person One")
        self.assertTrue(requests[0].full_url.endswith("/rest/v1/rpc/match_identity_embeddings"))
        self.assertEqual(requests[0].get_header("Authorization"), "Bearer key")

    def test_criminal_records_are_looked_up_by_matched_identity(self):
        requests = []

        def open_request(request, timeout):
            requests.append(request)
            return Response(
                [
                    {
                        "identity_id": "person-1",
                        "active_warrant": True,
                        "primary_offense": "Synthetic offense",
                    }
                ]
            )

        client = SupabaseClient("https://example.supabase.co", "key", opener=open_request)
        result = CriminalRecordsService(client).lookup("person-1")

        self.assertEqual(result.status, "records_found")
        self.assertTrue(result.records[0]["active_warrant"])
        self.assertIn("criminal_records?identity_id=eq.person-1", requests[0].full_url)

    def test_mock_criminal_records_are_consistent(self):
        for record_id in range(1, len(OFFENSES) + 1):
            values = details_for(record_id)
            self.assertLessEqual(values["conviction_count"], values["arrest_count"])
            self.assertEqual(bool(values["warrant_number"]), values["active_warrant"])
            self.assertEqual(bool(values["warrant_issue_date"]), values["active_warrant"])
            if not values["active_warrant"]:
                self.assertEqual(values["wanted_level"], 0)

    def test_mock_criminal_record_update_writes_every_record(self):
        class Client:
            updates = []

            def list_criminal_records(self):
                return ({"id": 1}, {"id": 2})

            def update_criminal_record(self, record_id, values):
                self.updates.append((record_id, values))

        client = Client()
        self.assertEqual(update_all(True, client), 2)
        self.assertEqual([record_id for record_id, _values in client.updates], [1, 2])

    def test_missing_criminal_records_are_not_reported_as_an_error(self):
        client = SupabaseClient(
            "https://example.supabase.co",
            "key",
            opener=lambda *_args, **_kwargs: Response([]),
        )

        result = CriminalRecordsService(client).lookup("person-1")

        self.assertEqual(result.status, "no_records")
        self.assertEqual(result.records, ())

    def test_supabase_lists_bucket_recursively(self):
        responses = iter(
            (
                Response([{"name": "person-one", "id": None}]),
                Response([{"name": "face.jpg", "id": "object-id", "metadata": {}}]),
            )
        )
        client = SupabaseClient(
            "https://example.supabase.co", "key", opener=lambda *_args, **_kwargs: next(responses)
        )

        files = client.list_bucket_files()

        self.assertEqual(files[0]["path"], "person-one/face.jpg")

    def test_supabase_health_checks_required_tables(self):
        requests = []
        client = SupabaseClient(
            "https://example.supabase.co",
            "key",
            opener=lambda request, timeout: requests.append(request) or Response([]),
        )

        self.assertTrue(client.health())
        self.assertTrue(requests[0].full_url.endswith("identities?select=id&limit=1"))
        self.assertTrue(
            requests[1].full_url.endswith("criminal_records?select=id&limit=1")
        )
        self.assertEqual(len(requests), 2)

    def test_face_embedding_is_matched_and_grouped_by_identity(self):
        unit = tuple([1.0] + [0.0] * 511)

        class Embeddings:
            def embed_frame(self, frame, rect):
                self.sample = frame, rect
                return unit

        class Matches:
            def match_embedding(self, embedding, threshold, limit):
                self.embedding = embedding
                return (
                    {"identity_id": "one", "image_id": "a", "similarity": 0.6},
                    {"identity_id": "one", "image_id": "b", "similarity": 0.8},
                    {"identity_id": "two", "image_id": "c", "similarity": 0.7},
                )

            def identity_name(self, identity_id):
                return {"one": "Person One", "two": "Person Two"}[identity_id]

        clearview, supabase = Embeddings(), Matches()
        service = FacialRecognitionService(clearview, supabase)
        result = service.recognize_face(FaceSample(object(), (1, 2, 3, 4)))

        self.assertEqual(result.status, "candidates_found")
        self.assertEqual([candidate["identity_id"] for candidate in result.candidates], ["one", "two"])
        self.assertEqual([candidate["display_name"] for candidate in result.candidates], ["Person One", "Person Two"])
        self.assertEqual(supabase.embedding, unit)

    def test_unusable_face_requests_a_retry(self):
        class Embeddings:
            def embed_frame(self, _frame, _rect):
                raise ClearviewNoFace("unusable")

        service = FacialRecognitionService(Embeddings(), object())

        self.assertEqual(
            service.recognize_face(FaceSample(object(), (1, 2, 3, 4))).status,
            "retry_face",
        )


if __name__ == "__main__":
    unittest.main()
