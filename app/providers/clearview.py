"""Small authenticated client for the Clearview demo embedding API."""

import json
import math
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

from app.http import open_url


DEFAULT_URL = "https://ip-10-200-46-204.tail5891d.ts.net"


class ClearviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class HealthStatus:
    online: bool
    ready: bool


@dataclass(frozen=True)
class EmbeddedFace:
    rect: tuple
    confidence: float
    embedding: tuple


class ClearviewClient:
    def __init__(self, token, base_url=DEFAULT_URL, timeout=20, opener=open_url):
        if not token:
            raise ValueError("MLAPI_TOKEN is required")
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._open = opener

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("MLAPI_TOKEN"), os.environ.get("MLAPI_URL", DEFAULT_URL))

    def health(self):
        payload = self._request("/mlapi/online")
        data = payload.get("data", {})
        return HealthStatus(bool(data.get("online")), bool(data.get("ready")))

    def embed_bytes(self, image, rect, filename="frame.jpg", content_type="image/jpeg"):
        rect = self._validate_rect(rect)
        self._validate_image(image, content_type)
        rect_text = ",".join(f"{value:.6g}" for value in rect)
        body, boundary = self._multipart(
            image, Path(filename).name, content_type, (("rect", rect_text),)
        )
        payload = self._request(
            "/mlapi/v1/embed",
            method="POST",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        return self._validate_embedding(payload.get("data", {}).get("embedding"))

    def detect_and_embed_bytes(self, image, filename="image.jpg", content_type="image/jpeg"):
        self._validate_image(image, content_type)
        body, boundary = self._multipart(image, Path(filename).name, content_type)
        payload = self._request(
            "/mlapi/v1/detect_and_embed",
            method="POST",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        faces = payload.get("data", {}).get("faces")
        if not isinstance(faces, list):
            raise ClearviewError("Clearview detect-and-embed response has no face list")
        return tuple(self._validate_face(face) for face in faces)

    def embed_frame(self, frame, rect):
        import cv2

        x, y, width, height = self._validate_rect(rect)
        frame_height, frame_width = frame.shape[:2]
        if x < 0 or y < 0 or x + width > frame_width or y + height > frame_height:
            raise ValueError("Face rectangle is outside the image")
        encoded, jpeg = cv2.imencode(".jpg", frame)
        if not encoded:
            raise ClearviewError("Could not encode camera frame")
        return self.embed_bytes(jpeg.tobytes(), (x, y, width, height))

    def embed_burst(self, samples):
        with ThreadPoolExecutor(max_workers=5) as workers:
            return tuple(workers.map(lambda sample: self.embed_frame(*sample), samples))

    def _request(self, path, method="GET", body=None, content_type=None):
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        request = Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            with self._open(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ClearviewError(f"HTTP {error.code}: {detail or error.reason}") from error
        except (URLError, TimeoutError) as error:
            raise ClearviewError(f"Clearview request failed: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ClearviewError("Clearview returned invalid JSON") from error

    @staticmethod
    def _validate_rect(rect):
        if isinstance(rect, str):
            rect = rect.split(",")
        if len(rect) != 4:
            raise ValueError("Face rectangle must contain x, y, width, height")
        values = tuple(float(value) for value in rect)
        if not all(math.isfinite(value) for value in values) or values[2] <= 0 or values[3] <= 0:
            raise ValueError("Face rectangle must contain finite positive dimensions")
        return values

    @staticmethod
    def _validate_image(image, content_type):
        if not image:
            raise ValueError("Image must not be empty")
        if content_type not in ("image/jpeg", "image/png"):
            raise ValueError("Clearview accepts JPEG or PNG images")

    @classmethod
    def _validate_face(cls, face):
        try:
            confidence = float(face["confidence"])
            if not math.isfinite(confidence):
                raise ValueError
            return EmbeddedFace(
                cls._validate_rect(face["rect"]),
                confidence,
                cls._validate_embedding(face["embedding"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ClearviewError("Clearview returned an invalid face") from error

    @staticmethod
    def _validate_embedding(embedding):
        if not isinstance(embedding, list) or len(embedding) != 512:
            raise ClearviewError("Clearview embedding must contain 512 values")
        values = tuple(float(value) for value in embedding)
        if not all(math.isfinite(value) for value in values):
            raise ClearviewError("Clearview embedding contains a non-finite value")
        norm = math.sqrt(sum(value * value for value in values))
        if not math.isclose(norm, 1.0, rel_tol=0.02, abs_tol=0.02):
            raise ClearviewError(f"Clearview embedding is not normalized (norm={norm:.4f})")
        return values

    @staticmethod
    def _multipart(image, filename, content_type, fields=()):
        boundary = "----seastreet-" + uuid.uuid4().hex
        marker = boundary.encode("ascii")
        parts = [
            b"--" + marker,
            b'Content-Disposition: form-data; name="file"; filename="' + filename.encode("utf-8") + b'"',
            b"Content-Type: " + content_type.encode("ascii"),
            b"",
            image,
        ]
        for name, value in fields:
            parts.extend(
                (
                    b"--" + marker,
                    b'Content-Disposition: form-data; name="' + name.encode("ascii") + b'"',
                    b"",
                    value.encode("utf-8"),
                )
            )
        parts.extend((b"--" + marker + b"--", b""))
        return b"\r\n".join(parts), boundary
