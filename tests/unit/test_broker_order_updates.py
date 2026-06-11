from datetime import datetime, timezone
from decimal import Decimal

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.common import Direction
from arthabot.broker_order_updates import BrokerOrderUpdateProcessor
from arthabot.internal_state_store import InternalTradingSnapshot, InternalTradingStateStore, InternalTradingStateTransitions
from arthabot.order_reconciliation import InternalOrderState
from arthabot.reconciliation import InternalPosition


def processor(tmp_path, *, status="OPEN"):
    store = InternalTradingStateStore(tmp_path / "state.json")
    store.save(
        InternalTradingSnapshot(
            Decimal("5000"),
            (InternalOrderState("o1", "INFY", status, 2),),
            (),
            datetime.now(timezone.utc),
        )
    )
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    return BrokerOrderUpdateProcessor(
        state_store=store,
        transitions=InternalTradingStateTransitions(store=store),
        audit=audit,
    ), store, audit


def test_broker_order_update_applies_complete_fill_and_is_idempotent(tmp_path):
    subject, store, audit = processor(tmp_path)
    update = {
        "order_id": "o1",
        "tradingsymbol": "INFY",
        "status": "COMPLETE",
        "filled_quantity": 2,
        "transaction_type": "BUY",
        "average_price": "100",
    }

    first = subject.process(update)
    second = subject.process(update)

    assert first.reason_code == "BROKER_ORDER_FILL_APPLIED"
    assert second.reason_code == "BROKER_ORDER_UPDATE_DUPLICATE"
    assert store.load().positions[0].quantity == 2
    assert audit.read_all()[-1].event_type == "broker_order_update_duplicate"


def test_broker_order_update_applies_cancelled_state(tmp_path):
    subject, store, _ = processor(tmp_path)

    result = subject.process({"order_id": "o1", "tradingsymbol": "INFY", "status": "CANCELLED", "filled_quantity": 0})

    assert result.must_stop_trading is False
    assert store.load().orders[0].status == "CANCELLED"


def test_broker_order_update_fails_closed_on_unknown_order(tmp_path):
    subject, _, audit = processor(tmp_path)

    result = subject.process({"order_id": "external", "tradingsymbol": "INFY", "status": "OPEN", "filled_quantity": 0})

    assert result.reason_code == "UNKNOWN_INTERNAL_ORDER"
    assert result.must_stop_trading is True
    assert audit.read_all()[-1].event_type == "broker_order_update_failed_closed"


def test_broker_order_update_fails_closed_on_partial_fill(tmp_path):
    subject, _, _ = processor(tmp_path)

    result = subject.process(
        {"order_id": "o1", "tradingsymbol": "INFY", "status": "OPEN", "filled_quantity": 1, "transaction_type": "BUY"}
    )

    assert result.reason_code == "PARTIAL_FILL_UNSUPPORTED"
    assert result.must_stop_trading is True


def test_broker_order_update_pairs_exit_fill_and_applies_cost_aware_net_pnl(tmp_path):
    store = InternalTradingStateStore(tmp_path / "state.json")
    store.save(
        InternalTradingSnapshot(
            Decimal("5000"),
            (InternalOrderState("exit-1", "INFY", "OPEN", 2),),
            (InternalPosition("INFY", 2, Direction.LONG, Decimal("100")),),
            datetime.now(timezone.utc),
        )
    )
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    subject = BrokerOrderUpdateProcessor(
        state_store=store,
        transitions=InternalTradingStateTransitions(store=store),
        audit=audit,
    )

    result = subject.process(
        {"order_id": "exit-1", "tradingsymbol": "INFY", "status": "COMPLETE", "filled_quantity": 2,
         "transaction_type": "SELL", "average_price": "105"}
    )

    loaded = store.load()
    assert result.reason_code == "BROKER_EXIT_FILL_APPLIED"
    assert loaded.positions == ()
    assert loaded.available_cash < Decimal("5010")
    assert loaded.available_cash > Decimal("5000")
    assert "realized_net_pnl" in audit.read_all()[-1].payload


def test_broker_order_update_rejects_unknown_status(tmp_path):
    subject, _, _ = processor(tmp_path)

    result = subject.process({"order_id": "o1", "tradingsymbol": "INFY", "status": "MYSTERY", "filled_quantity": 0})

    assert result.reason_code == "UNKNOWN_BROKER_ORDER_STATE"
    assert result.must_stop_trading is True
