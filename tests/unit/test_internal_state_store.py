import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from arthabot.common import Direction
from arthabot.internal_state_store import InternalTradingSnapshot, InternalTradingStateStore
from arthabot.internal_state_store import InternalTradingStateTransitions
from arthabot.order_reconciliation import InternalOrderState
from arthabot.reconciliation import InternalPosition


def snapshot():
    return InternalTradingSnapshot(
        available_cash=Decimal("4990.25"),
        orders=(InternalOrderState("o1", "INFY", "COMPLETE", 2),),
        positions=(InternalPosition("INFY", 2, Direction.LONG),),
        updated_at=datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc),
    )


def test_internal_state_store_round_trips_versioned_snapshot(tmp_path):
    store = InternalTradingStateStore(tmp_path / "state.json")

    store.save(snapshot())
    loaded = store.load()

    assert loaded == snapshot()
    assert json.loads((tmp_path / "state.json").read_text())["version"] == 3


def test_internal_state_store_requires_existing_snapshot(tmp_path):
    with pytest.raises(FileNotFoundError, match="internal trading state"):
        InternalTradingStateStore(tmp_path / "missing.json").load()


def test_internal_state_store_rejects_duplicate_order_ids(tmp_path):
    invalid = InternalTradingSnapshot(
        available_cash=Decimal("5000"),
        orders=(
            InternalOrderState("o1", "INFY", "OPEN", 1),
            InternalOrderState("o1", "INFY", "OPEN", 1),
        ),
        positions=(),
        updated_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValueError, match="duplicate internal order"):
        InternalTradingStateStore(tmp_path / "state.json").save(invalid)


def test_internal_state_store_rejects_corrupt_or_unknown_version(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"version": 4}', encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported internal state version"):
        InternalTradingStateStore(path).load()


def test_state_transitions_record_submitted_order_and_fill_position(tmp_path):
    store = InternalTradingStateStore(tmp_path / "state.json")
    store.save(InternalTradingSnapshot(Decimal("5000"), (), (), datetime.now(timezone.utc)))
    transitions = InternalTradingStateTransitions(store=store, clock=lambda: datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc))

    transitions.record_order_submitted(order_id="o1", symbol="INFY", quantity=2)
    transitions.record_order_filled(order_id="o1", symbol="INFY", quantity=2, direction=Direction.LONG)

    loaded = store.load()
    assert loaded.orders == (InternalOrderState("o1", "INFY", "COMPLETE", 2),)
    assert loaded.positions == (InternalPosition("INFY", 2, Direction.LONG),)


def test_state_transitions_cancel_order_without_creating_position(tmp_path):
    store = InternalTradingStateStore(tmp_path / "state.json")
    store.save(InternalTradingSnapshot(Decimal("5000"), (), (), datetime.now(timezone.utc)))
    transitions = InternalTradingStateTransitions(store=store)

    transitions.record_order_submitted(order_id="o1", symbol="INFY", quantity=1)
    transitions.record_order_cancelled(order_id="o1")

    loaded = store.load()
    assert loaded.orders[0].status == "CANCELLED"
    assert loaded.positions == ()


def test_state_transitions_apply_realized_pnl_and_close_position(tmp_path):
    store = InternalTradingStateStore(tmp_path / "state.json")
    store.save(
        InternalTradingSnapshot(
            Decimal("5000"), (), (InternalPosition("INFY", 2, Direction.LONG),), datetime.now(timezone.utc)
        )
    )

    InternalTradingStateTransitions(store=store).record_position_closed(
        symbol="INFY", direction=Direction.LONG, quantity=2, realized_net_pnl=Decimal("25.50")
    )

    loaded = store.load()
    assert loaded.available_cash == Decimal("5025.50")
    assert loaded.positions == ()
