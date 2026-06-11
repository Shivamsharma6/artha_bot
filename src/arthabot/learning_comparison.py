from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arthabot.common import Mode
from arthabot.learning import LearningEngine, ProposedChange
from arthabot.strategy_comparison import StrategyComparison


@dataclass(frozen=True)
class LearningComparisonSummary:
    best_strategy_version: str
    proposed_change: ProposedChange


class LearningComparisonReport:
    def __init__(self, *, comparison: StrategyComparison) -> None:
        self.comparison = comparison
        self.engine = LearningEngine()

    def summarize(self) -> LearningComparisonSummary:
        best = self.comparison.best
        weakest = min(self.comparison.rankings, key=lambda item: item.report.net_profit)
        proposed = self.engine.validate_change(
            ProposedChange(
                name=f"rerun backtest for {weakest.strategy_version}",
                target=f"backtest.rerun.{weakest.strategy_version}",
                value=Decimal("1"),
                mode=Mode.PAPER,
            )
        )
        return LearningComparisonSummary(
            best_strategy_version=best.strategy_version,
            proposed_change=proposed,
        )

