from datetime import date
from decimal import Decimal

from arthabot.strategy_calibration import (
    CalibrationThresholds,
    StrategyCalibrationArtifactStore,
    StrategyCalibrationEvidence,
    StrategyCalibrationGate,
)


def test_strategy_calibration_gate_accepts_real_data_validated_strategy():
    evidence = StrategyCalibrationEvidence(
        strategy_version="momentum-v1",
        data_start=date(2023, 1, 1),
        data_end=date(2026, 1, 2),
        data_resolution="1m",
        symbols=("INFY", "RELIANCE"),
        brokerage_and_slippage_included=True,
        walk_forward_windows=8,
        out_of_sample_tested=True,
        survivorship_bias_checked=True,
        net_profit=Decimal("1200"),
        expectancy=Decimal("0.35"),
        max_drawdown=Decimal("8"),
        rejected_trades=14,
    )

    result = StrategyCalibrationGate(
        thresholds=CalibrationThresholds(
            min_data_years=Decimal("3"),
            min_walk_forward_windows=4,
            max_drawdown=Decimal("10"),
            min_expectancy=Decimal("0.01"),
        )
    ).evaluate(evidence)

    assert result.promotable
    assert result.reason_codes == ("CALIBRATION_PASSED",)


def test_strategy_calibration_gate_rejects_undervalidated_strategy():
    evidence = StrategyCalibrationEvidence(
        strategy_version="breakout-v1",
        data_start=date(2025, 1, 1),
        data_end=date(2026, 1, 1),
        data_resolution="unknown",
        symbols=("INFY",),
        brokerage_and_slippage_included=False,
        walk_forward_windows=0,
        out_of_sample_tested=False,
        survivorship_bias_checked=False,
        net_profit=Decimal("-10"),
        expectancy=Decimal("-0.05"),
        max_drawdown=Decimal("15"),
        rejected_trades=0,
    )

    result = StrategyCalibrationGate(
        thresholds=CalibrationThresholds(
            min_data_years=Decimal("3"),
            min_walk_forward_windows=4,
            max_drawdown=Decimal("10"),
            min_expectancy=Decimal("0.01"),
        )
    ).evaluate(evidence)

    assert not result.promotable
    assert result.reason_codes == (
        "INSUFFICIENT_DATA_DEPTH",
        "UNKNOWN_DATA_RESOLUTION",
        "COSTS_NOT_INCLUDED",
        "INSUFFICIENT_WALK_FORWARD_WINDOWS",
        "OUT_OF_SAMPLE_MISSING",
        "SURVIVORSHIP_CHECK_MISSING",
        "NON_POSITIVE_NET_PROFIT",
        "EXPECTANCY_TOO_LOW",
        "DRAWDOWN_TOO_HIGH",
        "NO_REJECTED_TRADE_LOGGING_EVIDENCE",
    )


def test_strategy_calibration_artifact_store_persists_evidence_and_result(tmp_path):
    evidence = StrategyCalibrationEvidence(
        strategy_version="volume-mover-v1",
        data_start=date(2023, 1, 1),
        data_end=date(2026, 1, 2),
        data_resolution="1m",
        symbols=("INFY", "TCS"),
        brokerage_and_slippage_included=True,
        walk_forward_windows=5,
        out_of_sample_tested=True,
        survivorship_bias_checked=True,
        net_profit=Decimal("900"),
        expectancy=Decimal("0.22"),
        max_drawdown=Decimal("7"),
        rejected_trades=9,
    )
    gate = StrategyCalibrationGate(
        thresholds=CalibrationThresholds(
            min_data_years=Decimal("3"),
            min_walk_forward_windows=4,
            max_drawdown=Decimal("10"),
            min_expectancy=Decimal("0.01"),
        )
    )
    store = StrategyCalibrationArtifactStore(tmp_path / "calibration")

    artifact_path = store.write(evidence=evidence, result=gate.evaluate(evidence))
    loaded = store.read("volume-mover-v1")

    assert artifact_path.exists()
    assert loaded.evidence == evidence
    assert loaded.result.promotable
    assert loaded.result.reason_codes == ("CALIBRATION_PASSED",)


def test_strategy_calibration_evidence_rejects_invalid_date_range():
    try:
        StrategyCalibrationEvidence(
            strategy_version="bad-v1",
            data_start=date(2026, 1, 2),
            data_end=date(2026, 1, 1),
            data_resolution="1m",
            symbols=("INFY",),
            brokerage_and_slippage_included=True,
            walk_forward_windows=1,
            out_of_sample_tested=True,
            survivorship_bias_checked=True,
            net_profit=Decimal("1"),
            expectancy=Decimal("0.1"),
            max_drawdown=Decimal("1"),
            rejected_trades=1,
        )
    except ValueError as exc:
        assert "data_end" in str(exc)
    else:
        raise AssertionError("invalid calibration date range was accepted")
