import json
import unittest

import numpy

from app.providers.clearview import ClearviewClient, ClearviewError, ClearviewNoFace
from app.providers.face_recognition import FaceSample, FacialRecognitionService
from app.records.supabase import SupabaseClient


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

    def test_camera_face_rectangle_is_padded(self):
        client = ClearviewClient("secret")
        client.embed_bytes = lambda _image, rect: rect

        rect = client.embed_frame(numpy.zeros((100, 100, 3), dtype=numpy.uint8), (10, 10, 20, 20))

        self.assertEqual(rect, (6.0, 6.0, 28.0, 28.0))

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
