from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from arthabot.audit_store import JsonlAuditStore


@dataclass(frozen=True)
class TimeOfDaySchedule:
    run_at: time

    @classmethod
    def from_string(cls, value: str) -> TimeOfDaySchedule:
        hour, minute = value.split(":", 1)
        return cls(run_at=time(hour=int(hour), minute=int(minute)))

    def is_due(self, *, now: datetime, last_run_at: datetime | None) -> bool:
        if now.time() < self.run_at:
            return False
        if last_run_at is None:
            return True
        return last_run_at.date() < now.date()


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    schedule: TimeOfDaySchedule
    action: Callable[[datetime], Any]
    critical: bool
    last_run_at: datetime | None = None


@dataclass(frozen=True)
class ScheduledJobResult:
    job_name: str
    executed: bool
    must_stop_trading: bool
    reason_code: str
    payload: Any = None


class SchedulerRunner:
    def __init__(self, *, audit: JsonlAuditStore) -> None:
        self.audit = audit

    def run(self, job: ScheduledJob, *, now: datetime) -> ScheduledJobResult:
        if not job.schedule.is_due(now=now, last_run_at=job.last_run_at):
            self.audit.append(
                event_type="scheduled_job_skipped",
                payload={"job_name": job.name, "reason_code": "SCHEDULE_NOT_DUE"},
            )
            return ScheduledJobResult(
                job_name=job.name,
                executed=False,
                must_stop_trading=False,
                reason_code="SCHEDULE_NOT_DUE",
            )

        try:
            payload = job.action(now)
        except Exception as exc:
            self.audit.append(
                event_type="scheduled_job_failed",
                payload={"job_name": job.name, "reason_code": "SCHEDULED_JOB_FAILED", "error": str(exc)},
            )
            return ScheduledJobResult(
                job_name=job.name,
                executed=True,
                must_stop_trading=job.critical,
                reason_code="SCHEDULED_JOB_FAILED",
            )

        self.audit.append(
            event_type="scheduled_job_completed",
            payload={"job_name": job.name, "reason_code": "SCHEDULED_JOB_COMPLETED"},
        )
        return ScheduledJobResult(
            job_name=job.name,
            executed=True,
            must_stop_trading=False,
            reason_code="SCHEDULED_JOB_COMPLETED",
            payload=payload,
        )
