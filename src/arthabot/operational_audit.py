from __future__ import annotations

from typing import Any

from arthabot.audit_store import JsonlAuditStore


class AuditedRuntime:
    def __init__(self, audit: JsonlAuditStore) -> None:
        self.audit = audit

    def record_decision(self, *, symbol: str, decision: dict[str, Any]) -> None:
        self.audit.append(event_type="decision", payload={"symbol": symbol, "decision": decision})

    def record_risk_rejection(self, *, symbol: str, reason_code: str) -> None:
        self.audit.append(event_type="risk_rejection", payload={"symbol": symbol, "reason_code": reason_code})

    def record_execution_update(self, *, symbol: str, order_id: str, status: str) -> None:
        self.audit.append(
            event_type="execution_update",
            payload={"symbol": symbol, "order_id": order_id, "status": status},
        )

