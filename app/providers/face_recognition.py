"""Burst embedding and identity-vector matching orchestration."""

import math
import os
from dataclasses import dataclass

from app.providers.clearview import ClearviewClient, ClearviewError
from app.records.supabase import SupabaseClient, SupabaseError


@dataclass(frozen=True)
class FaceSample:
    frame: object
    rect: tuple


@dataclass(frozen=True)
class RecognitionResult:
    status: str
    snapshot_count: int
    candidates: tuple = ()
    error: str = None


class FacialRecognitionService:
    def __init__(self, clearview=None, supabase=None, threshold=0.47, limit=10):
        if (clearview is None) != (supabase is None):
            raise ValueError("Clearview and Supabase clients must be configured together")
        self.clearview = clearview
        self.supabase = supabase
        self.threshold = threshold
        self.limit = limit

    @classmethod
    def from_environment(cls):
        required = ("MLAPI_TOKEN", "SUPABASE_URL", "SUPABASE_KEY")
        configured = [name for name in required if os.environ.get(name)]
        if not configured:
            return cls()
        missing = [name for name in required if name not in configured]
        if missing:
            raise ValueError("Missing environment variables: " + ", ".join(missing))
        return cls(
            ClearviewClient.from_environment(),
            SupabaseClient.from_environment(),
            float(os.environ.get("FACE_MATCH_THRESHOLD", "0.47")),
            int(os.environ.get("FACE_MATCH_LIMIT", "10")),
        )

    def recognize(self, snapshots):
        if len(snapshots) != 5:
            raise ValueError("Facial recognition requires exactly five snapshots")
        if self.clearview is None:
            return RecognitionResult("pending_provider", len(snapshots))

        try:
            embeddings = self.clearview.embed_burst(
                (sample.frame, sample.rect) for sample in snapshots
            )
            query = self.average_embeddings(embeddings)
            matches = self.supabase.match_embedding(query, self.threshold, self.limit)
            candidates = self.best_identity_matches(matches)
            status = "candidates_found" if candidates else "no_match"
            return RecognitionResult(status, len(snapshots), candidates)
        except (ClearviewError, SupabaseError, ValueError) as error:
            return RecognitionResult("provider_error", len(snapshots), error=str(error))

    @staticmethod
    def average_embeddings(embeddings):
        if not embeddings or any(len(embedding) != 512 for embedding in embeddings):
            raise ValueError("Expected one or more 512-value embeddings")
        mean = [sum(values) / len(embeddings) for values in zip(*embeddings)]
        norm = math.sqrt(sum(value * value for value in mean))
        if not math.isfinite(norm) or norm == 0:
            raise ValueError("Could not normalize the burst embedding")
        return tuple(value / norm for value in mean)

    @staticmethod
    def best_identity_matches(matches):
        best = {}
        for match in matches:
            identity_id = match["identity_id"]
            if identity_id not in best or match["similarity"] > best[identity_id]["similarity"]:
                best[identity_id] = match
        return tuple(sorted(best.values(), key=lambda match: match["similarity"], reverse=True))
