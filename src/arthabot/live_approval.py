from __future__ import annotations

from dataclasses import dataclass

from arthabot.audit_store import JsonlAuditStore
from arthabot.live_promotion import LivePromotionChecklist, LivePromotionDecision, LivePromotionGate


@dataclass(frozen=True)
class HumanApprovalRecord:
    strategy_version: str
    approved_by: str
    approved_at: str
    checklist: LivePromotionChecklist


class HumanApprovalWorkflow:
    def __init__(self, audit: JsonlAuditStore) -> None:
        self.audit = audit
        self._records: dict[str, HumanApprovalRecord] = {}
        self.gate = LivePromotionGate()

    def approve(self, record: HumanApprovalRecord) -> LivePromotionDecision:
        if not record.strategy_version.strip():
            raise ValueError("strategy_version is required")
        if not record.approved_by.strip():
            raise ValueError("approved_by is required")
        if not record.approved_at.strip():
            raise ValueError("approved_at is required")
        decision = self.gate.evaluate(record.checklist)
        self.audit.append(
            event_type="human_live_approval",
            payload={
                "strategy_version": record.strategy_version,
                "approved_by": record.approved_by,
                "approved_at": record.approved_at,
                "approved": decision.approved,
                "reason_code": decision.reason_code,
            },
        )
        if decision.approved:
            self._records[record.strategy_version] = record
        return decision

    def latest_approval(self, strategy_version: str) -> HumanApprovalRecord | None:
        return self._records.get(strategy_version)

