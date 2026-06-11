from __future__ import annotations

import argparse
from collections.abc import Callable
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

from arthabot.audit_store import JsonlAuditStore
from arthabot.brokerage import BrokerageConfig
from arthabot.data_providers import HistoricalDataProvider
from arthabot.strategy_calibration import CalibrationThresholds, StrategyCalibrationArtifactStore
from arthabot.strategy_calibration_config import load_strategy_calibration_config
from arthabot.strategy_calibration_operations import StrategyCalibrationRunService


ServiceFactory = Callable[[argparse.Namespace], Any]


def main(argv: list[str] | None = None, *, service_factory: ServiceFactory | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ArthaBot historical strategy calibration backtests.")
    parser.add_argument("--config-path", default="config/strategy.yaml")
    parser.add_argument("--audit-path", default="logs/strategy_calibration.audit.jsonl")
    parser.add_argument("--artifact-dir", default="reports/calibration")
    parser.add_argument("--historical-json-path")
    parser.add_argument("--strategy-version", action="append", default=[])
    args = parser.parse_args(argv)

    if service_factory is None:
        if args.historical_json_path is None:
            return 2
        service_factory = _build_service_from_args

    service = service_factory(args)
    versions = tuple(args.strategy_version) if args.strategy_version else None
    service.run(strategy_versions=versions)
    return 0


def _build_service_from_args(args: argparse.Namespace) -> StrategyCalibrationRunService:
    return StrategyCalibrationRunService(
        config=load_strategy_calibration_config(args.config_path),
        historical_provider=_historical_provider_from_json(Path(args.historical_json_path)),
        starting_capital=Decimal("5000"),
        brokerage_config=BrokerageConfig(),
        thresholds=CalibrationThresholds(
            min_data_years=Decimal("3"),
            min_walk_forward_windows=4,
            max_drawdown=Decimal("500"),
            min_expectancy=Decimal("0.01"),
        ),
        store=StrategyCalibrationArtifactStore(args.artifact_dir),
        audit=JsonlAuditStore(args.audit_path),
    )


def _historical_provider_from_json(path: Path) -> HistoricalDataProvider:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("historical JSON payload must be a symbol-to-candles mapping")

    def fetch_rows(request):
        rows = payload.get(request.symbol)
        if rows is None:
            raise KeyError(f"missing historical rows for {request.symbol}")
        return list(rows)

    return HistoricalDataProvider(client=fetch_rows)
