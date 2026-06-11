from __future__ import annotations

import argparse
from datetime import datetime

from arthabot.audit_store import JsonlAuditStore
from arthabot.deployment_config import DeploymentJobConfig, load_deployment_config
from arthabot.deployment_command import build_paper_deployment_service
from arthabot.deployment_service import DeploymentSchedulerService
from arthabot.deployment_worker import DeploymentJobRegistry, DeploymentSchedulerWorker
from arthabot.scheduler import ScheduledJob, TimeOfDaySchedule


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ArthaBot PAPER deployment scheduler service.")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--audit-path", default="logs/deployment_scheduler.audit.jsonl")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-ticks", type=int)
    parser.add_argument("--allow-noop-registry", action="store_true")
    parser.add_argument("--instrument-store-path", default="data/instruments.json")
    args = parser.parse_args(argv)

    max_ticks = 1 if args.once else args.max_ticks
    if max_ticks is None:
        return 2
    if not args.allow_noop_registry:
        service = build_paper_deployment_service(
            config_dir=args.config_dir,
            audit_path=args.audit_path,
            instrument_store_path=args.instrument_store_path,
            live_feed_supervision=lambda now: {"configured": False, "job": "live_feed_supervision"},
            learning_rerun=lambda now: {"configured": False, "job": "learning_rerun"},
            strategy_calibration=lambda now: {"configured": False, "job": "strategy_calibration"},
            interval_seconds=args.interval_seconds,
        )
        result = service.run(max_ticks=max_ticks)
        return 1 if result.must_stop_trading else 0

    audit = JsonlAuditStore(args.audit_path)
    config = load_deployment_config(args.config_dir)
    worker = DeploymentSchedulerWorker(
        audit=audit,
        registry=_noop_registry(),
        job_configs=config.scheduler.jobs,
    )
    result = DeploymentSchedulerService(
        worker=worker,
        audit=audit,
        interval_seconds=args.interval_seconds,
        sleep=lambda _: None,
    ).run(max_ticks=max_ticks)
    return 1 if result.must_stop_trading else 0


def _noop_registry() -> DeploymentJobRegistry:
    return DeploymentJobRegistry(
        factories={
            "instrument_refresh": _build_noop_job,
            "news_ingestion": _build_noop_job,
            "live_feed_supervision": _build_noop_job,
            "learning_rerun": _build_noop_job,
            "strategy_calibration": _build_noop_job,
        }
    )


def _build_noop_job(config: DeploymentJobConfig) -> ScheduledJob:
    return ScheduledJob(
        name=config.name,
        schedule=TimeOfDaySchedule.from_string(config.run_at),
        action=lambda now: {
            "job_type": config.type,
            "noop": True,
            "timestamp": datetime.isoformat(now),
        },
        critical=config.critical,
    )


if __name__ == "__main__":
    raise SystemExit(main())
