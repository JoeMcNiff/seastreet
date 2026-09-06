"""Face embedding and identity-vector matching orchestration."""

import os
from dataclasses import dataclass

from app.providers.clearview import ClearviewClient, ClearviewError, ClearviewNoFace
from app.records.supabase import SupabaseClient, SupabaseError


@dataclass(frozen=True)
class FaceSample:
    frame: object
    rect: tuple


@dataclass(frozen=True)
class RecognitionResult:
    status: str
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

    def recognize_face(self, sample):
        if self.clearview is None:
            return RecognitionResult("pending_provider")

        try:
            embedding = self.clearview.embed_frame(sample.frame, sample.rect)
            matches = self.supabase.match_embedding(embedding, self.threshold, self.limit)
            candidates = self.best_identity_matches(matches)
            candidates = tuple(
                candidate
                if candidate.get("display_name")
                else {
                    **candidate,
                    "display_name": self.supabase.identity_name(candidate["identity_id"]),
                }
                for candidate in candidates
            )
            status = "candidates_found" if candidates else "no_match"
            return RecognitionResult(status, candidates)
        except ClearviewNoFace:
            return RecognitionResult("retry_face")
        except (ClearviewError, SupabaseError, ValueError) as error:
            return RecognitionResult("provider_error", error=str(error))

    @staticmethod
    def best_identity_matches(matches):
        best = {}
        for match in matches:
            identity_id = match["identity_id"]
            if identity_id not in best or match["similarity"] > best[identity_id]["similarity"]:
                best[identity_id] = match
        return tuple(sorted(best.values(), key=lambda match: match["similarity"], reverse=True))
