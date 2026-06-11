from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from arthabot.common import Direction
from arthabot.data import MarketSnapshot
from arthabot.strategies import TradeCandidate


class BreakoutSignalEngine:
    def __init__(
        self,
        *,
        resistance_by_symbol: Mapping[str, Decimal] | None = None,
        support_by_symbol: Mapping[str, Decimal] | None = None,
        min_breakout_pct: Decimal,
    ) -> None:
        if min_breakout_pct <= 0:
            raise ValueError("min_breakout_pct must be positive")
        self.resistance_by_symbol = dict(resistance_by_symbol or {})
        self.support_by_symbol = dict(support_by_symbol or {})
        self.min_breakout_pct = min_breakout_pct

    def generate(self, snapshots: list[MarketSnapshot]) -> list[TradeCandidate]:
        candidates: list[TradeCandidate] = []
        for snapshot in snapshots:
            resistance = self.resistance_by_symbol.get(snapshot.symbol)
            if resistance is not None and resistance > 0:
                move_above_resistance = (snapshot.last_price - resistance) / resistance
                if move_above_resistance >= self.min_breakout_pct:
                    candidates.append(
                        TradeCandidate(
                            symbol=snapshot.symbol,
                            direction=Direction.LONG,
                            score=move_above_resistance,
                            rationale="Long breakout above configured resistance.",
                        )
                    )

            support = self.support_by_symbol.get(snapshot.symbol)
            if support is not None and support > 0:
                move_below_support = (support - snapshot.last_price) / support
                if move_below_support >= self.min_breakout_pct:
                    candidates.append(
                        TradeCandidate(
                            symbol=snapshot.symbol,
                            direction=Direction.SHORT,
                            score=move_below_support,
                            rationale="Short breakdown below configured support.",
                        )
                    )
        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)


class ReversalSignalEngine:
    def __init__(self, *, min_reversal_pct: Decimal) -> None:
        if min_reversal_pct <= 0:
            raise ValueError("min_reversal_pct must be positive")
        self.min_reversal_pct = min_reversal_pct

    def generate(self, snapshots: list[MarketSnapshot]) -> list[TradeCandidate]:
        candidates: list[TradeCandidate] = []
        for snapshot in snapshots:
            if snapshot.open_price is None or snapshot.open_price <= 0:
                continue
            move_pct = (snapshot.last_price - snapshot.open_price) / snapshot.open_price
            if move_pct <= -self.min_reversal_pct:
                candidates.append(
                    TradeCandidate(
                        symbol=snapshot.symbol,
                        direction=Direction.LONG,
                        score=abs(move_pct),
                        rationale="Long reversal candidate after deep intraday drop.",
                    )
                )
            elif move_pct >= self.min_reversal_pct:
                candidates.append(
                    TradeCandidate(
                        symbol=snapshot.symbol,
                        direction=Direction.SHORT,
                        score=move_pct,
                        rationale="Short reversal candidate after sharp intraday spike.",
                    )
                )
        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)


class VolumeMoverSignalEngine:
    def __init__(self, *, min_volume: int, min_move_pct: Decimal) -> None:
        if min_volume <= 0:
            raise ValueError("min_volume must be positive")
        if min_move_pct <= 0:
            raise ValueError("min_move_pct must be positive")
        self.min_volume = min_volume
        self.min_move_pct = min_move_pct

    def generate(self, snapshots: list[MarketSnapshot]) -> list[TradeCandidate]:
        candidates: list[TradeCandidate] = []
        for snapshot in snapshots:
            if snapshot.open_price is None or snapshot.open_price <= 0:
                continue
            if snapshot.volume < self.min_volume:
                continue
            move_pct = (snapshot.last_price - snapshot.open_price) / snapshot.open_price
            if abs(move_pct) < self.min_move_pct:
                continue
            direction = Direction.LONG if move_pct > 0 else Direction.SHORT
            candidates.append(
                TradeCandidate(
                    symbol=snapshot.symbol,
                    direction=direction,
                    score=abs(move_pct),
                    rationale="High-volume intraday top mover candidate.",
                )
            )
        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
