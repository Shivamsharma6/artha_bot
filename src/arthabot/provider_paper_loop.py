from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from arthabot.audit_store import JsonlAuditStore
from arthabot.execution import OrderResult
from arthabot.runtime_pipeline import PaperRuntimePipeline
from arthabot.scheduler import ScheduledJob, ScheduledJobResult, SchedulerRunner
from arthabot.strategies import TradeCandidate


@dataclass(frozen=True)
class ProviderBackedPaperLoopResult:
    job_results: list[ScheduledJobResult]
    signal_results: list[OrderResult | None]
    must_stop_trading: bool
    reason_code: str


class ProviderBackedPaperLoop:
    def __init__(
        self,
        *,
        scheduler: SchedulerRunner,
        pipeline: PaperRuntimePipeline,
        audit: JsonlAuditStore,
    ) -> None:
        self.scheduler = scheduler
        self.pipeline = pipeline
        self.audit = audit

    def run(
        self,
        *,
        jobs: list[ScheduledJob],
        candidates: list[TradeCandidate],
        now: datetime,
    ) -> ProviderBackedPaperLoopResult:
        job_results = [self.scheduler.run(job, now=now) for job in jobs]
        stop_result = next((result for result in job_results if result.must_stop_trading), None)
        if stop_result is not None:
            self.audit.append(
                event_type="provider_paper_loop_stopped",
                payload={
                    "reason_code": stop_result.reason_code,
                    "job_name": stop_result.job_name,
                    "candidate_count": len(candidates),
                },
            )
            return ProviderBackedPaperLoopResult(
                job_results=job_results,
                signal_results=[],
                must_stop_trading=True,
                reason_code=stop_result.reason_code,
            )

        signal_results = [self.pipeline.process_candidate(candidate, now=now) for candidate in candidates]
        self.audit.append(
            event_type="provider_paper_loop_completed",
            payload={
                "reason_code": "PROVIDER_JOBS_PASSED",
                "job_count": len(job_results),
                "candidate_count": len(candidates),
                "executed_signal_count": sum(result is not None for result in signal_results),
            },
        )
        return ProviderBackedPaperLoopResult(
            job_results=job_results,
            signal_results=signal_results,
            must_stop_trading=False,
            reason_code="PROVIDER_JOBS_PASSED",
        )
