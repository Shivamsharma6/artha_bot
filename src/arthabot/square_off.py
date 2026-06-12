from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.broker_gateway import BrokerCancelRequest, BrokerOrderRequest, ZerodhaGateway
from arthabot.common import Direction
from arthabot.internal_state_store import InternalTradingStateStore, InternalTradingStateTransitions


@dataclass(frozen=True)
class SquareOffResult:
    submitted_orders: tuple[str, ...]
    cancelled_orders: tuple[str, ...]
    must_stop_trading: bool
    reason_code: str


class ForcedSquareOffService:
    def __init__(
        self,
        *,
        gateway: ZerodhaGateway,
        state_store: InternalTradingStateStore,
        transitions: InternalTradingStateTransitions,
        audit: JsonlAuditStore,
    ) -> None:
        self.gateway = gateway
        self.state_store = state_store
        self.transitions = transitions
        self.audit = audit

    def run(self, *, now: datetime) -> SquareOffResult:
        snapshot = self.state_store.load()
        cancelled: list[str] = []
        submitted: list[str] = []
        try:
            for order in snapshot.orders:
                if order.status not in {"OPEN", "TRIGGER PENDING"}:
                    continue
                response = self.gateway.cancel_order(BrokerCancelRequest(order_id=order.order_id))
                self.transitions.record_order_cancelled(order_id=order.order_id)
                cancelled.append(response.order_id)

            if cancelled:
                import time
                time.sleep(2.0)  # Wait for broker order updates to reconcile cancelled states and partial fills via WS

            snapshot = self.state_store.load()
            for position in snapshot.positions:
                exit_direction = Direction.SHORT if position.direction == Direction.LONG else Direction.LONG
                response = self.gateway.place_intraday_order(
                    BrokerOrderRequest(
                        symbol=position.symbol,
                        direction=exit_direction,
                        quantity=position.quantity,
                        price=Decimal("0"),
                        order_type="MARKET",
                    )
                )
                self.transitions.record_order_submitted(
                    order_id=response.order_id,
                    symbol=position.symbol,
                    quantity=position.quantity,
                    transaction_type="SELL" if exit_direction == Direction.SHORT else "BUY",
                )
                submitted.append(response.order_id)
        except Exception as exc:
            self.audit.append(
                event_type="forced_square_off_failed_closed",
                payload={
                    "reason_code": "SQUARE_OFF_STATE_UNCERTAIN",
                    "submitted_orders": submitted,
                    "cancelled_orders": cancelled,
                    "error": str(exc),
                    "must_stop_trading": True,
                    "timestamp": now.isoformat(),
                },
            )
            return SquareOffResult(tuple(submitted), tuple(cancelled), True, "SQUARE_OFF_STATE_UNCERTAIN")

        reason_code = "SQUARE_OFF_ORDERS_SUBMITTED" if submitted else "NO_OPEN_POSITIONS"
        self.audit.append(
            event_type="forced_square_off_completed",
            payload={
                "reason_code": reason_code,
                "submitted_orders": submitted,
                "cancelled_orders": cancelled,
                "timestamp": now.isoformat(),
            },
        )
        return SquareOffResult(tuple(submitted), tuple(cancelled), False, reason_code)


class ForcedSquareOffSchedulerHandler:
    def __init__(self, *, service: ForcedSquareOffService) -> None:
        self.service = service

    def __call__(self, now: datetime) -> dict[str, object]:
        result = self.service.run(now=now)
        return {
            "reason_code": result.reason_code,
            "submitted_orders": list(result.submitted_orders),
            "cancelled_orders": list(result.cancelled_orders),
            "must_stop_trading": result.must_stop_trading,
            "timestamp": now.isoformat(),
        }
