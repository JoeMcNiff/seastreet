"""Import one-face reference images from Supabase Storage."""

import argparse
import hashlib
import mimetypes
import os

from app.providers.clearview import ClearviewClient, ClearviewError
from app.records.supabase import SupabaseClient, SupabaseError

SUPPORTED_TYPES = {"image/jpeg", "image/png"}


def import_bucket(bucket="identity-images", prefix="", force=False):
    clearview = ClearviewClient.from_environment()
    supabase = SupabaseClient.from_environment()
    model_version = os.environ.get("MLAPI_MODEL_VERSION", "demo-v1")

    health = clearview.health()
    if not health.online or not health.ready:
        raise RuntimeError("Clearview is not ready")
    supabase.health()

    objects = supabase.list_bucket_files(bucket, prefix)
    imported = unchanged = skipped = 0
    for item in objects:
        path = item["path"]
        parts = path.split("/")
        if len(parts) < 2:
            print(f"SKIP {path}: expected <identity-ref>/<image-file>")
            skipped += 1
            continue

        identity_ref = parts[0]
        content_type = (item.get("metadata") or {}).get("mimetype") or mimetypes.guess_type(path)[0]
        if content_type not in SUPPORTED_TYPES:
            print(f"SKIP {path}: Clearview accepts JPEG or PNG")
            skipped += 1
            continue

        try:
            content = supabase.download_file(path, bucket)
            checksum = hashlib.sha256(content).hexdigest()
            image = supabase.image_by_storage_path(path, bucket)
            identity = supabase.identity_by_external_ref(identity_ref)
            if identity is None:
                name = identity_ref.replace("_", " ").replace("-", " ").strip().title()
                identity = supabase.upsert_identity(identity_ref, name)

            if image and image.get("sha256") == checksum and not force and supabase.has_embedding(
                image["id"], model_version=model_version
            ):
                supabase.link_image(identity["id"], image["id"])
                print(f"OK   {path}: unchanged")
                unchanged += 1
                continue

            faces = clearview.detect_and_embed_bytes(content, parts[-1], content_type)
            if len(faces) != 1:
                print(f"SKIP {path}: expected 1 face, found {len(faces)}")
                skipped += 1
                continue

            face = faces[0]
            image = supabase.upsert_image(
                path,
                content_type,
                bucket,
                sha256=checksum,
                face_rect=list(face.rect),
            )
            supabase.link_image(identity["id"], image["id"])
            supabase.insert_embedding(
                image["id"], face.embedding, model_version=model_version
            )
            print(f"OK   {path}: embedded (confidence={face.confidence:.3f})")
            imported += 1
        except (ClearviewError, SupabaseError, ValueError) as error:
            print(f"SKIP {path}: {error}")
            skipped += 1

    print(
        f"Done: {imported} imported, {unchanged} unchanged, "
        f"{skipped} skipped, {len(objects)} total"
    )
    return imported, unchanged, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default="identity-images")
    parser.add_argument("--prefix", default="")
    parser.add_argument("--force", action="store_true", help="re-embed unchanged images")
    args = parser.parse_args()
    import_bucket(args.bucket, args.prefix, args.force)


if __name__ == "__main__":
    main()
