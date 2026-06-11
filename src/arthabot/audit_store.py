from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from arthabot.observability import AuditEvent, AuditLogger


class JsonlAuditStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.logger = AuditLogger()

    def append(self, *, event_type: str, payload: dict[str, Any]) -> AuditEvent:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        event = self.logger.record(event_type=event_type, payload=payload)
        record = asdict(event)
        record["timestamp"] = event.timestamp.isoformat()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return event

    def read_all(self) -> list[AuditEvent]:
        if not self.path.exists():
            return []
        events: list[AuditEvent] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                events.append(
                    AuditEvent(
                        event_type=record["event_type"],
                        payload=record["payload"],
                        timestamp=datetime.fromisoformat(record["timestamp"]),
                    )
                )
        return events

