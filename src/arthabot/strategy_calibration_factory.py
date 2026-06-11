from __future__ import annotations

from dataclasses import dataclass

from arthabot.audit_store import JsonlAuditStore
from arthabot.backtest import BacktestReport, HistoricalDataset
from arthabot.strategy_calibration import (
    CalibrationThresholds,
    StrategyCalibrationArtifactStore,
    StrategyCalibrationGate,
)
from arthabot.strategy_calibration_coverage import historical_coverage_from_datasets
from arthabot.strategy_calibration_registry import StrategyCalibrationRegistry
from arthabot.strategy_calibration_runner import (
    StrategyCalibrationJobRunner,
    calibration_summary_from_backtest_report,
)


CORE_STRATEGY_VERSIONS = (
    "momentum-v1",
    "breakout-v1",
    "reversal-v1",
    "volume-mover-v1",
)


@dataclass(frozen=True)
class StrategyCalibrationInputs:
    datasets_by_version: dict[str, list[HistoricalDataset]]
    reports_by_version: dict[str, BacktestReport]
    walk_forward_windows_by_version: dict[str, int]
    out_of_sample_tested_by_version: dict[str, bool]
    survivorship_bias_checked_by_version: dict[str, bool]


def build_strategy_calibration_registry(
    *,
    inputs: StrategyCalibrationInputs,
    thresholds: CalibrationThresholds,
    store: StrategyCalibrationArtifactStore,
    audit: JsonlAuditStore,
    strategy_versions: tuple[str, ...] = CORE_STRATEGY_VERSIONS,
) -> StrategyCalibrationRegistry:
    runners = {}
    gate = StrategyCalibrationGate(thresholds=thresholds)
    for version in strategy_versions:
        _validate_inputs(inputs, version)
        runners[version] = StrategyCalibrationJobRunner(
            coverage_provider=lambda request, selected_version=version: historical_coverage_from_datasets(
                inputs.datasets_by_version[selected_version]
            ),
            backtest_runner=lambda request, selected_version=version: calibration_summary_from_backtest_report(
                inputs.reports_by_version[selected_version],
                walk_forward_windows=inputs.walk_forward_windows_by_version[selected_version],
                out_of_sample_tested=inputs.out_of_sample_tested_by_version[selected_version],
                survivorship_bias_checked=inputs.survivorship_bias_checked_by_version[selected_version],
            ),
            gate=gate,
            store=store,
            audit=audit,
        )
    return StrategyCalibrationRegistry(runners=runners)


def _validate_inputs(inputs: StrategyCalibrationInputs, version: str) -> None:
    if version not in inputs.datasets_by_version:
        raise ValueError(f"missing calibration datasets for {version}")
    if version not in inputs.reports_by_version:
        raise ValueError(f"missing calibration report for {version}")
    if version not in inputs.walk_forward_windows_by_version:
        raise ValueError(f"missing walk-forward window count for {version}")
    if version not in inputs.out_of_sample_tested_by_version:
        raise ValueError(f"missing out-of-sample validation flag for {version}")
    if version not in inputs.survivorship_bias_checked_by_version:
        raise ValueError(f"missing survivorship-bias validation flag for {version}")
