from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from arthabot.brokerage import BrokerageCalculator, TradeSide
from arthabot.common import Direction
from arthabot.trailing_stop import TrailingStopPolicy, TrailingStopState


@dataclass(frozen=True)
class TrackedPosition:
    symbol: str
    direction: Direction
    entry_price: Decimal
    quantity: int
    stop_loss: Decimal
    trailing_stop_step: Decimal
    trailing: TrailingStopState | None
    entry_timestamp: datetime


@dataclass(frozen=True)
class PositionSnapshot:
    open_positions: tuple[TrackedPosition, ...]
    available_capital: Decimal
    daily_realized_pnl: Decimal
    unrealized_pnl: Decimal
    trades_today: int
    open_symbols: frozenset[str]


@dataclass(frozen=True)
class ExitEvent:
    symbol: str
    direction: Direction
    entry_price: Decimal
    exit_price: Decimal
    quantity: int
    gross_pnl: Decimal
    total_costs: Decimal
    net_pnl: Decimal
    reason: str
    timestamp: datetime


class PositionTracker:
    def __init__(
        self,
        *,
        starting_capital: Decimal,
        brokerage: BrokerageCalculator,
        trailing_policy: TrailingStopPolicy | None = None,
    ) -> None:
        self._available_capital = starting_capital
        self._daily_realized_pnl = Decimal("0")
        self._positions: dict[str, TrackedPosition] = {}
        self._trades_today = 0
        self._brokerage = brokerage
        self._trailing_policy = trailing_policy

    def open_position(
        self,
        *,
        symbol: str,
        direction: Direction,
        entry_price: Decimal,
        quantity: int,
        stop_loss: Decimal,
        trailing_stop_step: Decimal,
        now: datetime,
    ) -> None:
        trailing = None
        if trailing_stop_step > 0:
            trailing = TrailingStopState(
                symbol=symbol,
                direction=direction,
                current_stop=stop_loss,
                last_reference_price=entry_price,
                last_modified_at=now,
                modifications=0,
            )
        self._positions[symbol] = TrackedPosition(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            trailing_stop_step=trailing_stop_step,
            trailing=trailing,
            entry_timestamp=now,
        )
        self._trades_today += 1

    def close_position(
        self,
        *,
        symbol: str,
        exit_price: Decimal,
        reason: str,
        now: datetime,
    ) -> ExitEvent:
        position = self._positions.pop(symbol)
        if position.direction == Direction.LONG:
            gross_pnl = (exit_price - position.entry_price) * position.quantity
        else:
            gross_pnl = (position.entry_price - exit_price) * position.quantity
        side = TradeSide.LONG if position.direction == Direction.LONG else TradeSide.SHORT
        costs = self._brokerage.estimate_intraday_equity(
            side=side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
        )
        net_pnl = gross_pnl - costs.total_charges
        self._available_capital += net_pnl
        self._daily_realized_pnl += net_pnl
        return ExitEvent(
            symbol=symbol,
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            gross_pnl=gross_pnl,
            total_costs=costs.total_charges,
            net_pnl=net_pnl,
            reason=reason,
            timestamp=now,
        )

    def on_tick(
        self, *, symbol: str, price: Decimal, now: datetime
    ) -> ExitEvent | None:
        position = self._positions.get(symbol)
        if position is None:
            return None

        # Update trailing stop
        if position.trailing is not None and self._trailing_policy is not None:
            updated = self._trailing_policy.propose_update(
                position.trailing, price=price, now=now
            )
            if updated is not None:
                position = replace(position, trailing=updated)
                self._positions[symbol] = position

        # Check exit condition
        current_stop = (
            position.trailing.current_stop
            if position.trailing
            else position.stop_loss
        )
        if position.direction == Direction.LONG and price <= current_stop:
            return self.close_position(
                symbol=symbol, exit_price=current_stop,
                reason="trailing_stop_hit", now=now,
            )
        if position.direction == Direction.SHORT and price >= current_stop:
            return self.close_position(
                symbol=symbol, exit_price=current_stop,
                reason="trailing_stop_hit", now=now,
            )
        return None

    def close_all_positions(
        self, *, prices: dict[str, Decimal], reason: str, now: datetime
    ) -> list[ExitEvent]:
        events: list[ExitEvent] = []
        for symbol in list(self._positions.keys()):
            price = prices.get(symbol, self._positions[symbol].entry_price)
            events.append(self.close_position(
                symbol=symbol, exit_price=price, reason=reason, now=now,
            ))
        return events

    def unrealized_pnl(self, *, prices: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for position in self._positions.values():
            current_price = prices.get(position.symbol)
            if current_price is None:
                continue
            if position.direction == Direction.LONG:
                total += (current_price - position.entry_price) * position.quantity
            else:
                total += (position.entry_price - current_price) * position.quantity
        return total

    def snapshot(self, *, prices: dict[str, Decimal] | None = None) -> PositionSnapshot:
        unrealized = self.unrealized_pnl(prices=prices) if prices is not None else Decimal("0")
        return PositionSnapshot(
            open_positions=tuple(self._positions.values()),
            available_capital=self._available_capital,
            daily_realized_pnl=self._daily_realized_pnl,
            unrealized_pnl=unrealized,
            trades_today=self._trades_today,
            open_symbols=frozenset(self._positions.keys()),
        )
