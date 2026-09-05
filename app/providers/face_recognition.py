"""Mock-only facial-recognition service boundary for the demo."""

from dataclasses import dataclass
from typing import Any, Sequence, Tuple


@dataclass(frozen=True)
class RecognitionResult:
    """A normalized provider result that still requires human review."""

    status: str
    snapshot_count: int
    candidates: Tuple[Any, ...] = ()


@dataclass(frozen=True)
class MockCandidate:
    """Non-identifying, synthetic candidate used to exercise the UI flow."""

    reference: str
    confidence: float


class FacialRecognitionService:
    """Return a deterministic synthetic candidate without a network request."""

    def recognize(self, snapshots: Sequence[Any]) -> RecognitionResult:
        if len(snapshots) != 5:
            raise ValueError("Facial recognition requires exactly five snapshots")

        return RecognitionResult(
            status="mock_candidate_returned",
            snapshot_count=len(snapshots),
            candidates=(MockCandidate(reference="SYNTHETIC-DEMO-001", confidence=0.87),),
        )
