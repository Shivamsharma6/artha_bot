from __future__ import annotations

from dataclasses import dataclass

from arthabot.audit_store import JsonlAuditStore
from arthabot.observability import AuditEvent


REQUIRED_RUNTIME_AUDIT_EVENTS = (
    "decision",
    "risk_rejection",
    "risk_approved",
    "paper_signal_executed",
    "provider_paper_loop_completed",
    "scheduled_job_completed",
    "deployment_scheduler_service_completed",
    "strategy_calibration_completed",
    "strategy_calibration_batch_completed",
    "kite_balance_smoke_probe_completed",
    "human_live_approval",
)


@dataclass(frozen=True)
class OperationalAuditCoverageResult:
    ok: bool
    missing_event_types: tuple[str, ...]
    reason_code: str


class OperationalAuditCoverageChecker:
    def __init__(self, *, required_events: tuple[str, ...] = REQUIRED_RUNTIME_AUDIT_EVENTS) -> None:
        self.required_events = required_events

    def evaluate(self, events: list[AuditEvent]) -> OperationalAuditCoverageResult:
        observed = {event.event_type for event in events}
        missing = tuple(sorted(set(self.required_events) - observed))
        if missing:
            return OperationalAuditCoverageResult(
                ok=False,
                missing_event_types=missing,
                reason_code="AUDIT_COVERAGE_MISSING_EVENTS",
            )
        return OperationalAuditCoverageResult(
            ok=True,
            missing_event_types=(),
            reason_code="AUDIT_COVERAGE_OK",
        )

    def evaluate_store(self, store: JsonlAuditStore) -> OperationalAuditCoverageResult:
        return self.evaluate(store.read_all())
