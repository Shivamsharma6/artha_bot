from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arthabot.backtest import BacktestReport


@dataclass(frozen=True)
class StrategyResult:
    strategy_version: str
    report: BacktestReport


@dataclass(frozen=True)
class RankedStrategy:
    strategy_version: str
    report: BacktestReport
    promotable: bool
    reason_code: str


@dataclass(frozen=True)
class StrategyComparison:
    rankings: tuple[RankedStrategy, ...]

    @property
    def best(self) -> RankedStrategy:
        return self.rankings[0]


class StrategyComparisonHarness:
    def __init__(self, *, max_drawdown_limit: Decimal) -> None:
        self.max_drawdown_limit = max_drawdown_limit

    def compare(self, results: list[StrategyResult]) -> StrategyComparison:
        if not results:
            raise ValueError("at least one strategy result is required")
        ranked = [
            RankedStrategy(
                strategy_version=result.strategy_version,
                report=result.report,
                promotable=result.report.max_drawdown <= self.max_drawdown_limit and result.report.net_profit > 0,
                reason_code=self._reason_code(result.report),
            )
            for result in sorted(
                results,
                key=lambda item: (item.report.net_profit, -item.report.max_drawdown),
                reverse=True,
            )
        ]
        return StrategyComparison(rankings=tuple(ranked))

    def _reason_code(self, report: BacktestReport) -> str:
        if report.max_drawdown > self.max_drawdown_limit:
            return "DRAWDOWN_LIMIT_BREACHED"
        if report.net_profit <= 0:
            return "NON_POSITIVE_NET_PROFIT"
        return "PROMOTABLE"

