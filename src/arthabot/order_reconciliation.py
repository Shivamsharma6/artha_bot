from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


KNOWN_BROKER_STATES = {"OPEN", "COMPLETE", "CANCELLED", "REJECTED", "TRIGGER PENDING"}


@dataclass(frozen=True)
class BrokerOrderState:
    order_id: str
    symbol: str
    status: str
    filled_quantity: int


@dataclass(frozen=True)
class InternalOrderState:
    order_id: str
    symbol: str
    status: str
    expected_quantity: int
    filled_quantity: int = 0
    average_fill_price: Decimal | None = None
    transaction_type: str | None = None


@dataclass(frozen=True)
class OrderReconciliationResult:
    ok: bool
    reason_code: str
    must_stop_trading: bool


class OrderReconciliationService:
    def reconcile(
        self,
        *,
        broker_orders: list[BrokerOrderState],
        internal_orders: list[InternalOrderState],
    ) -> OrderReconciliationResult:
        broker_by_id = {order.order_id: order for order in broker_orders}
        internal_ids = {order.order_id for order in internal_orders}
        for broker_order in broker_orders:
            if broker_order.status not in KNOWN_BROKER_STATES:
                return OrderReconciliationResult(False, "UNKNOWN_BROKER_ORDER_STATE", True)
            if broker_order.order_id not in internal_ids:
                return OrderReconciliationResult(False, "UNEXPECTED_BROKER_ORDER", True)
        for internal_order in internal_orders:
            broker_order = broker_by_id.get(internal_order.order_id)
            if broker_order is None:
                return OrderReconciliationResult(False, "MISSING_BROKER_ORDER", True)
            if broker_order.symbol != internal_order.symbol:
                return OrderReconciliationResult(False, "ORDER_SYMBOL_MISMATCH", True)
            if broker_order.status != internal_order.status:
                return OrderReconciliationResult(False, "ORDER_STATUS_MISMATCH", True)
            if broker_order.status == "COMPLETE" and broker_order.filled_quantity != internal_order.expected_quantity:
                return OrderReconciliationResult(False, "FILL_MISMATCH", True)
        return OrderReconciliationResult(True, "ORDERS_RECONCILED", False)
