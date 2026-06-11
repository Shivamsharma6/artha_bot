from __future__ import annotations

from dataclasses import dataclass, fields
import json
from pathlib import Path

from arthabot.audit_store import JsonlAuditStore
from arthabot.live_approval import HumanApprovalRecord, HumanApprovalWorkflow
from arthabot.live_promotion import LivePromotionChecklist, LivePromotionDecision


@dataclass(frozen=True)
class ApprovalPayload:
    strategy_version: str
    approved_by: str
    approved_at: str
    checklist: dict[str, bool]


class ApprovalInterface:
    def __init__(self, audit: JsonlAuditStore) -> None:
        self.audit = audit
        self.workflow = HumanApprovalWorkflow(audit)

    def render_request(self, *, strategy_version: str) -> str:
        checklist_lines = "\n".join(f"  {field.name}: false" for field in fields(LivePromotionChecklist))
        return (
            f"strategy_version: {strategy_version}\n"
            "approved_by: \n"
            "approved_at: \n"
            "checklist:\n"
            f"{checklist_lines}\n"
        )

    def submit(self, payload: ApprovalPayload) -> LivePromotionDecision:
        checklist = self._checklist_from_payload(payload.checklist)
        return self.workflow.approve(
            HumanApprovalRecord(
                strategy_version=payload.strategy_version,
                approved_by=payload.approved_by,
                approved_at=payload.approved_at,
                checklist=checklist,
            )
        )

    @staticmethod
    def load_payload(path: Path) -> ApprovalPayload:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ApprovalPayload(
            strategy_version=str(raw["strategy_version"]),
            approved_by=str(raw["approved_by"]),
            approved_at=str(raw["approved_at"]),
            checklist={key: bool(value) for key, value in raw["checklist"].items()},
        )

    @staticmethod
    def _checklist_from_payload(payload: dict[str, bool]) -> LivePromotionChecklist:
        required = {field.name for field in fields(LivePromotionChecklist)}
        provided = set(payload)
        missing = tuple(sorted(required - provided))
        if missing:
            raise ValueError(f"missing checklist fields: {', '.join(missing)}")
        extra = tuple(sorted(provided - required))
        if extra:
            raise ValueError(f"unknown checklist fields: {', '.join(extra)}")
        return LivePromotionChecklist(**{field.name: bool(payload[field.name]) for field in fields(LivePromotionChecklist)})

