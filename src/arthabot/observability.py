from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SECRET_MARKERS = ("secret", "token", "api_key", "password", "credential")


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLogger:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, *, event_type: str, payload: dict[str, Any]) -> AuditEvent:
        event = AuditEvent(event_type=event_type, payload=self._redact(payload))
        self.events.append(event)
        return event

    def _redact(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            lowered = key.lower()
            if any(marker in lowered for marker in SECRET_MARKERS):
                redacted[key] = "[REDACTED]"
            elif isinstance(value, dict):
                redacted[key] = self._redact(value)
            else:
                redacted[key] = value
        return redacted

