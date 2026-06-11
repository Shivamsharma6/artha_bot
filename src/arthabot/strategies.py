from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arthabot.common import Direction
from arthabot.data import MarketSnapshot


@dataclass(frozen=True)
class TradeCandidate:
    symbol: str
    direction: Direction
    score: Decimal
    rationale: str
    strategy_version: str = "unknown"


class MomentumSignalEngine:
    def __init__(self, *, min_move_pct: Decimal) -> None:
        if min_move_pct <= 0:
            raise ValueError("min_move_pct must be positive")
        self.min_move_pct = min_move_pct

    def generate(self, snapshots: list[MarketSnapshot]) -> list[TradeCandidate]:
        candidates: list[TradeCandidate] = []
        for snapshot in snapshots:
            if snapshot.open_price is None or snapshot.open_price <= 0:
                continue
            move_pct = (snapshot.last_price - snapshot.open_price) / snapshot.open_price
            if move_pct >= self.min_move_pct:
                candidates.append(
                    TradeCandidate(
                        symbol=snapshot.symbol,
                        direction=Direction.LONG,
                        score=move_pct,
                        rationale="Positive intraday momentum from open price.",
                    )
                )
            elif move_pct <= -self.min_move_pct:
                candidates.append(
                    TradeCandidate(
                        symbol=snapshot.symbol,
                        direction=Direction.SHORT,
                        score=abs(move_pct),
                        rationale="Negative intraday momentum from open price.",
                    )
                )
        return candidates
