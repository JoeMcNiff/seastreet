"""Skeleton facial-recognition service boundary."""

from dataclasses import dataclass
from typing import Any, Sequence, Tuple


@dataclass(frozen=True)
class RecognitionResult:
    """Placeholder response until the Clearview embedding contract exists."""

    status: str
    snapshot_count: int
    candidates: Tuple[Any, ...] = ()


class FacialRecognitionService:
    """Accept a snapshot burst without making a provider request yet."""

    def recognize(self, snapshots: Sequence[Any]) -> RecognitionResult:
        if len(snapshots) != 5:
            raise ValueError("Facial recognition requires exactly five snapshots")

        return RecognitionResult(
            status="pending_provider",
            snapshot_count=len(snapshots),
        )