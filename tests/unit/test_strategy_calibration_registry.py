from decimal import Decimal

import pytest

from arthabot.strategy_calibration import StrategyCalibrationResult
from arthabot.strategy_calibration_registry import StrategyCalibrationRegistry
from arthabot.strategy_calibration_runner import CalibrationRunRequest


class FakeCalibrationRunner:
    def __init__(self) -> None:
        self.requests: list[CalibrationRunRequest] = []

    def run(self, request: CalibrationRunRequest) -> StrategyCalibrationResult:
        self.requests.append(request)
        return StrategyCalibrationResult(
            strategy_version=request.strategy_version,
            promotable=True,
            reason_codes=("CALIBRATION_PASSED",),
        )


def test_strategy_calibration_registry_runs_named_strategy_version():
    runner = FakeCalibrationRunner()
    registry = StrategyCalibrationRegistry(
        runners={
            "momentum-v1": runner,
            "breakout-v1": FakeCalibrationRunner(),
        }
    )

    result = registry.run("momentum-v1")

    assert result.promotable
    assert runner.requests == [CalibrationRunRequest(strategy_version="momentum-v1")]


def test_strategy_calibration_registry_rejects_unknown_strategy_version():
    registry = StrategyCalibrationRegistry(runners={})

    with pytest.raises(KeyError, match="unknown strategy calibration version"):
        registry.run("unknown-v1")


def test_strategy_calibration_registry_requires_core_strategy_versions():
    registry = StrategyCalibrationRegistry(
        runners={
            "momentum-v1": FakeCalibrationRunner(),
            "breakout-v1": FakeCalibrationRunner(),
            "reversal-v1": FakeCalibrationRunner(),
            "volume-mover-v1": FakeCalibrationRunner(),
        }
    )

    assert registry.available_versions == (
        "breakout-v1",
        "momentum-v1",
        "reversal-v1",
        "volume-mover-v1",
    )
