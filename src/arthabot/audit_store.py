from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from arthabot.observability import AuditEvent, AuditLogger


class JsonlAuditStore:
    def __init__(self, path: str | Path, *, max_bytes: int = 10_000_000, backup_count: int = 5) -> None:
        if max_bytes <= 0 or backup_count < 0:
            raise ValueError("audit rotation limits are invalid")
        self.path = Path(path)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.logger = AuditLogger()

    def append(self, *, event_type: str, payload: dict[str, Any]) -> AuditEvent:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        event = self.logger.record(event_type=event_type, payload=payload)
        record = asdict(event)
        record["timestamp"] = event.timestamp.isoformat()
        line = json.dumps(record, sort_keys=True) + "\n"
        self._rotate_if_needed(len(line.encode("utf-8")))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        return event

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        if not self.path.exists() or self.path.stat().st_size + incoming_bytes <= self.max_bytes:
            return
        if self.backup_count == 0:
            self.path.unlink()
            return
        oldest = self.path.with_name(f"{self.path.name}.{self.backup_count}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backup_count - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            if source.exists():
                source.replace(self.path.with_name(f"{self.path.name}.{index + 1}"))
        self.path.replace(self.path.with_name(f"{self.path.name}.1"))

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
