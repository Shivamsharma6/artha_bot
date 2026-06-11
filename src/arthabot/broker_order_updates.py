from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from arthabot.audit_store import JsonlAuditStore
from arthabot.common import Direction
from arthabot.brokerage import BrokerageCalculator, BrokerageConfig, TradeSide
from arthabot.internal_state_store import InternalTradingStateStore, InternalTradingStateTransitions


@dataclass(frozen=True)
class BrokerOrderUpdateResult:
    applied: bool
    reason_code: str
    must_stop_trading: bool


class BrokerOrderUpdateProcessor:
    TERMINAL_STATES = {"COMPLETE", "CANCELLED", "REJECTED"}
    KNOWN_STATES = TERMINAL_STATES | {"OPEN", "TRIGGER PENDING"}

    def __init__(
        self,
        *,
        state_store: InternalTradingStateStore,
        transitions: InternalTradingStateTransitions,
        audit: JsonlAuditStore,
        brokerage: BrokerageCalculator | None = None,
    ) -> None:
        self.state_store = state_store
        self.transitions = transitions
        self.audit = audit
        self.brokerage = brokerage or BrokerageCalculator(BrokerageConfig())

    def process(self, update: dict[str, Any]) -> BrokerOrderUpdateResult:
        try:
            order_id = str(update["order_id"])
            symbol = str(update["tradingsymbol"])
            status = str(update["status"])
            filled_quantity = int(update.get("filled_quantity", 0))
        except (KeyError, TypeError, ValueError) as exc:
            return self._failed("MALFORMED_BROKER_ORDER_UPDATE", error=str(exc))
        snapshot = self.state_store.load()
        order = next((item for item in snapshot.orders if item.order_id == order_id), None)
        if order is None:
            return self._failed("UNKNOWN_INTERNAL_ORDER", order_id=order_id)
        if order.symbol != symbol:
            return self._failed("ORDER_SYMBOL_MISMATCH", order_id=order_id)
        if status not in self.KNOWN_STATES:
            return self._failed("UNKNOWN_BROKER_ORDER_STATE", order_id=order_id)
        if order.status == status and status in self.TERMINAL_STATES:
            return self._duplicate(order_id)
        if 0 < filled_quantity < order.expected_quantity:
            return self._failed("PARTIAL_FILL_UNSUPPORTED", order_id=order_id)

        if status == "COMPLETE":
            if filled_quantity != order.expected_quantity:
                return self._failed("FILL_MISMATCH", order_id=order_id)
            transaction_type = str(update.get("transaction_type", ""))
            if transaction_type not in {"BUY", "SELL"}:
                return self._failed("MISSING_ORDER_DIRECTION", order_id=order_id)
            fill_price = update.get("average_price")
            if fill_price is None or Decimal(str(fill_price)) <= 0:
                return self._failed("MISSING_FILL_PRICE", order_id=order_id)
            fill_price = Decimal(str(fill_price))
            fill_direction = Direction.LONG if transaction_type == "BUY" else Direction.SHORT
            opposing = next(
                (position for position in snapshot.positions if position.symbol == symbol and position.direction != fill_direction),
                None,
            )
            if opposing is not None:
                if opposing.quantity != filled_quantity or opposing.entry_price is None:
                    return self._failed("EXIT_POSITION_STATE_MISMATCH", order_id=order_id)
                estimate = self.brokerage.estimate_intraday_equity(
                    side=TradeSide.LONG if opposing.direction == Direction.LONG else TradeSide.SHORT,
                    entry_price=opposing.entry_price,
                    exit_price=fill_price,
                    quantity=filled_quantity,
                )
                self.transitions.record_order_cancelled(order_id=order_id)
                self.transitions.record_position_closed(
                    symbol=symbol,
                    direction=opposing.direction,
                    quantity=filled_quantity,
                    realized_net_pnl=estimate.net_pnl,
                )
                return self._applied("BROKER_EXIT_FILL_APPLIED", order_id, net_pnl=estimate.net_pnl)
            self.transitions.record_order_filled(
                order_id=order_id, symbol=symbol, quantity=filled_quantity,
                direction=fill_direction, fill_price=fill_price,
            )
            return self._applied("BROKER_ORDER_FILL_APPLIED", order_id)
        if status in {"CANCELLED", "REJECTED"}:
            self.transitions.record_order_cancelled(order_id=order_id)
            return self._applied(f"BROKER_ORDER_{status}_APPLIED", order_id)
        if filled_quantity != 0:
            return self._failed("PARTIAL_FILL_UNSUPPORTED", order_id=order_id)
        return BrokerOrderUpdateResult(False, "BROKER_ORDER_UPDATE_NO_CHANGE", False)

    def _applied(self, reason_code: str, order_id: str, *, net_pnl=None) -> BrokerOrderUpdateResult:
        payload = {"order_id": order_id, "reason_code": reason_code}
        if net_pnl is not None:
            payload["realized_net_pnl"] = str(net_pnl)
        self.audit.append(event_type="broker_order_update_applied", payload=payload)
        return BrokerOrderUpdateResult(True, reason_code, False)

    def _duplicate(self, order_id: str) -> BrokerOrderUpdateResult:
        self.audit.append(event_type="broker_order_update_duplicate", payload={"order_id": order_id})
        return BrokerOrderUpdateResult(False, "BROKER_ORDER_UPDATE_DUPLICATE", False)

    def _failed(self, reason_code: str, *, order_id: str | None = None, error: str | None = None) -> BrokerOrderUpdateResult:
        payload: dict[str, Any] = {"reason_code": reason_code, "must_stop_trading": True}
        if order_id is not None:
            payload["order_id"] = order_id
        if error is not None:
            payload["error"] = error
        self.audit.append(event_type="broker_order_update_failed_closed", payload=payload)
        return BrokerOrderUpdateResult(False, reason_code, True)
