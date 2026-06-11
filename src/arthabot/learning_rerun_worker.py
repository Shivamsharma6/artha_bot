from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from arthabot.audit_store import JsonlAuditStore
from arthabot.learning import ProposedChange
from arthabot.learning_operations import BacktestRerunResult, LearningRerunWorkflow


@dataclass(frozen=True)
class LearningRerunWorkerResult:
    completed: int
    failed: int
    must_stop_trading: bool
    reason_code: str
    results: tuple[BacktestRerunResult, ...]


class LearningRerunWorker:
    def __init__(
        self,
        *,
        workflow: LearningRerunWorkflow,
        audit: JsonlAuditStore,
        max_attempts: int,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self.workflow = workflow
        self.audit = audit
        self.max_attempts = max_attempts

    def run(self, changes: list[ProposedChange]) -> LearningRerunWorkerResult:
        results: list[BacktestRerunResult] = []
        failed = 0
        for change in changes:
            rerun = self._run_with_retries(change)
            if rerun is None:
                failed += 1
                self.audit.append(
                    event_type="learning_rerun_worker_failed",
                    payload={
                        "change_name": change.name,
                        "target": change.target,
                        "attempts": self.max_attempts,
                        "completed": len(results),
                        "failed": failed,
                    },
                )
                return LearningRerunWorkerResult(
                    completed=len(results),
                    failed=failed,
                    must_stop_trading=True,
                    reason_code="LEARNING_RERUN_FAILED",
                    results=tuple(results),
                )
            results.append(rerun)

        self.audit.append(
            event_type="learning_rerun_worker_completed",
            payload={
                "completed": len(results),
                "failed": failed,
                "change_count": len(changes),
            },
        )
        return LearningRerunWorkerResult(
            completed=len(results),
            failed=failed,
            must_stop_trading=False,
            reason_code="LEARNING_RERUNS_COMPLETED",
            results=tuple(results),
        )

    def _run_with_retries(self, change: ProposedChange) -> BacktestRerunResult | None:
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.workflow.run(change)
            except Exception as exc:
                self.audit.append(
                    event_type="learning_rerun_attempt_failed",
                    payload={
                        "change_name": change.name,
                        "target": change.target,
                        "attempt": attempt,
                        "max_attempts": self.max_attempts,
                        "error": str(exc),
                    },
                )
        return None


class LearningRerunSchedulerHandler:
    def __init__(self, *, worker: LearningRerunWorker, changes: list[ProposedChange]) -> None:
        self.worker = worker
        self.changes = list(changes)

    def __call__(self, now: datetime | None = None) -> dict[str, Any]:
        result = self.worker.run(self.changes)
        return {
            "reason_code": result.reason_code,
            "completed": result.completed,
            "failed": result.failed,
            "must_stop_trading": result.must_stop_trading,
            "timestamp": now.isoformat() if now is not None else None,
        }
