import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.audit.evidence_log import EvidenceLog


class AuditTests(unittest.TestCase):
    def test_event_is_persisted_and_available_to_the_live_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            log = EvidenceLog(
                path, clock=lambda: datetime(2026, 9, 6, 12, 30, tzinfo=timezone.utc)
            )

            event = log.append(
                "recognition_submitted",
                "Subject 2 recognition submitted",
                session_id="session-1",
                event_id="event-1",
                track_id=2,
                face_rect=(10, 20, 30, 40),
            )

            stored = json.loads(path.read_text().strip())
            self.assertEqual(stored, event)
            self.assertEqual(stored["face_rect"], [10, 20, 30, 40])
            self.assertEqual(log.recent(), (event,))


if __name__ == "__main__":
    unittest.main()
