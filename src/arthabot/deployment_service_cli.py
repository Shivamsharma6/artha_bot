from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from kiteconnect import KiteTicker

from arthabot.audit_store import JsonlAuditStore
from arthabot.brokerage import BrokerageConfig
from arthabot.config import load_runtime_config
from arthabot.deployment_config import DeploymentJobConfig, load_deployment_config
from arthabot.deployment_command import build_paper_deployment_service
from arthabot.deployment_service import DeploymentSchedulerService
from arthabot.deployment_worker import DeploymentJobRegistry, DeploymentSchedulerWorker
from arthabot.learning_operations import LearningRerunWorkflow
from arthabot.learning_rerun_worker import LearningRerunWorker
from arthabot.instruments import InstrumentTokenStore
from arthabot.internal_state_store import InternalTradingStateStore
from arthabot.internal_state_store import InternalTradingStateTransitions
from arthabot.broker_order_updates import BrokerOrderUpdateProcessor
from arthabot.live_feed import ZerodhaLiveFeedSchedulerHandler
from arthabot.news_curation import load_news_curation_config
from arthabot.operational_handlers import (
    FileBackedLearningRerunHandler,
    HistoricalBacktestRerunRunner,
    StrategyCalibrationSchedulerHandler,
)
from arthabot.scheduler import ScheduledJob, TimeOfDaySchedule
from arthabot.secrets import SecretConfig, load_secret_export
from arthabot.reconciliation_operations import BrokerReconciliationOperation, BrokerReconciliationSchedulerHandler
from arthabot.http_clients import build_zerodha_http_client
from arthabot.strategy_calibration import CalibrationThresholds, StrategyCalibrationArtifactStore
from arthabot.strategy_calibration_cli import _historical_provider_from_json
from arthabot.strategy_calibration_config import load_strategy_calibration_config
from arthabot.strategy_calibration_operations import StrategyCalibrationRunService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ArthaBot PAPER deployment scheduler service.")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--audit-path", default="logs/deployment_scheduler.audit.jsonl")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-ticks", type=int)
    parser.add_argument("--allow-noop-registry", action="store_true")
    parser.add_argument("--instrument-store-path", default="data/instruments.json")
    parser.add_argument("--learning-queue-path")
    parser.add_argument("--historical-json-path")
    parser.add_argument("--learning-artifact-dir", default="reports/learning-reruns")
    parser.add_argument("--calibration-artifact-dir", default="reports/calibration")
    parser.add_argument("--secret-export-path")
    parser.add_argument("--internal-state-path", default="data/internal_trading_state.json")
    args = parser.parse_args(argv)

    max_ticks = 1 if args.once else args.max_ticks
    if max_ticks is None:
        return 2
    if not args.allow_noop_registry:
        if args.learning_queue_path is None or args.historical_json_path is None:
            return 2
        secrets = (
            load_secret_export(Path(args.secret_export_path))
            if args.secret_export_path is not None
            else SecretConfig.from_env(require_zerodha=True)
        )
        live_feed = _build_live_feed_handler(args, secrets)
        reconciliation = _build_reconciliation_handler(args, secrets)
        learning_rerun, strategy_calibration = _build_file_backed_handlers(args, secrets)
        service = build_paper_deployment_service(
            config_dir=args.config_dir,
            audit_path=args.audit_path,
            instrument_store_path=args.instrument_store_path,
            live_feed_supervision=live_feed,
            learning_rerun=learning_rerun,
            strategy_calibration=strategy_calibration,
            broker_reconciliation=reconciliation,
            secret_config=secrets,
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
        timezone_name=config.scheduler.timezone,
    )
    result = DeploymentSchedulerService(
        worker=worker,
        audit=audit,
        interval_seconds=args.interval_seconds,
        sleep=lambda _: None,
    ).run(max_ticks=max_ticks)
    return 1 if result.must_stop_trading else 0


def _build_file_backed_handlers(args, secrets):
    config = load_strategy_calibration_config(Path(args.config_dir) / "strategy.yaml")
    historical_provider = _historical_provider_from_json(Path(args.historical_json_path))
    brokerage = BrokerageConfig()
    learning_audit = JsonlAuditStore(Path(args.audit_path).with_name("learning_rerun.audit.jsonl"))
    runner = HistoricalBacktestRerunRunner(
        config=config,
        historical_provider=historical_provider,
        starting_capital=Decimal("5000"),
        brokerage_config=brokerage,
    )
    workflow = LearningRerunWorkflow(
        audit=learning_audit,
        artifact_dir=args.learning_artifact_dir,
        runner=runner,
    )
    learning_handler = FileBackedLearningRerunHandler(
        queue_path=args.learning_queue_path,
        worker=LearningRerunWorker(workflow=workflow, audit=learning_audit, max_attempts=2),
    )
    calibration_service = StrategyCalibrationRunService(
        config=config,
        historical_provider=historical_provider,
        starting_capital=Decimal("5000"),
        brokerage_config=brokerage,
        thresholds=CalibrationThresholds(
            min_data_years=Decimal("3"),
            min_walk_forward_windows=4,
            max_drawdown=Decimal("500"),
            min_expectancy=Decimal("0.01"),
        ),
        store=StrategyCalibrationArtifactStore(args.calibration_artifact_dir),
        audit=JsonlAuditStore(Path(args.audit_path).with_name("strategy_calibration.audit.jsonl")),
    )
    return learning_handler, StrategyCalibrationSchedulerHandler(service=calibration_service)


def _build_live_feed_handler(args, secrets):
    runtime = load_runtime_config(args.config_dir)
    curation = load_news_curation_config(args.config_dir)
    state_store = InternalTradingStateStore(args.internal_state_path)
    order_audit = JsonlAuditStore(Path(args.audit_path).with_name("broker_order_updates.audit.jsonl"))
    return ZerodhaLiveFeedSchedulerHandler(
        secret_config=secrets,
        instrument_store=InstrumentTokenStore(args.instrument_store_path),
        symbols=tuple(curation.company_terms),
        audit=JsonlAuditStore(Path(args.audit_path).with_name("live_feed.audit.jsonl")),
        ticker_factory=lambda api_key, access_token: KiteTicker(api_key, access_token),
        market_timezone="Asia/Kolkata",
        max_tick_age_seconds=runtime.risk.quote_max_age_seconds,
        order_update_handler=BrokerOrderUpdateProcessor(
            state_store=state_store,
            transitions=InternalTradingStateTransitions(store=state_store),
            audit=order_audit,
        ).process,
    )


def _build_reconciliation_handler(args, secrets):
    audit = JsonlAuditStore(Path(args.audit_path).with_name("broker_reconciliation.audit.jsonl"))
    return BrokerReconciliationSchedulerHandler(
        operation=BrokerReconciliationOperation(
            client=build_zerodha_http_client(secret_config=secrets),
            audit=audit,
        ),
        state_store=InternalTradingStateStore(args.internal_state_path),
        max_state_age_seconds=300,
    )


def _noop_registry() -> DeploymentJobRegistry:
    return DeploymentJobRegistry(
        factories={
            "instrument_refresh": _build_noop_job,
            "news_ingestion": _build_noop_job,
            "live_feed_supervision": _build_noop_job,
            "learning_rerun": _build_noop_job,
            "strategy_calibration": _build_noop_job,
            "broker_reconciliation": _build_noop_job,
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
