from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from arthabot.audit_store import JsonlAuditStore
from arthabot.broker_gateway import BrokerCancelRequest, BrokerModifyRequest, BrokerOrderRequest
from arthabot.common import Direction
from arthabot.http_clients import ZerodhaHttpClient


@dataclass(frozen=True)
class KiteSmokeTestResult:
    ok: bool
    payload: dict[str, Any]


class KiteSmokeTestRunner:
    def __init__(self, *, client: ZerodhaHttpClient, audit: JsonlAuditStore) -> None:
        self.client = client
        self.audit = audit

    def run_balance_probe(self, *, segment: str = "equity") -> KiteSmokeTestResult:
        balance = self.client.fetch_margin_balance(segment=segment)
        result = KiteSmokeTestResult(ok=True, payload=balance)
        self.audit.append(
            event_type="kite_balance_smoke_probe_completed",
            payload={"segment": segment, "ok": result.ok},
        )
        return result

    def run_order_adapter_probe(
        self,
        *,
        symbol: str,
        approved_non_live_order_probe: bool,
        price: Decimal = Decimal("1"),
        quantity: int = 1,
    ) -> KiteSmokeTestResult:
        if not approved_non_live_order_probe:
            raise PermissionError("non-live order probe approval is required")
        placed = self.client.place_order(
            BrokerOrderRequest(
                symbol=symbol,
                direction=Direction.LONG,
                quantity=quantity,
                price=price,
                product="MIS",
            )
        )
        modified = self.client.modify_order(
            BrokerModifyRequest(
                order_id=placed.order_id,
                price=price,
                quantity=quantity,
            )
        )
        cancelled = self.client.cancel_order(BrokerCancelRequest(order_id=placed.order_id))
        payload = {
            "symbol": symbol,
            "place_status": placed.status,
            "modify_status": modified.status,
            "cancel_status": cancelled.status,
            "order_id": placed.order_id,
        }
        self.audit.append(
            event_type="kite_order_adapter_smoke_probe_completed",
            payload=payload,
        )
        return KiteSmokeTestResult(ok=True, payload=payload)
