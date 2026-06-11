from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from arthabot.backtest import Candle, HistoricalDataset
from arthabot.data import MarketSnapshot


@dataclass(frozen=True)
class HistoricalBar:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    resolution: str


class CachedMarketDataStore:
    def __init__(self, *, max_age_seconds: int) -> None:
        self.max_age_seconds = max_age_seconds
        self._snapshots: dict[str, MarketSnapshot] = {}
        self._history: dict[str, list[HistoricalBar]] = {}

    def put_snapshot(self, symbol: str, *, price: Decimal, volume: int, timestamp: datetime) -> None:
        self._snapshots[symbol] = MarketSnapshot(
            symbol=symbol,
            last_price=price,
            volume=volume,
            timestamp=timestamp,
        )

    def get_fresh_snapshot(self, symbol: str, *, now: datetime) -> MarketSnapshot:
        snapshot = self._snapshots.get(symbol)
        if snapshot is None:
            raise KeyError(f"no snapshot for {symbol}")
        age = (now - snapshot.timestamp).total_seconds()
        if age < 0 or age > self.max_age_seconds:
            raise ValueError(f"snapshot for {symbol} is stale")
        return snapshot

    def put_historical_bar(self, bar: HistoricalBar) -> None:
        self._history.setdefault(bar.symbol, []).append(bar)

    def get_historical_dataset(self, symbol: str) -> HistoricalDataset:
        bars = sorted(self._history.get(symbol, []), key=lambda item: item.timestamp)
        if not bars:
            raise KeyError(f"no historical bars for {symbol}")
        resolutions = {bar.resolution for bar in bars}
        if len(resolutions) != 1:
            raise ValueError("historical dataset mixes resolutions")
        return HistoricalDataset(
            symbol=symbol,
            resolution=bars[0].resolution,
            candles=[
                Candle(
                    timestamp=bar.timestamp,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                )
                for bar in bars
            ],
        )

