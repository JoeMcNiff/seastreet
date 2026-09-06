"""Import one-face reference images from Supabase Storage."""

import argparse
import hashlib
import mimetypes
import os
import re

from app.providers.clearview import ClearviewClient, ClearviewError
from app.records.supabase import SupabaseClient, SupabaseError

SUPPORTED_TYPES = {"image/jpeg", "image/png"}


def identity_key(value):
    """Normalize a folder or display name for identity matching."""
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def valid_identity_folder(value):
    return re.fullmatch(r"[a-z0-9]+_[a-z0-9]+(?:_[a-z0-9]+)*", value) is not None


def display_name_from_folder(value):
    return " ".join(part.capitalize() for part in value.split("_"))


def parse_identity_names(values):
    names = {}
    for value in values or ():
        folder, separator, display_name = value.partition("=")
        folder = folder.strip()
        display_name = display_name.strip()
        if not separator or not folder or not display_name:
            raise ValueError(
                f"invalid identity name {value!r}; expected folder=First Last"
            )
        if not valid_identity_folder(folder):
            raise ValueError(
                f"identity folder must be lowercase names joined by underscores: {folder!r}"
            )
        words = display_name.split()
        if (
            identity_key(display_name) != identity_key(folder)
            or len(words) < 2
            or not words[0][0].isupper()
            or not words[-1][0].isupper()
        ):
            raise ValueError(
                f"display name {display_name!r} does not match folder {folder!r}"
            )
        names[folder] = display_name
    return names


def identity_candidates(identity_ref, identities):
    """Find existing identities whose ref or formatted name matches a folder."""
    key = identity_key(identity_ref)
    matches = {}
    for identity in identities:
        external_ref = identity.get("external_ref") or ""
        display_name = identity.get("display_name") or ""
        if identity_key(external_ref) == key or identity_key(display_name) == key:
            matches[str(identity["id"])] = identity

    # Prefer an active, properly spaced display name over a stale identity that
    # an older importer may have created as (for example) "Johndoe".
    return sorted(
        matches.values(),
        key=lambda identity: (
            identity.get("status") == "active",
            " " in (identity.get("display_name") or "").strip(),
            (identity.get("external_ref") or "") == identity_ref,
        ),
        reverse=True,
    )


def resolve_identity(identity_ref, identities_by_folder, identities, name_map, supabase):
    if identity_ref in identities_by_folder:
        return identities_by_folder[identity_ref]

    candidates = identity_candidates(identity_ref, identities)
    if candidates:
        identity = candidates[0]
        if len(candidates) > 1:
            print(
                f"WARN {identity_ref}: {len(candidates)} matching identities; "
                f"using {identity['display_name']} ({identity['id']})"
            )
    else:
        display_name = name_map.get(identity_ref, display_name_from_folder(identity_ref))
        identity = supabase.upsert_identity(identity_ref, display_name)
        identities.append(identity)
        print(f"NEW  {identity_ref}: created identity {display_name}")

    identities_by_folder[identity_ref] = identity
    return identity


def import_bucket(bucket="identity-images", prefix="", force=False, identity_names=None):
    clearview = ClearviewClient.from_environment()
    supabase = SupabaseClient.from_environment()
    model_version = os.environ.get("MLAPI_MODEL_VERSION", "demo-v1")
    name_map = parse_identity_names(identity_names)

    health = clearview.health()
    if not health.online or not health.ready:
        raise RuntimeError("Clearview is not ready")
    supabase.health()

    objects = supabase.list_bucket_files(bucket, prefix)
    identities = list(supabase.list_identities())
    identities_by_folder = {}
    imported = unchanged = skipped = 0
    for item in objects:
        path = item["path"]
        parts = path.split("/")
        if len(parts) < 2:
            print(f"SKIP {path}: expected <identity-ref>/<image-file>")
            skipped += 1
            continue

        identity_ref = parts[0]
        if not valid_identity_folder(identity_ref):
            print(
                f"SKIP {path}: identity folder must be lowercase names joined "
                "by underscores"
            )
            skipped += 1
            continue
        content_type = (item.get("metadata") or {}).get("mimetype") or mimetypes.guess_type(path)[0]
        if content_type not in SUPPORTED_TYPES:
            print(f"SKIP {path}: Clearview accepts JPEG or PNG")
            skipped += 1
            continue

        try:
            content = supabase.download_file(path, bucket)
            checksum = hashlib.sha256(content).hexdigest()
            image = supabase.image_by_storage_path(path, bucket)

            if image and image.get("sha256") == checksum and not force and supabase.has_embedding(
                image["id"], model_version=model_version
            ):
                identity = resolve_identity(
                    identity_ref, identities_by_folder, identities, name_map, supabase
                )
                supabase.assign_image_identity(identity["id"], image["id"])
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
            identity = resolve_identity(
                identity_ref, identities_by_folder, identities, name_map, supabase
            )
            supabase.assign_image_identity(identity["id"], image["id"])
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
    parser.add_argument(
        "--bucket",
        default="identity-images",
        metavar="BUCKET",
        help="import only from this Supabase Storage bucket (default: identity-images)",
    )
    parser.add_argument("--prefix", default="")
    parser.add_argument("--force", action="store_true", help="re-embed unchanged images")
    parser.add_argument(
        "--identity-name",
        action="append",
        default=[],
        metavar="FOLDER=FIRST LAST",
        help="display-name override for special capitalization (repeatable)",
    )
    args = parser.parse_args()
    import_bucket(args.bucket, args.prefix, args.force, args.identity_name)


if __name__ == "__main__":
    main()
