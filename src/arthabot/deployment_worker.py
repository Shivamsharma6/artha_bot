from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from arthabot.audit_store import JsonlAuditStore
from arthabot.deployment_config import DeploymentJobConfig
from arthabot.scheduler import ScheduledJob, ScheduledJobResult, SchedulerRunner


@dataclass(frozen=True)
class DeploymentJobRegistry:
    factories: dict[str, Callable[[DeploymentJobConfig], ScheduledJob]]

    def build(self, config: DeploymentJobConfig) -> ScheduledJob:
        factory = self.factories.get(config.type)
        if factory is None:
            raise ValueError(f"unknown deployment job type: {config.type}")
        return factory(config)


@dataclass(frozen=True)
class DeploymentSchedulerTickResult:
    job_results: list[ScheduledJobResult]
    must_stop_trading: bool
    reason_code: str


class DeploymentSchedulerWorker:
    def __init__(
        self,
        *,
        audit: JsonlAuditStore,
        registry: DeploymentJobRegistry,
        job_configs: list[DeploymentJobConfig],
        timezone_name: str = "UTC",
    ) -> None:
        self.audit = audit
        self.runner = SchedulerRunner(audit=audit)
        self.timezone = ZoneInfo(timezone_name)
        self.jobs = [registry.build(config) for config in job_configs if config.enabled]

    def tick(self, *, now: datetime) -> DeploymentSchedulerTickResult:
        if now.tzinfo is None:
            raise ValueError("deployment scheduler clock must be timezone-aware")
        local_now = now.astimezone(self.timezone)
        job_results = [self.runner.run(job, now=local_now) for job in self.jobs]
        stop_result = next((result for result in job_results if result.must_stop_trading), None)
        if stop_result is not None:
            self.audit.append(
                event_type="deployment_scheduler_tick_stopped",
                payload={
                    "reason_code": stop_result.reason_code,
                    "job_name": stop_result.job_name,
                    "job_count": len(job_results),
                },
            )
            return DeploymentSchedulerTickResult(
                job_results=job_results,
                must_stop_trading=True,
                reason_code=stop_result.reason_code,
            )

        self.audit.append(
            event_type="deployment_scheduler_tick_completed",
            payload={
                "reason_code": "DEPLOYMENT_SCHEDULER_TICK_COMPLETED",
                "job_count": len(job_results),
                "executed_job_count": sum(result.executed for result in job_results),
            },
        )
        return DeploymentSchedulerTickResult(
            job_results=job_results,
            must_stop_trading=False,
            reason_code="DEPLOYMENT_SCHEDULER_TICK_COMPLETED",
        )
