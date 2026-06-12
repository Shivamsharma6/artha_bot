from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from arthabot.common import Direction


@dataclass(frozen=True)
class TrailingStopState:
    symbol: str
    direction: Direction
    current_stop: Decimal
    last_reference_price: Decimal
    last_modified_at: datetime
    modifications: int


@dataclass(frozen=True)
class TrailingStopPolicy:
    step: Decimal
    cooldown_seconds: int
    max_modifications_per_trade: int

    def __post_init__(self) -> None:
        if self.step <= 0:
            raise ValueError("trailing stop step must be positive")
        if self.cooldown_seconds < 0:
            raise ValueError("trailing stop cooldown must not be negative")
        if self.max_modifications_per_trade <= 0:
            raise ValueError("trailing stop max modifications must be positive")

    def propose_update(
        self,
        state: TrailingStopState,
        *,
        price: Decimal,
        now: datetime,
    ) -> TrailingStopState | None:
        if state.modifications >= self.max_modifications_per_trade:
            return None
        if (now - state.last_modified_at).total_seconds() < self.cooldown_seconds:
            return None
        if state.direction == Direction.LONG:
            favorable_move = price - state.last_reference_price
            if favorable_move < self.step:
                return None
            new_stop = price - self.step * Decimal("2")
            if new_stop <= state.current_stop:
                return None
        else:
            favorable_move = state.last_reference_price - price
            if favorable_move < self.step:
                return None
            new_stop = price + self.step * Decimal("2")
            if new_stop >= state.current_stop:
                return None
        return TrailingStopState(
            symbol=state.symbol,
            direction=state.direction,
            current_stop=new_stop,
            last_reference_price=price,
            last_modified_at=now,
            modifications=state.modifications + 1,
        )
