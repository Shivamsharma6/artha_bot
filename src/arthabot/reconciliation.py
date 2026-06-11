from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arthabot.common import Direction


@dataclass(frozen=True)
class AccountSnapshot:
    available_cash: Decimal


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    quantity: int
    direction: Direction


@dataclass(frozen=True)
class InternalPosition:
    symbol: str
    quantity: int
    direction: Direction
    entry_price: Decimal | None = None


@dataclass(frozen=True)
class ReconciliationResult:
    ok: bool
    reason_code: str
    must_stop_trading: bool


class ReconciliationService:
    def __init__(self, *, cash_tolerance: Decimal = Decimal("0.00")) -> None:
        self.cash_tolerance = cash_tolerance

    def reconcile(
        self,
        *,
        account: AccountSnapshot | None,
        internal_cash: Decimal,
        broker_positions: list[BrokerPosition],
        internal_positions: list[InternalPosition],
    ) -> ReconciliationResult:
        if account is None:
            raise ValueError("account balance must be verified before trading")
        cash_difference = abs(account.available_cash - internal_cash)
        if cash_difference > self.cash_tolerance:
            return ReconciliationResult(False, "CASH_MISMATCH", True)
        if self._position_map(broker_positions) != self._position_map(internal_positions):
            return ReconciliationResult(False, "POSITION_MISMATCH", True)
        return ReconciliationResult(True, "RECONCILED", False)

    @staticmethod
    def _position_map(
        positions: list[BrokerPosition] | list[InternalPosition],
    ) -> dict[tuple[str, Direction], int]:
        totals: dict[tuple[str, Direction], int] = {}
        for position in positions:
            key = (position.symbol, position.direction)
            totals[key] = totals.get(key, 0) + position.quantity
        return totals
