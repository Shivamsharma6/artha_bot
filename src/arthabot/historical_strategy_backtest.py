from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from arthabot.backtest import BacktestExecutionEngine, BacktestReport, BacktestSignal, HistoricalDataset
from arthabot.data import MarketSnapshot
from arthabot.strategy_calibration_factory import StrategyCalibrationInputs
from arthabot.strategies import TradeCandidate


class HistoricalSignalEngine(Protocol):
    def generate(self, snapshots: list[MarketSnapshot]) -> list[TradeCandidate]:
        ...


@dataclass(frozen=True)
class HistoricalStrategyBacktestBuilder:
    signal_engine: HistoricalSignalEngine
    execution_engine: BacktestExecutionEngine
    quantity: int

    def run(self, datasets: list[HistoricalDataset]) -> BacktestReport:
        return self.execution_engine.run(self.build_signals(datasets))

    def build_signals(self, datasets: list[HistoricalDataset]) -> list[BacktestSignal]:
        signals: list[BacktestSignal] = []
        for dataset in datasets:
            if not dataset.candles:
                raise ValueError("historical candles are required for strategy backtests")
            ordered = sorted(dataset.candles, key=lambda candle: candle.timestamp)
            for index, candle in enumerate(ordered[:-1]):
                next_candle = ordered[index + 1]
                snapshot = MarketSnapshot(
                    symbol=dataset.symbol,
                    last_price=candle.close,
                    volume=candle.volume,
                    timestamp=candle.timestamp,
                    open_price=candle.open,
                )
                for candidate in self.signal_engine.generate([snapshot]):
                    if candidate.symbol != dataset.symbol:
                        continue
                    signals.append(
                        BacktestSignal(
                            symbol=candidate.symbol,
                            direction=candidate.direction,
                            entry_date=candle.timestamp.date(),
                            entry_price=candle.close,
                            exit_price=next_candle.close,
                            quantity=self.quantity,
                        )
                    )
        return signals


def build_calibration_inputs_from_historical_backtests(
    *,
    datasets_by_version: dict[str, list[HistoricalDataset]],
    signal_engines_by_version: dict[str, HistoricalSignalEngine],
    execution_engines_by_version: dict[str, BacktestExecutionEngine],
    quantity_by_version: dict[str, int],
    walk_forward_windows_by_version: dict[str, int],
    out_of_sample_tested_by_version: dict[str, bool],
    survivorship_bias_checked_by_version: dict[str, bool],
) -> StrategyCalibrationInputs:
    reports_by_version: dict[str, BacktestReport] = {}
    for version, datasets in datasets_by_version.items():
        _require_version(signal_engines_by_version, version, "signal engine")
        _require_version(execution_engines_by_version, version, "execution engine")
        _require_version(quantity_by_version, version, "quantity")
        _require_version(walk_forward_windows_by_version, version, "walk-forward window count")
        _require_version(out_of_sample_tested_by_version, version, "out-of-sample validation flag")
        _require_version(survivorship_bias_checked_by_version, version, "survivorship-bias validation flag")
        reports_by_version[version] = HistoricalStrategyBacktestBuilder(
            signal_engine=signal_engines_by_version[version],
            execution_engine=execution_engines_by_version[version],
            quantity=quantity_by_version[version],
        ).run(datasets)

    return StrategyCalibrationInputs(
        datasets_by_version=datasets_by_version,
        reports_by_version=reports_by_version,
        walk_forward_windows_by_version=walk_forward_windows_by_version,
        out_of_sample_tested_by_version=out_of_sample_tested_by_version,
        survivorship_bias_checked_by_version=survivorship_bias_checked_by_version,
    )


def _require_version(mapping: dict[str, object], version: str, label: str) -> None:
    if version not in mapping:
        raise ValueError(f"missing {label} for {version}")
