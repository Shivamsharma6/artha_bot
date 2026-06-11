from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.broker_gateway import BrokerModifyRequest, ZerodhaGateway
from arthabot.common import Direction
from arthabot.trailing_stop import TrailingStopPolicy, TrailingStopState


@dataclass(frozen=True)
class OpenPositionState:
    symbol: str
    quantity: int
    direction: Direction
    open: bool


@dataclass(frozen=True)
class BrokerStopOrderState:
    order_id: str
    status: str
    quantity: int


class BrokerTrailingStopWorkflow:
    def __init__(self, *, gateway: ZerodhaGateway, policy: TrailingStopPolicy, audit: JsonlAuditStore) -> None:
        self.gateway = gateway
        self.policy = policy
        self.audit = audit

    def maybe_modify(
        self,
        *,
        position: OpenPositionState,
        stop_order: BrokerStopOrderState,
        trailing: TrailingStopState,
        price: Decimal,
        quote_timestamp: datetime,
        now: datetime,
    ) -> TrailingStopState | None:
        if not position.open:
            self.audit.append(event_type="stop_modify_skipped", payload={"symbol": position.symbol, "reason": "POSITION_CLOSED"})
            return None
        if stop_order.status not in {"OPEN", "TRIGGER PENDING"}:
            self.audit.append(
                event_type="stop_modify_blocked",
                payload={"symbol": position.symbol, "reason": "INVALID_ORDER_STATE", "status": stop_order.status},
            )
            raise RuntimeError("stop-loss order state is not modifiable")
        if position.quantity != stop_order.quantity:
            raise RuntimeError("position and stop-loss order quantity mismatch")
        if (now - quote_timestamp).total_seconds() < 0:
            raise RuntimeError("quote timestamp is in the future")
        if (now - quote_timestamp).total_seconds() > self.policy.cooldown_seconds:
            self.audit.append(event_type="stop_modify_blocked", payload={"symbol": position.symbol, "reason": "STALE_QUOTE"})
            raise RuntimeError("quote is stale")

        proposed = self.policy.propose_update(trailing, price=price, now=now)
        if proposed is None:
            self.audit.append(event_type="stop_modify_skipped", payload={"symbol": position.symbol, "reason": "NO_POLICY_UPDATE"})
            return None
        response = self.gateway.modify_order(
            BrokerModifyRequest(order_id=stop_order.order_id, price=proposed.current_stop, quantity=position.quantity)
        )
        self.audit.append(
            event_type="stop_modified",
            payload={
                "symbol": position.symbol,
                "order_id": response.order_id,
                "status": response.status,
                "new_stop": str(proposed.current_stop),
            },
        )
        return proposed

