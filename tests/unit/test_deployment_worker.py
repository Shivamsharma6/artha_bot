from datetime import datetime, timezone

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.deployment_config import DeploymentJobConfig, load_deployment_config
from arthabot.deployment_worker import DeploymentJobRegistry, DeploymentSchedulerWorker
from arthabot.scheduler import ScheduledJob, TimeOfDaySchedule


def test_deployment_worker_runs_enabled_configured_jobs_and_skips_disabled_jobs(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    calls: list[str] = []
    registry = DeploymentJobRegistry(
        factories={
            "news_ingestion": lambda config: ScheduledJob(
                name=config.name,
                schedule=TimeOfDaySchedule.from_string(config.run_at),
                action=lambda now: calls.append(config.name),
                critical=config.critical,
            )
        }
    )
    worker = DeploymentSchedulerWorker(
        audit=audit,
        registry=registry,
        job_configs=[
            DeploymentJobConfig(
                name="news-ingest",
                type="news_ingestion",
                enabled=True,
                critical=False,
                run_at="08:45",
            ),
            DeploymentJobConfig(
                name="disabled-news",
                type="news_ingestion",
                enabled=False,
                critical=False,
                run_at="08:45",
            ),
        ],
    )

    result = worker.tick(now=datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))

    assert calls == ["news-ingest"]
    assert not result.must_stop_trading
    assert [job_result.job_name for job_result in result.job_results] == ["news-ingest"]
    assert audit.read_all()[-1].event_type == "deployment_scheduler_tick_completed"


def test_deployment_worker_fails_closed_when_critical_job_fails(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    registry = DeploymentJobRegistry(
        factories={
            "instrument_refresh": lambda config: ScheduledJob(
                name=config.name,
                schedule=TimeOfDaySchedule.from_string(config.run_at),
                action=lambda now: (_ for _ in ()).throw(RuntimeError("provider down")),
                critical=config.critical,
            )
        }
    )
    worker = DeploymentSchedulerWorker(
        audit=audit,
        registry=registry,
        job_configs=[
            DeploymentJobConfig(
                name="instrument-refresh",
                type="instrument_refresh",
                enabled=True,
                critical=True,
                run_at="08:30",
            )
        ],
    )

    result = worker.tick(now=datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))

    assert result.must_stop_trading
    assert result.reason_code == "SCHEDULED_JOB_FAILED"
    assert audit.read_all()[-1].event_type == "deployment_scheduler_tick_stopped"


def test_deployment_worker_rejects_unknown_enabled_job_type(tmp_path):
    with pytest.raises(ValueError, match="unknown deployment job type"):
        DeploymentSchedulerWorker(
            audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
            registry=DeploymentJobRegistry(factories={}),
            job_configs=[
                DeploymentJobConfig(
                    name="mystery-job",
                    type="unknown",
                    enabled=True,
                    critical=False,
                    run_at="09:00",
                )
            ],
        )


def test_deployment_worker_builds_all_enabled_jobs_from_default_deployment_config(tmp_path):
    config = load_deployment_config("config")
    built_job_names: list[str] = []
    registry = DeploymentJobRegistry(
        factories={
            job_type: lambda job_config: ScheduledJob(
                name=job_config.name,
                schedule=TimeOfDaySchedule.from_string(job_config.run_at),
                action=lambda now, name=job_config.name: built_job_names.append(name),
                critical=job_config.critical,
            )
            for job_type in {
                "instrument_refresh",
                "news_ingestion",
                "live_feed_supervision",
                "learning_rerun",
                "strategy_calibration",
            }
        }
    )
    worker = DeploymentSchedulerWorker(
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
        registry=registry,
        job_configs=config.scheduler.jobs,
    )

    result = worker.tick(now=datetime(2026, 1, 5, 16, 30, tzinfo=timezone.utc))

    assert [job_result.job_name for job_result in result.job_results] == [
        "instrument-refresh-nse",
        "news-ingest-core-watchlist",
        "live-feed-supervision",
        "operational-learning-rerun",
        "strategy-calibration-rerun",
    ]
    assert built_job_names == [
        "instrument-refresh-nse",
        "news-ingest-core-watchlist",
        "live-feed-supervision",
        "operational-learning-rerun",
        "strategy-calibration-rerun",
    ]
