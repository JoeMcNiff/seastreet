import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.import_bucket_faces import (
    display_name_from_folder,
    identity_candidates,
    identity_key,
    import_bucket,
    parse_identity_names,
    valid_identity_folder,
)


class FakeClearview:
    def __init__(self, faces):
        self.faces = faces

    def health(self):
        return SimpleNamespace(online=True, ready=True)

    def detect_and_embed_bytes(self, *_args):
        return self.faces


class FakeSupabase:
    def __init__(self, objects, identities=(), images=None, links=None):
        self.objects = objects
        self.identities = list(identities)
        self.images = dict(images or {})
        self.links = dict(links or {})
        self.created_identities = []
        self.list_calls = []
        self.download_calls = []
        self.image_lookup_calls = []

    def health(self):
        return True

    def list_bucket_files(self, bucket, prefix):
        self.list_calls.append((bucket, prefix))
        return self.objects

    def list_identities(self):
        return tuple(self.identities)

    def download_file(self, path, bucket):
        self.download_calls.append((path, bucket))
        return path.encode()

    def image_by_storage_path(self, path, bucket):
        self.image_lookup_calls.append((path, bucket))
        return self.images.get(path)

    def has_embedding(self, _image_id, model_version):
        return False

    def upsert_identity(self, external_ref, display_name):
        identity = {
            "id": f"identity-{len(self.created_identities) + 1}",
            "external_ref": external_ref,
            "display_name": display_name,
            "status": "active",
        }
        self.created_identities.append(identity)
        return identity

    def upsert_image(self, path, content_type, bucket, **metadata):
        existing = self.images.get(path)
        image = {
            "id": existing["id"] if existing else f"image-{len(self.images) + 1}",
            "storage_path": path,
            "content_type": content_type,
            "storage_bucket": bucket,
            **metadata,
        }
        self.images[path] = image
        return image

    def assign_image_identity(self, identity_id, image_id):
        self.links[image_id] = next(
            identity
            for identity in self.identities + self.created_identities
            if identity["id"] == identity_id
        )

    def insert_embedding(self, *_args, **_kwargs):
        return None


class ImportBucketFacesTests(unittest.TestCase):
    def test_compact_folder_matches_formatted_display_name(self):
        proper = {
            "id": "proper",
            "external_ref": None,
            "display_name": "Joe McNiff",
            "status": "active",
        }
        stale_duplicate = {
            "id": "stale",
            "external_ref": "joemcniff",
            "display_name": "Joemcniff",
            "status": "active",
        }

        self.assertEqual(identity_key("Joe McNiff"), "joemcniff")
        self.assertEqual(
            identity_candidates("joe_mcniff", [stale_duplicate, proper])[0], proper
        )

    def test_underscore_folder_produces_a_formatted_display_name(self):
        self.assertTrue(valid_identity_folder("jane_doe"))
        self.assertFalse(valid_identity_folder("janedoe"))
        self.assertEqual(display_name_from_folder("jane_doe"), "Jane Doe")

    def test_identity_name_override_must_match_underscore_folder(self):
        self.assertEqual(
            parse_identity_names(["jane_doe=Jane Doe"]), {"jane_doe": "Jane Doe"}
        )
        with self.assertRaises(ValueError):
            parse_identity_names(["jane_doe=Janet Doe"])
        with self.assertRaises(ValueError):
            parse_identity_names(["jane_doe=jane doe"])

    def test_one_new_identity_is_reused_for_all_images_in_folder(self):
        objects = (
            {"path": "jane_doe/front.jpg", "metadata": {"mimetype": "image/jpeg"}},
            {"path": "jane_doe/side.jpg", "metadata": {"mimetype": "image/jpeg"}},
        )
        face = SimpleNamespace(rect=(1, 2, 3, 4), embedding=(0.1,), confidence=0.9)
        supabase = FakeSupabase(objects)

        with (
            patch(
                "scripts.import_bucket_faces.ClearviewClient.from_environment",
                return_value=FakeClearview((face,)),
            ),
            patch(
                "scripts.import_bucket_faces.SupabaseClient.from_environment",
                return_value=supabase,
            ),
        ):
            result = import_bucket()

        self.assertEqual(result, (2, 0, 0))
        self.assertEqual(len(supabase.created_identities), 1)
        self.assertEqual(
            {identity["id"] for identity in supabase.links.values()}, {"identity-1"}
        )

    def test_bucket_folder_overrides_an_images_existing_identity(self):
        objects = (
            {"path": "jane_doe/front.jpg", "metadata": {"mimetype": "image/jpeg"}},
            {"path": "jane_doe/side.jpg", "metadata": {"mimetype": "image/jpeg"}},
        )
        proper = {
            "id": "proper",
            "external_ref": None,
            "display_name": "Jane Doe",
            "status": "active",
        }
        stale = {
            "id": "stale",
            "external_ref": "jane_doe",
            "display_name": "Janedoe",
            "status": "active",
        }
        existing_image = {"id": "existing", "sha256": "old"}
        face = SimpleNamespace(rect=(1, 2, 3, 4), embedding=(0.1,), confidence=0.9)
        supabase = FakeSupabase(
            objects,
            identities=(proper, stale),
            images={"jane_doe/front.jpg": existing_image},
            links={"existing": stale},
        )

        with (
            patch(
                "scripts.import_bucket_faces.ClearviewClient.from_environment",
                return_value=FakeClearview((face,)),
            ),
            patch(
                "scripts.import_bucket_faces.SupabaseClient.from_environment",
                return_value=supabase,
            ),
        ):
            import_bucket()

        self.assertEqual(supabase.links["existing"], proper)
        self.assertEqual(supabase.links["image-2"], proper)

    def test_bucket_parameter_scopes_every_storage_operation(self):
        path = "jane_doe/front.jpg"
        objects = ({"path": path, "metadata": {"mimetype": "image/jpeg"}},)
        face = SimpleNamespace(rect=(1, 2, 3, 4), embedding=(0.1,), confidence=0.9)
        supabase = FakeSupabase(objects)

        with (
            patch(
                "scripts.import_bucket_faces.ClearviewClient.from_environment",
                return_value=FakeClearview((face,)),
            ),
            patch(
                "scripts.import_bucket_faces.SupabaseClient.from_environment",
                return_value=supabase,
            ),
        ):
            import_bucket(bucket="event-faces")

        self.assertEqual(supabase.list_calls, [("event-faces", "")])
        self.assertEqual(supabase.download_calls, [(path, "event-faces")])
        self.assertEqual(supabase.image_lookup_calls, [(path, "event-faces")])
        self.assertEqual(supabase.images[path]["storage_bucket"], "event-faces")

    def test_unusable_image_does_not_create_identity(self):
        objects = (
            {"path": "jane_doe/front.jpg", "metadata": {"mimetype": "image/jpeg"}},
        )
        supabase = FakeSupabase(objects)

        with (
            patch(
                "scripts.import_bucket_faces.ClearviewClient.from_environment",
                return_value=FakeClearview(()),
            ),
            patch(
                "scripts.import_bucket_faces.SupabaseClient.from_environment",
                return_value=supabase,
            ),
        ):
            result = import_bucket()

        self.assertEqual(result, (0, 0, 1))
        self.assertEqual(supabase.created_identities, [])


if __name__ == "__main__":
    unittest.main()
