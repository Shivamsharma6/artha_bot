from __future__ import annotations

from arthabot.backtest import HistoricalDataset
from arthabot.strategy_calibration_runner import HistoricalCoverage


def historical_coverage_from_datasets(datasets: list[HistoricalDataset]) -> HistoricalCoverage:
    if not datasets:
        raise ValueError("at least one historical dataset is required")

    resolutions = {dataset.resolution for dataset in datasets}
    if len(resolutions) != 1:
        raise ValueError("all calibration datasets must use the same resolution")

    timestamps = []
    symbols = []
    for dataset in datasets:
        if not dataset.candles:
            raise ValueError("historical candles are required for calibration coverage")
        symbols.append(dataset.symbol)
        timestamps.extend(candle.timestamp for candle in dataset.candles)

    return HistoricalCoverage(
        data_start=min(timestamps).date(),
        data_end=max(timestamps).date(),
        data_resolution=next(iter(resolutions)),
        symbols=tuple(sorted(symbols)),
    )
