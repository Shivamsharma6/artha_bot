from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from arthabot.common import Direction
from arthabot.order_reconciliation import InternalOrderState
from arthabot.reconciliation import InternalPosition


@dataclass(frozen=True)
class InternalTradingSnapshot:
    available_cash: Decimal
    orders: tuple[InternalOrderState, ...]
    positions: tuple[InternalPosition, ...]
    updated_at: datetime


class InternalTradingStateStore:
    VERSION = 3

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, snapshot: InternalTradingSnapshot) -> None:
        self._validate(snapshot)
        payload = {
            "version": self.VERSION,
            "available_cash": str(snapshot.available_cash),
            "updated_at": snapshot.updated_at.isoformat(),
            "orders": [
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "status": order.status,
                    "expected_quantity": order.expected_quantity,
                    "filled_quantity": order.filled_quantity,
                    "average_fill_price": str(order.average_fill_price) if order.average_fill_price is not None else None,
                    "transaction_type": order.transaction_type,
                }
                for order in snapshot.orders
            ],
            "positions": [
                {
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "direction": position.direction.value,
                    "entry_price": str(position.entry_price) if position.entry_price is not None else None,
                }
                for position in snapshot.positions
            ],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)

    def load(self) -> InternalTradingSnapshot:
        if not self.path.is_file():
            raise FileNotFoundError("internal trading state snapshot is unavailable")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("internal trading state snapshot is corrupt") from exc
        if payload.get("version") not in {1, 2, self.VERSION}:
            raise ValueError("unsupported internal state version")
        try:
            snapshot = InternalTradingSnapshot(
                available_cash=Decimal(str(payload["available_cash"])),
                updated_at=datetime.fromisoformat(str(payload["updated_at"])),
                orders=tuple(
                    InternalOrderState(
                        order_id=str(row["order_id"]),
                        symbol=str(row["symbol"]),
                        status=str(row["status"]),
                        expected_quantity=int(row["expected_quantity"]),
                        filled_quantity=int(row.get("filled_quantity", 0)),
                        average_fill_price=(
                            Decimal(str(row["average_fill_price"]))
                            if row.get("average_fill_price") is not None else None
                        ),
                        transaction_type=(str(row["transaction_type"]) if row.get("transaction_type") else None),
                    )
                    for row in payload["orders"]
                ),
                positions=tuple(
                    InternalPosition(
                        symbol=str(row["symbol"]),
                        quantity=int(row["quantity"]),
                        direction=Direction(str(row["direction"])),
                        entry_price=Decimal(str(row["entry_price"])) if row.get("entry_price") is not None else None,
                    )
                    for row in payload["positions"]
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("internal trading state snapshot is corrupt") from exc
        self._validate(snapshot)
        return snapshot

    @staticmethod
    def _validate(snapshot: InternalTradingSnapshot) -> None:
        if snapshot.available_cash < 0:
            raise ValueError("internal available cash must not be negative")
        if snapshot.updated_at.tzinfo is None:
            raise ValueError("internal state timestamp must be timezone-aware")
        order_ids = [order.order_id for order in snapshot.orders]
        if len(order_ids) != len(set(order_ids)):
            raise ValueError("duplicate internal order id")
        if any(order.expected_quantity <= 0 for order in snapshot.orders):
            raise ValueError("internal order quantity must be positive")
        if any(order.filled_quantity < 0 or order.filled_quantity > order.expected_quantity for order in snapshot.orders):
            raise ValueError("internal order filled quantity is invalid")
        if any(position.quantity <= 0 for position in snapshot.positions):
            raise ValueError("internal position quantity must be positive")


class InternalTradingStateTransitions:
    def __init__(self, *, store: InternalTradingStateStore, clock=None) -> None:
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def record_order_submitted(
        self,
        *,
        order_id: str,
        symbol: str,
        quantity: int,
        transaction_type: str | None = None,
    ) -> None:
        snapshot = self.store.load()
        if any(order.order_id == order_id for order in snapshot.orders):
            raise ValueError("duplicate internal order id")
        self._save(
            snapshot,
            orders=(*snapshot.orders, InternalOrderState(
                order_id, symbol, "OPEN", quantity,
                transaction_type=transaction_type,
            )),
        )

    def record_fill_progress(
        self,
        *,
        order_id: str,
        cumulative_filled_quantity: int,
        cumulative_average_price: Decimal,
        direction: Direction,
        realized_net_pnl: Decimal | None = None,
    ) -> int:
        snapshot = self.store.load()
        order = next((item for item in snapshot.orders if item.order_id == order_id), None)
        if order is None:
            raise KeyError(f"missing internal order: {order_id}")
        if cumulative_filled_quantity < order.filled_quantity:
            raise ValueError("broker filled quantity moved backwards")
        if cumulative_filled_quantity > order.expected_quantity:
            raise ValueError("broker fill exceeds expected quantity")
        delta = cumulative_filled_quantity - order.filled_quantity
        if delta == 0:
            return 0
        prior_fill_value = (order.average_fill_price or Decimal("0")) * order.filled_quantity
        delta_fill_price = (
            cumulative_average_price * cumulative_filled_quantity - prior_fill_value
        ) / delta
        status = "COMPLETE" if cumulative_filled_quantity == order.expected_quantity else "OPEN"
        updated_order = InternalOrderState(
            order.order_id,
            order.symbol,
            status,
            order.expected_quantity,
            cumulative_filled_quantity,
            cumulative_average_price,
            order.transaction_type,
        )
        orders = tuple(updated_order if item.order_id == order_id else item for item in snapshot.orders)
        opposing = next(
            (position for position in snapshot.positions if position.symbol == order.symbol and position.direction != direction),
            None,
        )
        positions = list(snapshot.positions)
        available_cash = snapshot.available_cash
        if opposing is not None:
            if opposing.quantity < delta or opposing.entry_price is None or realized_net_pnl is None:
                raise ValueError("exit fill cannot be reconciled with internal position")
            positions.remove(opposing)
            if opposing.quantity > delta:
                positions.append(InternalPosition(order.symbol, opposing.quantity - delta, opposing.direction, opposing.entry_price))
            available_cash += realized_net_pnl
        else:
            existing = next(
                (position for position in positions if position.symbol == order.symbol and position.direction == direction),
                None,
            )
            if existing is not None:
                positions.remove(existing)
                prior_value = (existing.entry_price or delta_fill_price) * existing.quantity
                entry_price = (prior_value + delta_fill_price * delta) / (existing.quantity + delta)
                positions.append(InternalPosition(order.symbol, existing.quantity + delta, direction, entry_price))
            else:
                positions.append(InternalPosition(order.symbol, delta, direction, delta_fill_price))
        self._save(snapshot, available_cash=available_cash, orders=orders, positions=tuple(positions))
        return delta

    def record_order_filled(
        self,
        *,
        order_id: str,
        symbol: str,
        quantity: int,
        direction: Direction,
        fill_price: Decimal | None = None,
    ) -> None:
        snapshot = self.store.load()
        orders = self._replace_order(snapshot.orders, order_id=order_id, status="COMPLETE", quantity=quantity)
        existing = next(
            (position for position in snapshot.positions if position.symbol == symbol and position.direction == direction),
            None,
        )
        positions = tuple(
            position for position in snapshot.positions
            if not (position.symbol == symbol and position.direction == direction)
        )
        total_quantity = quantity + (existing.quantity if existing is not None else 0)
        entry_price = fill_price
        if existing is not None and existing.entry_price is not None and fill_price is not None:
            entry_price = ((existing.entry_price * existing.quantity) + (fill_price * quantity)) / total_quantity
        elif existing is not None:
            entry_price = existing.entry_price
        self._save(snapshot, orders=orders, positions=(*positions, InternalPosition(symbol, total_quantity, direction, entry_price)))

    def record_order_cancelled(self, *, order_id: str) -> None:
        snapshot = self.store.load()
        self._save(snapshot, orders=self._replace_order(snapshot.orders, order_id=order_id, status="CANCELLED"))

    def record_position_closed(
        self,
        *,
        symbol: str,
        direction: Direction,
        quantity: int,
        realized_net_pnl: Decimal,
    ) -> None:
        snapshot = self.store.load()
        matching = next(
            (position for position in snapshot.positions if position.symbol == symbol and position.direction == direction),
            None,
        )
        if matching is None or matching.quantity < quantity:
            raise ValueError("position close exceeds internal position quantity")
        positions = tuple(
            position for position in snapshot.positions
            if not (position.symbol == symbol and position.direction == direction)
        )
        remaining = matching.quantity - quantity
        if remaining:
            positions = (*positions, InternalPosition(symbol, remaining, direction))
        self._save(snapshot, available_cash=snapshot.available_cash + realized_net_pnl, positions=positions)

    def _save(self, snapshot: InternalTradingSnapshot, **changes) -> None:
        self.store.save(
            InternalTradingSnapshot(
                available_cash=changes.get("available_cash", snapshot.available_cash),
                orders=changes.get("orders", snapshot.orders),
                positions=changes.get("positions", snapshot.positions),
                updated_at=self.clock(),
            )
        )

    @staticmethod
    def _replace_order(
        orders: tuple[InternalOrderState, ...],
        *,
        order_id: str,
        status: str,
        quantity: int | None = None,
    ) -> tuple[InternalOrderState, ...]:
        current = next((order for order in orders if order.order_id == order_id), None)
        if current is None:
            raise KeyError(f"missing internal order: {order_id}")
        expected_quantity = current.expected_quantity if quantity is None else quantity
        if quantity is not None and quantity != current.expected_quantity:
            raise ValueError("filled quantity does not match internal order")
        return tuple(
            InternalOrderState(
                order.order_id,
                order.symbol,
                status,
                expected_quantity,
                order.filled_quantity,
                order.average_fill_price,
                order.transaction_type,
            )
            if order.order_id == order_id else order
            for order in orders
        )
