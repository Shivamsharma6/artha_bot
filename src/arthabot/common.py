from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"


class Mode(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    last_price: Decimal
    timestamp: datetime

