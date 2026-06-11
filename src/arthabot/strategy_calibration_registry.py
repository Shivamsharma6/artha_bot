from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from arthabot.strategy_calibration import StrategyCalibrationResult
from arthabot.strategy_calibration_runner import CalibrationRunRequest


class CalibrationRunner(Protocol):
    def run(self, request: CalibrationRunRequest) -> StrategyCalibrationResult:
        ...


@dataclass(frozen=True)
class StrategyCalibrationRegistry:
    runners: dict[str, CalibrationRunner]

    @property
    def available_versions(self) -> tuple[str, ...]:
        return tuple(sorted(self.runners))

    def run(self, strategy_version: str) -> StrategyCalibrationResult:
        runner = self.runners.get(strategy_version)
        if runner is None:
            raise KeyError(f"unknown strategy calibration version: {strategy_version}")
        return runner.run(CalibrationRunRequest(strategy_version=strategy_version))
