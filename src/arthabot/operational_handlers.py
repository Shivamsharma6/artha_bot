from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from arthabot.common import Mode
from arthabot.learning import ProposedChange
from arthabot.learning_operations import BacktestRerunRequest
from arthabot.learning_rerun_worker import LearningRerunWorker
from arthabot.strategy_calibration_config import (
    HistoricalProvider,
    StrategyCalibrationConfig,
    build_historical_calibration_inputs_from_config,
)
from arthabot.strategy_calibration_operations import StrategyCalibrationRunService


class HistoricalBacktestRerunRunner:
    def __init__(
        self,
        *,
        config: StrategyCalibrationConfig,
        historical_provider: HistoricalProvider,
        starting_capital,
        brokerage_config,
    ) -> None:
        self.config = config
        self.historical_provider = historical_provider
        self.starting_capital = starting_capital
        self.brokerage_config = brokerage_config

    def __call__(self, request: BacktestRerunRequest):
        configured = {version.version for version in self.config.versions}
        if request.strategy_version not in configured:
            raise KeyError(f"unknown configured rerun version: {request.strategy_version}")
        inputs = build_historical_calibration_inputs_from_config(
            config=self.config,
            historical_provider=self.historical_provider,
            starting_capital=self.starting_capital,
            brokerage_config=self.brokerage_config,
        )
        return inputs.reports_by_version[request.strategy_version]


class FileBackedLearningRerunHandler:
    def __init__(self, *, queue_path: str | Path, worker: LearningRerunWorker) -> None:
        self.queue_path = Path(queue_path)
        self.worker = worker

    def __call__(self, now: datetime | None = None) -> dict[str, Any]:
        changes = self._load_changes()
        result = self.worker.run(changes)
        if not result.must_stop_trading:
            self._clear_queue()
        return {
            "reason_code": result.reason_code,
            "completed": result.completed,
            "failed": result.failed,
            "must_stop_trading": result.must_stop_trading,
            "timestamp": now.isoformat() if now is not None else None,
        }

    def _load_changes(self) -> list[ProposedChange]:
        if not self.queue_path.exists():
            return []
        payload = json.loads(self.queue_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("learning rerun queue must be a JSON array")
        return [self._parse_change(entry) for entry in payload]

    @staticmethod
    def _parse_change(entry: object) -> ProposedChange:
        if not isinstance(entry, dict):
            raise ValueError("learning rerun queue entries must be JSON objects")
        required = {"name", "target", "value", "mode"}
        if not required.issubset(entry):
            raise ValueError("learning rerun queue entry is missing required fields")
        if entry["mode"] != Mode.PAPER.value:
            raise PermissionError("learning rerun queue only accepts PAPER mode")
        target = entry["target"]
        if not isinstance(target, str) or not target.startswith("backtest.rerun."):
            raise ValueError("learning rerun target must start with backtest.rerun")
        if not target.removeprefix("backtest.rerun."):
            raise ValueError("strategy version is required")
        name = entry["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("learning rerun name is required")
        return ProposedChange(name=name, target=target, value=entry["value"], mode=Mode.PAPER)

    def _clear_queue(self) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.queue_path.with_suffix(f"{self.queue_path.suffix}.tmp")
        temporary.write_text("[]", encoding="utf-8")
        temporary.replace(self.queue_path)


class StrategyCalibrationSchedulerHandler:
    def __init__(self, *, service: StrategyCalibrationRunService) -> None:
        self.service = service

    def __call__(self, now: datetime | None = None) -> dict[str, Any]:
        batch = self.service.run()
        versions = list(batch.results)
        return {
            "reason_code": "STRATEGY_CALIBRATION_COMPLETED",
            "strategy_versions": versions,
            "promotable_versions": [version for version in versions if batch.results[version].promotable],
            "rejected_versions": [version for version in versions if not batch.results[version].promotable],
            "must_stop_trading": False,
            "timestamp": now.isoformat() if now is not None else None,
        }
