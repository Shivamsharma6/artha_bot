from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from arthabot.audit_store import JsonlAuditStore
from arthabot.deployment_service import DeploymentSchedulerService
from arthabot.deployment_worker import DeploymentSchedulerTickResult
from arthabot.operational_audit_coverage import OperationalAuditCoverageChecker


@dataclass
class FakeWorker:
    results: list[DeploymentSchedulerTickResult]
    seen_times: list[datetime]

    def tick(self, *, now: datetime) -> DeploymentSchedulerTickResult:
        self.seen_times.append(now)
        return self.results.pop(0)


def test_deployment_scheduler_service_runs_bounded_ticks_with_sleep(tmp_path):
    now = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
    clock_values = [now, now + timedelta(seconds=30)]
    sleep_calls: list[float] = []
    worker = FakeWorker(
        results=[
            DeploymentSchedulerTickResult([], must_stop_trading=False, reason_code="OK"),
            DeploymentSchedulerTickResult([], must_stop_trading=False, reason_code="OK"),
        ],
        seen_times=[],
    )

    result = DeploymentSchedulerService(
        worker=worker,
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
        interval_seconds=30,
        clock=lambda: clock_values.pop(0),
        sleep=lambda seconds: sleep_calls.append(seconds),
    ).run(max_ticks=2)

    assert result.tick_count == 2
    assert not result.must_stop_trading
    assert worker.seen_times == [now, now + timedelta(seconds=30)]
    assert sleep_calls == [30]


def test_deployment_scheduler_service_stops_on_worker_stop_trading(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    worker = FakeWorker(
        results=[
            DeploymentSchedulerTickResult([], must_stop_trading=True, reason_code="SCHEDULED_JOB_FAILED"),
            DeploymentSchedulerTickResult([], must_stop_trading=False, reason_code="UNREACHED"),
        ],
        seen_times=[],
    )

    result = DeploymentSchedulerService(
        worker=worker,
        audit=audit,
        interval_seconds=30,
        clock=lambda: datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc),
        sleep=lambda seconds: None,
    ).run(max_ticks=5)

    assert result.tick_count == 1
    assert result.must_stop_trading
    assert result.reason_code == "SCHEDULED_JOB_FAILED"
    assert audit.read_all()[-1].event_type == "deployment_scheduler_service_stopped"


def test_deployment_scheduler_service_fails_closed_when_audit_coverage_is_missing(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    worker = FakeWorker(
        results=[DeploymentSchedulerTickResult([], must_stop_trading=False, reason_code="OK")],
        seen_times=[],
    )

    result = DeploymentSchedulerService(
        worker=worker,
        audit=audit,
        interval_seconds=30,
        clock=lambda: datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc),
        sleep=lambda seconds: None,
        audit_coverage_checker=OperationalAuditCoverageChecker(
            required_events=("deployment_scheduler_service_completed", "missing_event"),
        ),
    ).run(max_ticks=1)

    assert result.must_stop_trading
    assert result.reason_code == "AUDIT_COVERAGE_MISSING_EVENTS"
    assert audit.read_all()[-1].event_type == "deployment_scheduler_service_stopped"
    assert audit.read_all()[-1].payload["missing_event_types"] == ["missing_event"]


def test_deployment_scheduler_service_passes_when_audit_coverage_is_complete(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    worker = FakeWorker(
        results=[DeploymentSchedulerTickResult([], must_stop_trading=False, reason_code="OK")],
        seen_times=[],
    )

    result = DeploymentSchedulerService(
        worker=worker,
        audit=audit,
        interval_seconds=30,
        clock=lambda: datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc),
        sleep=lambda seconds: None,
        audit_coverage_checker=OperationalAuditCoverageChecker(
            required_events=("deployment_scheduler_service_completed",),
        ),
    ).run(max_ticks=1)

    assert not result.must_stop_trading
    assert result.reason_code == "MAX_TICKS_REACHED"
