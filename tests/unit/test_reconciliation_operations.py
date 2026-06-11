from decimal import Decimal
import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.common import Direction
from arthabot.order_reconciliation import BrokerOrderState, InternalOrderState
from arthabot.reconciliation import BrokerPosition, InternalPosition
from arthabot.reconciliation_operations import BrokerReconciliationOperation
from arthabot.reconciliation_operations import BrokerReconciliationSchedulerHandler
from arthabot.internal_state_store import InternalTradingSnapshot, InternalTradingStateStore
from datetime import datetime, timedelta, timezone


class BrokerClient:
    def fetch_margin_balance(self, *, segment="equity"):
        return {"available_cash": "5000"}

    def fetch_orders(self):
        return [BrokerOrderState("o1", "INFY", "COMPLETE", 1)]

    def fetch_positions(self):
        return [BrokerPosition("INFY", 1, Direction.LONG)]


def test_broker_reconciliation_operation_audits_complete_match(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    result = BrokerReconciliationOperation(client=BrokerClient(), audit=audit).run(
        internal_cash=Decimal("5000"),
        internal_orders=[InternalOrderState("o1", "INFY", "COMPLETE", 1)],
        internal_positions=[InternalPosition("INFY", 1, Direction.LONG)],
    )

    assert result.ok is True
    assert result.reason_code == "BROKER_STATE_RECONCILED"
    assert result.must_stop_trading is False
    assert audit.read_all()[-1].event_type == "broker_reconciliation_completed"


def test_broker_reconciliation_operation_fails_closed_and_audits_provider_error(tmp_path):
    class FailedClient(BrokerClient):
        def fetch_orders(self):
            raise RuntimeError("broker unavailable")

    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    result = BrokerReconciliationOperation(client=FailedClient(), audit=audit).run(
        internal_cash=Decimal("5000"), internal_orders=[], internal_positions=[]
    )

    assert result.reason_code == "BROKER_STATE_UNAVAILABLE"
    assert result.must_stop_trading is True
    assert audit.read_all()[-1].event_type == "broker_reconciliation_failed_closed"


def test_broker_reconciliation_operation_propagates_order_mismatch_as_stop(tmp_path):
    result = BrokerReconciliationOperation(
        client=BrokerClient(), audit=JsonlAuditStore(tmp_path / "audit.jsonl")
    ).run(internal_cash=Decimal("5000"), internal_orders=[], internal_positions=[])

    assert result.reason_code == "UNEXPECTED_BROKER_ORDER"
    assert result.must_stop_trading is True


def test_reconciliation_scheduler_handler_loads_durable_state(tmp_path):
    now = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
    store = InternalTradingStateStore(tmp_path / "state.json")
    store.save(
        InternalTradingSnapshot(
            available_cash=Decimal("5000"),
            orders=(InternalOrderState("o1", "INFY", "COMPLETE", 1),),
            positions=(InternalPosition("INFY", 1, Direction.LONG),),
            updated_at=now - timedelta(seconds=5),
        )
    )
    handler = BrokerReconciliationSchedulerHandler(
        operation=BrokerReconciliationOperation(client=BrokerClient(), audit=JsonlAuditStore(tmp_path / "audit.jsonl")),
        state_store=store,
        max_state_age_seconds=30,
    )

    payload = handler(now)

    assert payload["reason_code"] == "BROKER_STATE_RECONCILED"
    assert payload["must_stop_trading"] is False


def test_reconciliation_scheduler_handler_rejects_stale_internal_state(tmp_path):
    now = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)
    store = InternalTradingStateStore(tmp_path / "state.json")
    store.save(InternalTradingSnapshot(Decimal("5000"), (), (), now - timedelta(seconds=31)))
    handler = BrokerReconciliationSchedulerHandler(
        operation=BrokerReconciliationOperation(client=BrokerClient(), audit=JsonlAuditStore(tmp_path / "audit.jsonl")),
        state_store=store,
        max_state_age_seconds=30,
    )

    with pytest.raises(RuntimeError, match="internal trading state is stale"):
        handler(now)
