from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

from arthabot.audit_store import JsonlAuditStore
from arthabot.order_reconciliation import InternalOrderState, OrderReconciliationService
from arthabot.reconciliation import AccountSnapshot, InternalPosition, ReconciliationService
from arthabot.internal_state_store import InternalTradingStateStore


@dataclass(frozen=True)
class BrokerReconciliationOperationResult:
    ok: bool
    reason_code: str
    must_stop_trading: bool


class BrokerReconciliationOperation:
    def __init__(self, *, client, audit: JsonlAuditStore, cash_tolerance: Decimal = Decimal("0")) -> None:
        self.client = client
        self.audit = audit
        self.account_service = ReconciliationService(cash_tolerance=cash_tolerance)
        self.order_service = OrderReconciliationService()

    def run(
        self,
        *,
        internal_cash: Decimal,
        internal_orders: list[InternalOrderState],
        internal_positions: list[InternalPosition],
    ) -> BrokerReconciliationOperationResult:
        try:
            balance = self.client.fetch_margin_balance(segment="equity")
            broker_orders = self.client.fetch_orders()
            broker_positions = self.client.fetch_positions()
        except Exception as exc:
            return self._failed("BROKER_STATE_UNAVAILABLE", error=str(exc))

        order_result = self.order_service.reconcile(
            broker_orders=broker_orders,
            internal_orders=internal_orders,
        )
        if not order_result.ok:
            return self._failed(order_result.reason_code)

        account_result = self.account_service.reconcile(
            account=AccountSnapshot(available_cash=Decimal(str(balance["available_cash"]))),
            internal_cash=internal_cash,
            broker_positions=broker_positions,
            internal_positions=internal_positions,
        )
        if not account_result.ok:
            return self._failed(account_result.reason_code)

        result = BrokerReconciliationOperationResult(True, "BROKER_STATE_RECONCILED", False)
        self.audit.append(
            event_type="broker_reconciliation_completed",
            payload={
                "reason_code": result.reason_code,
                "order_count": len(broker_orders),
                "position_count": len(broker_positions),
            },
        )
        return result

    def _failed(self, reason_code: str, *, error: str | None = None) -> BrokerReconciliationOperationResult:
        payload = {"reason_code": reason_code, "must_stop_trading": True}
        if error is not None:
            payload["error"] = error
        self.audit.append(event_type="broker_reconciliation_failed_closed", payload=payload)
        return BrokerReconciliationOperationResult(False, reason_code, True)


class BrokerReconciliationSchedulerHandler:
    def __init__(
        self,
        *,
        operation: BrokerReconciliationOperation,
        state_store: InternalTradingStateStore,
        max_state_age_seconds: int,
    ) -> None:
        if max_state_age_seconds <= 0:
            raise ValueError("max_state_age_seconds must be positive")
        self.operation = operation
        self.state_store = state_store
        self.max_state_age_seconds = max_state_age_seconds

    def __call__(self, now: datetime) -> dict[str, object]:
        snapshot = self.state_store.load()
        age = (now - snapshot.updated_at).total_seconds()
        if age < 0:
            raise RuntimeError("internal trading state timestamp is in the future")
        if age > self.max_state_age_seconds:
            raise RuntimeError("internal trading state is stale")
        result = self.operation.run(
            internal_cash=snapshot.available_cash,
            internal_orders=list(snapshot.orders),
            internal_positions=list(snapshot.positions),
        )
        return {
            "reason_code": result.reason_code,
            "must_stop_trading": result.must_stop_trading,
            "state_updated_at": snapshot.updated_at.isoformat(),
            "timestamp": now.isoformat(),
        }
