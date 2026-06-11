from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.brokerage import BrokerageConfig
from arthabot.strategy_calibration import (
    CalibrationThresholds,
    StrategyCalibrationArtifactStore,
    StrategyCalibrationResult,
)
from arthabot.strategy_calibration_config import (
    HistoricalProvider,
    StrategyCalibrationConfig,
    build_historical_calibration_inputs_from_config,
)
from arthabot.strategy_calibration_factory import build_strategy_calibration_registry


@dataclass(frozen=True)
class StrategyCalibrationBatchResult:
    results: dict[str, StrategyCalibrationResult]

    @property
    def strategy_versions(self) -> tuple[str, ...]:
        return tuple(self.results)


class StrategyCalibrationRunService:
    def __init__(
        self,
        *,
        config: StrategyCalibrationConfig,
        historical_provider: HistoricalProvider,
        starting_capital: Decimal,
        brokerage_config: BrokerageConfig,
        thresholds: CalibrationThresholds,
        store: StrategyCalibrationArtifactStore,
        audit: JsonlAuditStore,
    ) -> None:
        self.config = config
        self.historical_provider = historical_provider
        self.starting_capital = starting_capital
        self.brokerage_config = brokerage_config
        self.thresholds = thresholds
        self.store = store
        self.audit = audit

    def run(self, *, strategy_versions: tuple[str, ...] | None = None) -> StrategyCalibrationBatchResult:
        configured_versions = tuple(version.version for version in self.config.versions)
        selected_versions = strategy_versions or configured_versions
        unknown_versions = tuple(version for version in selected_versions if version not in configured_versions)
        if unknown_versions:
            raise KeyError(f"unknown configured calibration version: {unknown_versions[0]}")

        inputs = build_historical_calibration_inputs_from_config(
            config=self.config,
            historical_provider=self.historical_provider,
            starting_capital=self.starting_capital,
            brokerage_config=self.brokerage_config,
        )
        registry = build_strategy_calibration_registry(
            inputs=inputs,
            thresholds=self.thresholds,
            store=self.store,
            audit=self.audit,
            strategy_versions=selected_versions,
        )
        results = {version: registry.run(version) for version in selected_versions}
        self.audit.append(
            event_type="strategy_calibration_batch_completed",
            payload={
                "strategy_versions": list(results),
                "promotable_versions": [
                    version for version, result in results.items() if result.promotable
                ],
                "rejected_versions": [
                    version for version, result in results.items() if not result.promotable
                ],
            },
        )
        return StrategyCalibrationBatchResult(results=results)
