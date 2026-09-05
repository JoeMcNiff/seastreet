"""Enroll synthetic identities and reference images from a JSON manifest."""

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path

import cv2

from app.detection.face_detection import full_face
from app.providers.clearview import ClearviewClient
from app.records.supabase import SupabaseClient


def safe_path(value):
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


def enroll(manifest_path):
    clearview = ClearviewClient.from_environment()
    supabase = SupabaseClient.from_environment()
    model_version = os.environ.get("MLAPI_MODEL_VERSION", "demo-v1")
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())

    health = clearview.health()
    if not health.online or not health.ready:
        raise RuntimeError("Clearview is not ready")
    supabase.health()

    for identity_data in manifest["identities"]:
        external_ref = identity_data["external_ref"]
        identity = supabase.upsert_identity(external_ref, identity_data["display_name"])

        for relative_path in identity_data.get("images", []):
            image_path = (manifest_path.parent / relative_path).resolve()
            content = image_path.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            content_type = mimetypes.guess_type(image_path.name)[0]
            if content_type not in ("image/jpeg", "image/png"):
                raise ValueError(f"{image_path}: Clearview accepts JPEG or PNG")
            image = supabase.image_by_checksum(checksum)

            if image is None:
                frame = cv2.imread(str(image_path))
                if frame is None:
                    raise ValueError(f"Could not decode {image_path}")
                detected, boxes, reason = full_face(frame)
                if not detected:
                    raise ValueError(f"{image_path}: {reason}")
                storage_path = f"{safe_path(external_ref)}/{checksum}{image_path.suffix.lower()}"
                supabase.upload_image(storage_path, content, content_type)
                image = supabase.create_image(
                    storage_path,
                    content_type,
                    sha256=checksum,
                    width=frame.shape[1],
                    height=frame.shape[0],
                    face_rect=list(boxes[0]),
                )

            supabase.link_image(identity["id"], image["id"])
            if not supabase.has_embedding(image["id"], model_version=model_version):
                rect = image.get("face_rect")
                if not rect:
                    raise ValueError(f"{image_path}: stored image has no face rectangle")
                embedding = clearview.embed_bytes(content, rect, image_path.name, content_type)
                supabase.insert_embedding(image["id"], embedding, model_version=model_version)

        for index, record in enumerate(identity_data.get("records", []), start=1):
            record_ref = record.get("external_ref", f"{external_ref}-record-{index}")
            supabase.upsert_record(
                identity["id"],
                record_ref,
                record.get("record_type", "unspecified"),
                record.get("record_data", {}),
            )
        print(f"Enrolled {identity_data['display_name']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Path to the synthetic enrollment manifest")
    enroll(parser.parse_args().manifest)


if __name__ == "__main__":
    main()
