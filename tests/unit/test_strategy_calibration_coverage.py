from datetime import datetime, timezone
from decimal import Decimal

import pytest

from arthabot.backtest import Candle, HistoricalDataset
from arthabot.strategy_calibration_coverage import historical_coverage_from_datasets


def candle(day: str) -> Candle:
    return Candle(
        timestamp=datetime.fromisoformat(f"{day}T09:15:00+00:00"),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=1000,
    )


def test_historical_coverage_from_datasets_summarizes_symbols_dates_and_resolution():
    coverage = historical_coverage_from_datasets(
        [
            HistoricalDataset(symbol="INFY", resolution="1m", candles=[candle("2023-01-01"), candle("2026-01-02")]),
            HistoricalDataset(symbol="TCS", resolution="1m", candles=[candle("2023-02-01"), candle("2025-12-31")]),
        ]
    )

    assert coverage.symbols == ("INFY", "TCS")
    assert coverage.data_resolution == "1m"
    assert coverage.data_start.isoformat() == "2023-01-01"
    assert coverage.data_end.isoformat() == "2026-01-02"


def test_historical_coverage_from_datasets_rejects_mixed_resolutions():
    with pytest.raises(ValueError, match="same resolution"):
        historical_coverage_from_datasets(
            [
                HistoricalDataset(symbol="INFY", resolution="1m", candles=[candle("2023-01-01")]),
                HistoricalDataset(symbol="TCS", resolution="5m", candles=[candle("2023-01-01")]),
            ]
        )


def test_historical_coverage_from_datasets_rejects_empty_dataset():
    with pytest.raises(ValueError, match="historical candles"):
        historical_coverage_from_datasets(
            [HistoricalDataset(symbol="INFY", resolution="1m", candles=[])]
        )
