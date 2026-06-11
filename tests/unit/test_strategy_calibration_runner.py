from datetime import date
from decimal import Decimal

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.backtest import BacktestReport
from arthabot.strategy_calibration import (
    CalibrationThresholds,
    StrategyCalibrationArtifactStore,
    StrategyCalibrationGate,
)
from arthabot.strategy_calibration_runner import (
    CalibrationBacktestSummary,
    CalibrationRunRequest,
    HistoricalCoverage,
    StrategyCalibrationJobRunner,
    calibration_summary_from_backtest_report,
)


def test_strategy_calibration_job_runner_persists_and_audits_promotable_evidence(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    store = StrategyCalibrationArtifactStore(tmp_path / "calibration")
    seen_requests: list[CalibrationRunRequest] = []

    def coverage_provider(request: CalibrationRunRequest) -> HistoricalCoverage:
        seen_requests.append(request)
        return HistoricalCoverage(
            data_start=date(2023, 1, 1),
            data_end=date(2026, 1, 2),
            data_resolution="1m",
            symbols=("INFY", "TCS"),
        )

    def backtest_runner(request: CalibrationRunRequest) -> CalibrationBacktestSummary:
        return CalibrationBacktestSummary(
            brokerage_and_slippage_included=True,
            walk_forward_windows=6,
            out_of_sample_tested=True,
            survivorship_bias_checked=True,
            net_profit=Decimal("750"),
            expectancy=Decimal("0.18"),
            max_drawdown=Decimal("6"),
            rejected_trades=11,
        )

    result = StrategyCalibrationJobRunner(
        coverage_provider=coverage_provider,
        backtest_runner=backtest_runner,
        gate=StrategyCalibrationGate(
            thresholds=CalibrationThresholds(
                min_data_years=Decimal("3"),
                min_walk_forward_windows=4,
                max_drawdown=Decimal("10"),
                min_expectancy=Decimal("0.01"),
            )
        ),
        store=store,
        audit=audit,
    ).run(CalibrationRunRequest(strategy_version="momentum-v1"))

    assert seen_requests == [CalibrationRunRequest(strategy_version="momentum-v1")]
    assert result.promotable
    assert store.read("momentum-v1").result.promotable
    assert audit.read_all()[-1].event_type == "strategy_calibration_completed"
    assert audit.read_all()[-1].payload["strategy_version"] == "momentum-v1"


def test_strategy_calibration_job_runner_rejects_summary_without_costs(tmp_path):
    runner = StrategyCalibrationJobRunner(
        coverage_provider=lambda request: HistoricalCoverage(
            data_start=date(2023, 1, 1),
            data_end=date(2026, 1, 2),
            data_resolution="1m",
            symbols=("INFY",),
        ),
        backtest_runner=lambda request: CalibrationBacktestSummary(
            brokerage_and_slippage_included=False,
            walk_forward_windows=6,
            out_of_sample_tested=True,
            survivorship_bias_checked=True,
            net_profit=Decimal("750"),
            expectancy=Decimal("0.18"),
            max_drawdown=Decimal("6"),
            rejected_trades=11,
        ),
        gate=StrategyCalibrationGate(
            thresholds=CalibrationThresholds(
                min_data_years=Decimal("3"),
                min_walk_forward_windows=4,
                max_drawdown=Decimal("10"),
                min_expectancy=Decimal("0.01"),
            )
        ),
        store=StrategyCalibrationArtifactStore(tmp_path / "calibration"),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    )

    result = runner.run(CalibrationRunRequest(strategy_version="breakout-v1"))

    assert not result.promotable
    assert "COSTS_NOT_INCLUDED" in result.reason_codes
    assert runner.audit.read_all()[-1].payload["promotable"] is False


def test_calibration_summary_from_backtest_report_derives_expectancy_and_preserves_rejections():
    summary = calibration_summary_from_backtest_report(
        BacktestReport(
            net_profit=Decimal("90"),
            gross_profit=Decimal("120"),
            total_costs=Decimal("30"),
            win_rate=Decimal("0.6"),
            number_of_trades=3,
            number_of_rejected_trades=2,
            max_drawdown=Decimal("12"),
        ),
        walk_forward_windows=5,
        out_of_sample_tested=True,
        survivorship_bias_checked=True,
    )

    assert summary.brokerage_and_slippage_included
    assert summary.expectancy == Decimal("30")
    assert summary.rejected_trades == 2
    assert summary.max_drawdown == Decimal("12")


def test_calibration_summary_from_backtest_report_handles_zero_trade_report():
    summary = calibration_summary_from_backtest_report(
        BacktestReport(
            net_profit=Decimal("0"),
            gross_profit=Decimal("0"),
            total_costs=Decimal("0"),
            win_rate=Decimal("0"),
            number_of_trades=0,
            number_of_rejected_trades=1,
            max_drawdown=Decimal("0"),
        ),
        walk_forward_windows=0,
        out_of_sample_tested=False,
        survivorship_bias_checked=False,
    )

    assert not summary.brokerage_and_slippage_included
    assert summary.expectancy == Decimal("0")
    assert summary.rejected_trades == 1
