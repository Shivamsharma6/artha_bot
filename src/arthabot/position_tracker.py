from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from threading import RLock

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
    trade_id: str = ""


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
    trade_id: str = ""


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
        self._lock = RLock()

    def open_position(
        self,
        *,
        trade_id: str = "",
        symbol: str,
        direction: Direction,
        entry_price: Decimal,
        quantity: int,
        stop_loss: Decimal,
        trailing_stop_step: Decimal,
        now: datetime,
    ) -> None:
        with self._lock:
            self._validate_open_position(
                trade_id=trade_id, symbol=symbol, entry_price=entry_price,
                quantity=quantity, stop_loss=stop_loss,
                trailing_stop_step=trailing_stop_step,
            )
            self._open_position(
                trade_id=trade_id, symbol=symbol, direction=direction,
                entry_price=entry_price, quantity=quantity, stop_loss=stop_loss,
                trailing_stop_step=trailing_stop_step, now=now,
            )

    def _open_position(
        self, *, trade_id: str, symbol: str, direction: Direction,
        entry_price: Decimal, quantity: int, stop_loss: Decimal,
        trailing_stop_step: Decimal, now: datetime,
    ) -> None:
        self._validate_open_position(
            trade_id=trade_id, symbol=symbol, entry_price=entry_price,
            quantity=quantity, stop_loss=stop_loss,
            trailing_stop_step=trailing_stop_step,
        )

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
        notional = entry_price * quantity
        self._available_capital -= notional
        self._positions[symbol] = TrackedPosition(
            trade_id=trade_id,
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

    def validate_open_position(
        self, *, trade_id: str, symbol: str, entry_price: Decimal,
        quantity: int, stop_loss: Decimal, trailing_stop_step: Decimal,
    ) -> None:
        with self._lock:
            self._validate_open_position(
                trade_id=trade_id, symbol=symbol, entry_price=entry_price,
                quantity=quantity, stop_loss=stop_loss,
                trailing_stop_step=trailing_stop_step,
            )

    def _validate_open_position(
        self, *, trade_id: str, symbol: str, entry_price: Decimal,
        quantity: int, stop_loss: Decimal, trailing_stop_step: Decimal,
    ) -> None:
        if not symbol:
            raise ValueError("symbol is required")
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if stop_loss <= 0:
            raise ValueError("stop_loss must be positive")
        if trailing_stop_step < 0:
            raise ValueError("trailing_stop_step must not be negative")
        if symbol in self._positions:
            raise ValueError(f"position already open for {symbol}")
        notional = entry_price * quantity
        if notional > self._available_capital:
            raise ValueError("position notional exceeds available capital")

    def close_position(
        self,
        *,
        symbol: str,
        exit_price: Decimal,
        reason: str,
        now: datetime,
    ) -> ExitEvent:
        with self._lock:
            return self._close_position(symbol=symbol, exit_price=exit_price, reason=reason, now=now)

    def _close_position(self, *, symbol: str, exit_price: Decimal, reason: str, now: datetime) -> ExitEvent:
        if exit_price <= 0:
            raise ValueError("exit_price must be positive")
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
        self._available_capital += position.entry_price * position.quantity + net_pnl
        self._daily_realized_pnl += net_pnl
        return ExitEvent(
            trade_id=position.trade_id,
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
        with self._lock:
            return self._on_tick(symbol=symbol, price=price, now=now)

    def _on_tick(self, *, symbol: str, price: Decimal, now: datetime) -> ExitEvent | None:
        position = self._positions.get(symbol)
        if position is None:
            return None
        # Update trailing stop
        if position.trailing is not None and self._trailing_policy is not None:
            trade_policy = TrailingStopPolicy(
                step=position.trailing_stop_step,
                cooldown_seconds=self._trailing_policy.cooldown_seconds,
                max_modifications_per_trade=self._trailing_policy.max_modifications_per_trade,
            )
            updated = trade_policy.propose_update(
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
            return self._close_position(
                symbol=symbol, exit_price=price,
                reason="trailing_stop_hit", now=now,
            )
        if position.direction == Direction.SHORT and price >= current_stop:
            return self._close_position(
                symbol=symbol, exit_price=price,
                reason="trailing_stop_hit", now=now,
            )
        return None

    def close_all_positions(
        self, *, prices: dict[str, Decimal], reason: str, now: datetime
    ) -> list[ExitEvent]:
        with self._lock:
            missing = [symbol for symbol in self._positions if symbol not in prices]
            if missing:
                raise ValueError(f"missing close price for {', '.join(missing)}")
            invalid = [symbol for symbol in self._positions if prices[symbol] <= 0]
            if invalid:
                raise ValueError(f"invalid close price for {', '.join(invalid)}")
            events: list[ExitEvent] = []
            for symbol in list(self._positions.keys()):
                events.append(self._close_position(
                    symbol=symbol, exit_price=prices[symbol], reason=reason, now=now,
                ))
            return events

    def unrealized_pnl(self, *, prices: dict[str, Decimal]) -> Decimal:
        with self._lock:
            return self._unrealized_pnl(prices=prices)

    def _unrealized_pnl(self, *, prices: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        missing = [position.symbol for position in self._positions.values() if position.symbol not in prices]
        if missing:
            raise ValueError(f"missing current price for {', '.join(missing)}")
        for position in self._positions.values():
            current_price = prices.get(position.symbol)
            if current_price is None or current_price <= 0:
                raise ValueError(f"invalid current price for {position.symbol}")
            if position.direction == Direction.LONG:
                total += (current_price - position.entry_price) * position.quantity
            else:
                total += (position.entry_price - current_price) * position.quantity
        return total

    def snapshot(self, *, prices: dict[str, Decimal] | None = None) -> PositionSnapshot:
        with self._lock:
            unrealized = self._unrealized_pnl(prices=prices) if prices is not None else Decimal("0")
            return PositionSnapshot(
                open_positions=tuple(self._positions.values()),
                available_capital=self._available_capital,
                daily_realized_pnl=self._daily_realized_pnl,
                unrealized_pnl=unrealized,
                trades_today=self._trades_today,
                open_symbols=frozenset(self._positions.keys()),
            )

    def export_state(self) -> dict:
        with self._lock:
            return {
                "available_capital": str(self._available_capital),
                "daily_realized_pnl": str(self._daily_realized_pnl),
                "trades_today": self._trades_today,
                "positions": [
                {
                    "trade_id": position.trade_id,
                    "symbol": position.symbol,
                    "direction": position.direction.value,
                    "entry_price": str(position.entry_price),
                    "quantity": position.quantity,
                    "stop_loss": str(position.stop_loss),
                    "trailing_stop_step": str(position.trailing_stop_step),
                    "entry_timestamp": position.entry_timestamp.isoformat(),
                    "trailing": None if position.trailing is None else {
                        "current_stop": str(position.trailing.current_stop),
                        "last_reference_price": str(position.trailing.last_reference_price),
                        "last_modified_at": position.trailing.last_modified_at.isoformat(),
                        "modifications": position.trailing.modifications,
                    },
                }
                    for position in self._positions.values()
                ],
            }

    def restore(self, state: dict) -> None:
        with self._lock:
            self._restore(state)

    def start_new_day(self) -> None:
        with self._lock:
            if self._positions:
                raise RuntimeError("cannot start new day with open positions")
            self._daily_realized_pnl = Decimal("0")
            self._trades_today = 0

    def _restore(self, state: dict) -> None:
        if self._positions or self._trades_today or self._daily_realized_pnl:
            raise RuntimeError("position tracker can only be restored when empty")
        self._available_capital = Decimal(str(state.get("available_capital", self._available_capital)))
        self._daily_realized_pnl = Decimal(str(state.get("daily_realized_pnl", "0")))
        self._trades_today = int(state.get("trades_today", 0))
        for row in state.get("positions", []):
            direction = Direction(str(row["direction"]))
            trailing_row = row.get("trailing")
            trailing = None
            if trailing_row is not None:
                trailing = TrailingStopState(
                    symbol=str(row["symbol"]), direction=direction,
                    current_stop=Decimal(str(trailing_row["current_stop"])),
                    last_reference_price=Decimal(str(trailing_row["last_reference_price"])),
                    last_modified_at=datetime.fromisoformat(str(trailing_row["last_modified_at"])),
                    modifications=int(trailing_row["modifications"]),
                )
            position = TrackedPosition(
                trade_id=str(row.get("trade_id", "")), symbol=str(row["symbol"]),
                direction=direction, entry_price=Decimal(str(row["entry_price"])),
                quantity=int(row["quantity"]), stop_loss=Decimal(str(row["stop_loss"])),
                trailing_stop_step=Decimal(str(row["trailing_stop_step"])),
                trailing=trailing,
                entry_timestamp=datetime.fromisoformat(str(row["entry_timestamp"])),
            )
            if position.symbol in self._positions:
                raise ValueError(f"duplicate restored position: {position.symbol}")
            self._positions[position.symbol] = position
