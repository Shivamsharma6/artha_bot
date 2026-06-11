from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.broker_gateway import BrokerOrderRequest, ZerodhaGateway
from arthabot.internal_state_store import InternalTradingStateTransitions
from arthabot.common import Direction, Mode


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    direction: Direction
    quantity: int
    price: Decimal


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    simulated: bool
    status: str


class ExecutionEngine:
    def __init__(
        self,
        *,
        gateway: ZerodhaGateway | None = None,
        audit: JsonlAuditStore | None = None,
        state_transitions: InternalTradingStateTransitions | None = None,
    ) -> None:
        self.gateway = gateway
        self.audit = audit
        self.state_transitions = state_transitions
        self.real_orders_submitted: list[OrderIntent] = []

    def submit(
        self,
        intent: OrderIntent,
        *,
        mode: Mode,
        risk_approved: bool,
        live_enabled: bool = False,
    ) -> OrderResult:
        if not risk_approved:
            raise PermissionError("Risk Engine approval is required before execution")
        if intent.quantity <= 0:
            raise ValueError("quantity must be positive")
        if intent.price <= 0:
            raise ValueError("price must be positive")
        if mode in {Mode.BACKTEST, Mode.PAPER}:
            return OrderResult(
                order_id=f"sim-{mode.value.lower()}-{intent.symbol}",
                simulated=True,
                status="accepted",
            )
        if not live_enabled:
            raise PermissionError("LIVE mode requires explicit configuration")
        if self.gateway is None or self.audit is None or self.state_transitions is None:
            raise RuntimeError("LIVE execution requires an injected gateway, audit store, and state transitions")
        try:
            response = self.gateway.place_intraday_order(
                BrokerOrderRequest(
                    symbol=intent.symbol,
                    direction=intent.direction,
                    quantity=intent.quantity,
                    price=intent.price,
                )
            )
        except Exception as exc:
            self.audit.append(
                event_type="live_order_submission_failed",
                payload={
                    "symbol": intent.symbol,
                    "direction": intent.direction.value,
                    "quantity": intent.quantity,
                    "error": str(exc),
                },
            )
            raise
        try:
            self.state_transitions.record_order_submitted(
                order_id=response.order_id,
                symbol=intent.symbol,
                quantity=intent.quantity,
                transaction_type="BUY" if intent.direction == Direction.LONG else "SELL",
            )
        except Exception as exc:
            self.audit.append(
                event_type="live_order_state_uncertain",
                payload={
                    "symbol": intent.symbol,
                    "order_id": response.order_id,
                    "status": response.status,
                    "error": str(exc),
                    "must_stop_trading": True,
                },
            )
            raise RuntimeError("broker accepted order but durable state update failed") from exc
        self.real_orders_submitted.append(intent)
        self.audit.append(
            event_type="live_order_submitted",
            payload={
                "symbol": intent.symbol,
                "direction": intent.direction.value,
                "quantity": intent.quantity,
                "order_id": response.order_id,
                "status": response.status,
            },
        )
        return OrderResult(order_id=response.order_id, simulated=False, status=response.status)
