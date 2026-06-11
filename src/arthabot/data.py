from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    last_price: Decimal
    volume: int
    timestamp: datetime
    open_price: Decimal | None = None


@dataclass(frozen=True)
class FreshnessPolicy:
    max_age_seconds: int

    def is_fresh(self, snapshot: MarketSnapshot, *, now: datetime) -> bool:
        return 0 <= (now - snapshot.timestamp).total_seconds() <= self.max_age_seconds

