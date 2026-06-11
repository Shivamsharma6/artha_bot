from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from arthabot.common import Mode
from arthabot.learning import LearningEngine, ProposedChange


@dataclass(frozen=True)
class StrategyObservation:
    window: str
    expectancy: Decimal
    max_drawdown: Decimal


@dataclass(frozen=True)
class LearningSummary:
    strategy_version: str
    degraded_windows: tuple[str, ...]
    proposed_change: ProposedChange


class LearningReport:
    def __init__(self, *, strategy_version: str, observations: list[StrategyObservation]) -> None:
        self.strategy_version = strategy_version
        self.observations = observations
        self.engine = LearningEngine()

    def summarize(self) -> LearningSummary:
        degraded = tuple(observation.window for observation in self.observations if observation.expectancy < 0)
        target_window = degraded[0] if degraded else "none"
        proposed = self.propose_change(
            name=f"reduce {target_window} window weight",
            target=f"strategy.window_weight.{target_window}",
            value=Decimal("0.5"),
            mode=Mode.PAPER,
        )
        return LearningSummary(
            strategy_version=self.strategy_version,
            degraded_windows=degraded,
            proposed_change=proposed,
        )

    def propose_change(self, *, name: str, target: str, value: Any, mode: Mode) -> ProposedChange:
        return self.engine.validate_change(ProposedChange(name=name, target=target, value=value, mode=mode))

