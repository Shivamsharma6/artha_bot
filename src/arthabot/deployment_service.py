from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from time import sleep as default_sleep

from arthabot.audit_store import JsonlAuditStore
from arthabot.deployment_worker import DeploymentSchedulerTickResult
from arthabot.operational_audit_coverage import OperationalAuditCoverageChecker


@dataclass(frozen=True)
class DeploymentSchedulerServiceResult:
    tick_count: int
    must_stop_trading: bool
    reason_code: str


class DeploymentSchedulerService:
    def __init__(
        self,
        *,
        worker,
        audit: JsonlAuditStore,
        interval_seconds: int,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = default_sleep,
        audit_coverage_checker: OperationalAuditCoverageChecker | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.worker = worker
        self.audit = audit
        self.interval_seconds = interval_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep
        self.audit_coverage_checker = audit_coverage_checker

    def run(self, *, max_ticks: int | None = None) -> DeploymentSchedulerServiceResult:
        tick_count = 0
        while max_ticks is None or tick_count < max_ticks:
            result: DeploymentSchedulerTickResult = self.worker.tick(now=self.clock())
            tick_count += 1
            if result.must_stop_trading:
                self.audit.append(
                    event_type="deployment_scheduler_service_stopped",
                    payload={
                        "reason_code": result.reason_code,
                        "tick_count": tick_count,
                    },
                )
                return DeploymentSchedulerServiceResult(
                    tick_count=tick_count,
                    must_stop_trading=True,
                    reason_code=result.reason_code,
                )
            if max_ticks is None or tick_count < max_ticks:
                self.sleep(self.interval_seconds)

        self.audit.append(
            event_type="deployment_scheduler_service_completed",
            payload={
                "reason_code": "MAX_TICKS_REACHED",
                "tick_count": tick_count,
            },
        )
        if self.audit_coverage_checker is not None:
            coverage = self.audit_coverage_checker.evaluate_store(self.audit)
            if not coverage.ok:
                self.audit.append(
                    event_type="deployment_scheduler_service_stopped",
                    payload={
                        "reason_code": coverage.reason_code,
                        "tick_count": tick_count,
                        "missing_event_types": list(coverage.missing_event_types),
                    },
                )
                return DeploymentSchedulerServiceResult(
                    tick_count=tick_count,
                    must_stop_trading=True,
                    reason_code=coverage.reason_code,
                )
        return DeploymentSchedulerServiceResult(
            tick_count=tick_count,
            must_stop_trading=False,
            reason_code="MAX_TICKS_REACHED",
        )
