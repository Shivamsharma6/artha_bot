from datetime import datetime, time, timezone

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.scheduler import ScheduledJob, SchedulerRunner, TimeOfDaySchedule


def test_scheduler_runner_executes_due_job_and_audits_result(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    calls = []
    runner = SchedulerRunner(audit=audit)
    job = ScheduledJob(
        name="instrument-refresh",
        schedule=TimeOfDaySchedule(run_at=time(8, 30)),
        action=lambda now: calls.append(now) or {"refreshed": True},
        critical=True,
    )
    now = datetime(2026, 1, 5, 8, 45, tzinfo=timezone.utc)

    result = runner.run(job, now=now)

    assert calls == [now]
    assert result.executed
    assert not result.must_stop_trading
    assert audit.read_all()[0].event_type == "scheduled_job_completed"


def test_scheduler_runner_does_not_repeat_job_on_later_tick_same_day(tmp_path):
    calls = []
    runner = SchedulerRunner(audit=JsonlAuditStore(tmp_path / "audit.jsonl"))
    job = ScheduledJob(
        name="live-feed",
        schedule=TimeOfDaySchedule(run_at=time(9, 0)),
        action=lambda now: calls.append(now),
        critical=True,
    )

    first = runner.run(job, now=datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))
    second = runner.run(job, now=datetime(2026, 1, 5, 9, 1, tzinfo=timezone.utc))

    assert first.executed is True
    assert second.executed is False
    assert calls == [datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)]


def test_scheduler_runner_skips_job_before_scheduled_time_and_audits(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    runner = SchedulerRunner(audit=audit)
    job = ScheduledJob(
        name="instrument-refresh",
        schedule=TimeOfDaySchedule(run_at=time(8, 30)),
        action=lambda now: pytest.fail("job should not run"),
        critical=True,
    )

    result = runner.run(job, now=datetime(2026, 1, 5, 8, 15, tzinfo=timezone.utc))

    assert not result.executed
    assert result.reason_code == "SCHEDULE_NOT_DUE"
    assert audit.read_all()[0].event_type == "scheduled_job_skipped"


def test_scheduler_runner_fails_closed_for_critical_job_error(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    runner = SchedulerRunner(audit=audit)

    def fail(now):
        raise RuntimeError("refresh failed")

    job = ScheduledJob(
        name="instrument-refresh",
        schedule=TimeOfDaySchedule(run_at=time(8, 30)),
        action=fail,
        critical=True,
    )

    result = runner.run(job, now=datetime(2026, 1, 5, 8, 45, tzinfo=timezone.utc))

    assert result.executed
    assert result.must_stop_trading
    assert result.reason_code == "SCHEDULED_JOB_FAILED"
    assert audit.read_all()[0].event_type == "scheduled_job_failed"


def test_time_of_day_schedule_runs_once_per_day():
    schedule = TimeOfDaySchedule(run_at=time(8, 30))

    assert schedule.is_due(now=datetime(2026, 1, 5, 8, 45, tzinfo=timezone.utc), last_run_at=None)
    assert not schedule.is_due(
        now=datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc),
        last_run_at=datetime(2026, 1, 5, 8, 45, tzinfo=timezone.utc),
    )
    assert schedule.is_due(
        now=datetime(2026, 1, 6, 8, 45, tzinfo=timezone.utc),
        last_run_at=datetime(2026, 1, 5, 8, 45, tzinfo=timezone.utc),
    )
