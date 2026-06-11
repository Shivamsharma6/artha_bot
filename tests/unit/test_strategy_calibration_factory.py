from datetime import datetime
from decimal import Decimal

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.backtest import BacktestReport, Candle, HistoricalDataset
from arthabot.strategy_calibration import (
    CalibrationThresholds,
    StrategyCalibrationArtifactStore,
)
from arthabot.strategy_calibration_factory import (
    CORE_STRATEGY_VERSIONS,
    StrategyCalibrationInputs,
    build_strategy_calibration_registry,
)


def candle(day: str) -> Candle:
    return Candle(
        timestamp=datetime.fromisoformat(f"{day}T09:15:00+00:00"),
        open=Decimal("100"),
        high=Decimal("104"),
        low=Decimal("99"),
        close=Decimal("103"),
        volume=1000,
    )


def dataset(symbol: str) -> HistoricalDataset:
    return HistoricalDataset(
        symbol=symbol,
        resolution="1m",
        candles=[candle("2023-01-01"), candle("2026-01-02")],
    )


def report(*, total_costs: Decimal = Decimal("20")) -> BacktestReport:
    return BacktestReport(
        net_profit=Decimal("120"),
        gross_profit=Decimal("140"),
        total_costs=total_costs,
        win_rate=Decimal("0.60"),
        number_of_trades=4,
        number_of_rejected_trades=3,
        max_drawdown=Decimal("5"),
    )


def inputs_for_all_versions(*, total_costs: Decimal = Decimal("20")) -> StrategyCalibrationInputs:
    return StrategyCalibrationInputs(
        datasets_by_version={version: [dataset("INFY")] for version in CORE_STRATEGY_VERSIONS},
        reports_by_version={version: report(total_costs=total_costs) for version in CORE_STRATEGY_VERSIONS},
        walk_forward_windows_by_version={version: 5 for version in CORE_STRATEGY_VERSIONS},
        out_of_sample_tested_by_version={version: True for version in CORE_STRATEGY_VERSIONS},
        survivorship_bias_checked_by_version={version: True for version in CORE_STRATEGY_VERSIONS},
    )


def test_build_strategy_calibration_registry_wires_core_versions_and_persists_results(tmp_path):
    store = StrategyCalibrationArtifactStore(tmp_path / "calibration")
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    registry = build_strategy_calibration_registry(
        inputs=inputs_for_all_versions(),
        thresholds=CalibrationThresholds(
            min_data_years=Decimal("3"),
            min_walk_forward_windows=4,
            max_drawdown=Decimal("10"),
            min_expectancy=Decimal("0.01"),
        ),
        store=store,
        audit=audit,
    )

    result = registry.run("momentum-v1")

    assert registry.available_versions == tuple(sorted(CORE_STRATEGY_VERSIONS))
    assert result.promotable
    assert store.read("momentum-v1").evidence.symbols == ("INFY",)
    assert audit.read_all()[-1].payload["strategy_version"] == "momentum-v1"


def test_build_strategy_calibration_registry_fails_closed_when_core_inputs_are_missing(tmp_path):
    inputs = inputs_for_all_versions()
    del inputs.reports_by_version["breakout-v1"]

    with pytest.raises(ValueError, match="missing calibration report for breakout-v1"):
        build_strategy_calibration_registry(
            inputs=inputs,
            thresholds=CalibrationThresholds(
                min_data_years=Decimal("3"),
                min_walk_forward_windows=4,
                max_drawdown=Decimal("10"),
                min_expectancy=Decimal("0.01"),
            ),
            store=StrategyCalibrationArtifactStore(tmp_path / "calibration"),
            audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
        )


def test_build_strategy_calibration_registry_keeps_cost_unaware_reports_non_promotable(tmp_path):
    registry = build_strategy_calibration_registry(
        inputs=inputs_for_all_versions(total_costs=Decimal("0")),
        thresholds=CalibrationThresholds(
            min_data_years=Decimal("3"),
            min_walk_forward_windows=4,
            max_drawdown=Decimal("10"),
            min_expectancy=Decimal("0.01"),
        ),
        store=StrategyCalibrationArtifactStore(tmp_path / "calibration"),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    )

    result = registry.run("volume-mover-v1")

    assert not result.promotable
    assert "COSTS_NOT_INCLUDED" in result.reason_codes
