"""Minimal Supabase REST, Storage, and pgvector RPC client."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request

from app.http import open_url


class SupabaseError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class SupabaseClient:
    def __init__(self, url, key, timeout=20, opener=open_url):
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY are required")
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout
        self._open = opener

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

    def create_identity(self, display_name, status="active"):
        return self._insert("identities", {"display_name": display_name, "status": status})

    def upsert_identity(self, external_ref, display_name, status="active"):
        return self._upsert(
            "identities",
            {"external_ref": external_ref, "display_name": display_name, "status": status},
            "external_ref",
        )

    def identity_by_external_ref(self, external_ref):
        rows = self._request(
            "/rest/v1/identities"
            f"?external_ref=eq.{quote(external_ref, safe='')}&select=*&limit=1"
        )
        return rows[0] if rows else None

    def create_image(self, storage_path, content_type, **metadata):
        values = {"storage_path": storage_path, "content_type": content_type}
        values.update(metadata)
        return self._insert("identity_images", values)

    def upsert_image(self, storage_path, content_type, bucket="identity-images", **metadata):
        values = {
            "storage_bucket": bucket,
            "storage_path": storage_path,
            "content_type": content_type,
        }
        values.update(metadata)
        return self._upsert("identity_images", values, "storage_bucket,storage_path")

    def link_image(self, identity_id, image_id):
        return self._upsert(
            "identity_image_links",
            {"identity_id": identity_id, "image_id": image_id},
            "identity_id,image_id",
        )

    def insert_embedding(self, image_id, embedding, provider="clearview", model_version="demo-v1"):
        return self._upsert(
            "image_embeddings",
            {
                "image_id": image_id,
                "embedding": list(embedding),
                "provider": provider,
                "model_version": model_version,
            },
            "image_id,provider,model_version",
        )

    def create_record(self, identity_id, record_type, record_data):
        return self._insert(
            "criminal_records",
            {
                "identity_id": identity_id,
                "record_type": record_type,
                "record_data": record_data,
            },
        )

    def upsert_record(self, identity_id, external_ref, record_type, record_data):
        return self._upsert(
            "criminal_records",
            {
                "identity_id": identity_id,
                "external_ref": external_ref,
                "record_type": record_type,
                "record_data": record_data,
            },
            "external_ref",
        )

    def match_embedding(self, embedding, threshold=0.47, limit=10):
        return tuple(
            self._request(
                "/rest/v1/rpc/match_identity_embeddings",
                method="POST",
                payload={
                    "query_embedding": list(embedding),
                    "match_threshold": threshold,
                    "match_count": limit,
                },
            )
        )

    def records_for_identity(self, identity_id):
        identity_id = quote(str(identity_id), safe="")
        return tuple(
            self._request(
                f"/rest/v1/criminal_records?identity_id=eq.{identity_id}&select=*"
            )
        )

    def image_by_checksum(self, sha256):
        rows = self._request(
            f"/rest/v1/identity_images?sha256=eq.{quote(sha256, safe='')}&select=*"
        )
        return rows[0] if rows else None

    def image_by_storage_path(self, storage_path, bucket="identity-images"):
        rows = self._request(
            "/rest/v1/identity_images"
            f"?storage_bucket=eq.{quote(bucket, safe='')}"
            f"&storage_path=eq.{quote(storage_path, safe='')}&select=*&limit=1"
        )
        return rows[0] if rows else None

    def has_embedding(self, image_id, provider="clearview", model_version="demo-v1"):
        image_id = quote(str(image_id), safe="")
        provider = quote(provider, safe="")
        model_version = quote(model_version, safe="")
        rows = self._request(
            "/rest/v1/image_embeddings"
            f"?image_id=eq.{image_id}&provider=eq.{provider}"
            f"&model_version=eq.{model_version}&select=id&limit=1"
        )
        return bool(rows)

    def upload_image(self, storage_path, content, content_type="image/jpeg", bucket="identity-images"):
        bucket = quote(bucket, safe="")
        storage_path = quote(storage_path.lstrip("/"), safe="/")
        return self._request(
            f"/storage/v1/object/{bucket}/{storage_path}",
            method="POST",
            body=content,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )

    def list_bucket_files(self, bucket="identity-images", prefix="", page_size=100):
        bucket = quote(bucket, safe="")
        pending = [prefix.strip("/")]
        files = []
        while pending:
            directory = pending.pop()
            offset = 0
            while True:
                items = self._request(
                    f"/storage/v1/object/list/{bucket}",
                    method="POST",
                    payload={
                        "prefix": directory,
                        "limit": page_size,
                        "offset": offset,
                        "sortBy": {"column": "name", "order": "asc"},
                    },
                )
                for item in items:
                    name = item.get("name")
                    if not name:
                        continue
                    path = f"{directory}/{name}" if directory else name
                    if item.get("id"):
                        files.append({**item, "path": path})
                    else:
                        pending.append(path)
                if len(items) < page_size:
                    break
                offset += page_size
        return tuple(files)

    def download_file(self, storage_path, bucket="identity-images"):
        bucket = quote(bucket, safe="")
        storage_path = quote(storage_path.lstrip("/"), safe="/")
        return self._request(
            f"/storage/v1/object/authenticated/{bucket}/{storage_path}", raw=True
        )

    def _insert(self, table, values):
        rows = self._request(
            f"/rest/v1/{table}",
            method="POST",
            payload=values,
            headers={"Prefer": "return=representation"},
        )
        if not rows:
            raise SupabaseError(f"Supabase did not return the inserted {table} row")
        return rows[0]

    def _upsert(self, table, values, conflict_columns):
        columns = quote(conflict_columns, safe=",")
        rows = self._request(
            f"/rest/v1/{table}?on_conflict={columns}",
            method="POST",
            payload=values,
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )
        if not rows:
            raise SupabaseError(f"Supabase did not return the upserted {table} row")
        return rows[0]

    def health(self):
        self._request("/rest/v1/identities?select=id&limit=1")
        return True

    def _request(self, path, method="GET", payload=None, body=None, headers=None, raw=False):
        request_headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Accept": "application/json",
        }
        request_headers.update(headers or {})
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(self.url + path, data=body, headers=request_headers, method=method)
        try:
            with self._open(request, timeout=self.timeout) as response:
                content = response.read()
                if raw:
                    return content
                return json.loads(content.decode("utf-8")) if content else None
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise SupabaseError(detail or error.reason, error.code) from error
        except (URLError, TimeoutError) as error:
            raise SupabaseError(f"Supabase request failed: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SupabaseError("Supabase returned invalid JSON") from error
