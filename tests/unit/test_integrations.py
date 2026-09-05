import json
import math
import unittest

from app.providers.clearview import ClearviewClient, ClearviewError
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
                                "landmarks": [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]],
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
            return Response([{"identity_id": "person-1", "image_id": "image-1", "similarity": 0.8}])

        client = SupabaseClient("https://example.supabase.co", "key", opener=open_request)
        matches = client.match_embedding([0.0] * 512)

        self.assertEqual(matches[0]["identity_id"], "person-1")
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

    def test_burst_is_averaged_normalized_and_grouped_by_identity(self):
        unit = tuple([1.0] + [0.0] * 511)

        class Embeddings:
            def embed_burst(self, samples):
                self.samples = tuple(samples)
                return (unit,) * 5

        class Matches:
            def match_embedding(self, embedding, threshold, limit):
                self.embedding = embedding
                return (
                    {"identity_id": "one", "image_id": "a", "similarity": 0.6},
                    {"identity_id": "one", "image_id": "b", "similarity": 0.8},
                    {"identity_id": "two", "image_id": "c", "similarity": 0.7},
                )

        clearview, supabase = Embeddings(), Matches()
        service = FacialRecognitionService(clearview, supabase)
        result = service.recognize([FaceSample(object(), (1, 2, 3, 4))] * 5)

        self.assertEqual(result.status, "candidates_found")
        self.assertEqual([candidate["identity_id"] for candidate in result.candidates], ["one", "two"])
        self.assertTrue(math.isclose(sum(value * value for value in supabase.embedding), 1.0))


if __name__ == "__main__":
    unittest.main()
