"""Append-only JSON Lines evidence log for the live demo."""

import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data/audit/events.jsonl"


class EvidenceLog:
    def __init__(self, path=DEFAULT_PATH, clock=None, history_size=100):
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._events = deque(maxlen=history_size)
        self._lock = threading.Lock()

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("AUDIT_LOG_PATH", DEFAULT_PATH))

    def append(self, event_type, message, **fields):
        event = {
            "timestamp": self.clock().isoformat(),
            "event_type": event_type,
            "message": message,
            **fields,
        }
        line = json.dumps(event, separators=(",", ":"))
        event = json.loads(line)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as output:
                output.write(line + "\n")
            self._events.append(event)
        return event

    def recent(self, limit=8):
        with self._lock:
            return tuple(self._events)[-limit:]
