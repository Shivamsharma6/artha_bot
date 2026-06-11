from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.backtest import BacktestReport
from arthabot.strategy_calibration import (
    StrategyCalibrationArtifactStore,
    StrategyCalibrationEvidence,
    StrategyCalibrationGate,
    StrategyCalibrationResult,
)


@dataclass(frozen=True)
class CalibrationRunRequest:
    strategy_version: str


@dataclass(frozen=True)
class HistoricalCoverage:
    data_start: date
    data_end: date
    data_resolution: str
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class CalibrationBacktestSummary:
    brokerage_and_slippage_included: bool
    walk_forward_windows: int
    out_of_sample_tested: bool
    survivorship_bias_checked: bool
    net_profit: Decimal
    expectancy: Decimal
    max_drawdown: Decimal
    rejected_trades: int


class StrategyCalibrationJobRunner:
    def __init__(
        self,
        *,
        coverage_provider: Callable[[CalibrationRunRequest], HistoricalCoverage],
        backtest_runner: Callable[[CalibrationRunRequest], CalibrationBacktestSummary],
        gate: StrategyCalibrationGate,
        store: StrategyCalibrationArtifactStore,
        audit: JsonlAuditStore,
    ) -> None:
        self.coverage_provider = coverage_provider
        self.backtest_runner = backtest_runner
        self.gate = gate
        self.store = store
        self.audit = audit

    def run(self, request: CalibrationRunRequest) -> StrategyCalibrationResult:
        coverage = self.coverage_provider(request)
        summary = self.backtest_runner(request)
        evidence = StrategyCalibrationEvidence(
            strategy_version=request.strategy_version,
            data_start=coverage.data_start,
            data_end=coverage.data_end,
            data_resolution=coverage.data_resolution,
            symbols=coverage.symbols,
            brokerage_and_slippage_included=summary.brokerage_and_slippage_included,
            walk_forward_windows=summary.walk_forward_windows,
            out_of_sample_tested=summary.out_of_sample_tested,
            survivorship_bias_checked=summary.survivorship_bias_checked,
            net_profit=summary.net_profit,
            expectancy=summary.expectancy,
            max_drawdown=summary.max_drawdown,
            rejected_trades=summary.rejected_trades,
        )
        result = self.gate.evaluate(evidence)
        artifact_path = self.store.write(evidence=evidence, result=result)
        self.audit.append(
            event_type="strategy_calibration_completed",
            payload={
                "strategy_version": result.strategy_version,
                "promotable": result.promotable,
                "reason_codes": list(result.reason_codes),
                "artifact_path": str(artifact_path),
            },
        )
        return result


def calibration_summary_from_backtest_report(
    report: BacktestReport,
    *,
    walk_forward_windows: int,
    out_of_sample_tested: bool,
    survivorship_bias_checked: bool,
) -> CalibrationBacktestSummary:
    expectancy = (
        report.net_profit / Decimal(report.number_of_trades)
        if report.number_of_trades > 0
        else Decimal("0")
    )
    return CalibrationBacktestSummary(
        brokerage_and_slippage_included=report.total_costs > 0,
        walk_forward_windows=walk_forward_windows,
        out_of_sample_tested=out_of_sample_tested,
        survivorship_bias_checked=survivorship_bias_checked,
        net_profit=report.net_profit,
        expectancy=expectancy,
        max_drawdown=report.max_drawdown,
        rejected_trades=report.number_of_rejected_trades,
    )
