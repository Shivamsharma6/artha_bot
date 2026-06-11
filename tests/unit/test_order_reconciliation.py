from decimal import Decimal

from arthabot.order_reconciliation import BrokerOrderState, InternalOrderState, OrderReconciliationService


def test_order_reconciliation_passes_when_status_and_fill_match():
    service = OrderReconciliationService()

    result = service.reconcile(
        broker_orders=[
            BrokerOrderState(order_id="o1", symbol="INFY", status="COMPLETE", filled_quantity=2),
        ],
        internal_orders=[
            InternalOrderState(order_id="o1", symbol="INFY", status="COMPLETE", expected_quantity=2),
        ],
    )

    assert result.ok
    assert result.reason_code == "ORDERS_RECONCILED"
    assert not result.must_stop_trading


def test_order_reconciliation_fails_closed_on_unknown_broker_order_state():
    service = OrderReconciliationService()

    result = service.reconcile(
        broker_orders=[
            BrokerOrderState(order_id="o1", symbol="INFY", status="MYSTERY", filled_quantity=0),
        ],
        internal_orders=[
            InternalOrderState(order_id="o1", symbol="INFY", status="OPEN", expected_quantity=2),
        ],
    )

    assert not result.ok
    assert result.reason_code == "UNKNOWN_BROKER_ORDER_STATE"
    assert result.must_stop_trading


def test_order_reconciliation_fails_closed_on_missing_broker_order():
    service = OrderReconciliationService()

    result = service.reconcile(
        broker_orders=[],
        internal_orders=[
            InternalOrderState(order_id="o1", symbol="INFY", status="OPEN", expected_quantity=1),
        ],
    )

    assert not result.ok
    assert result.reason_code == "MISSING_BROKER_ORDER"
    assert result.must_stop_trading


def test_order_reconciliation_fails_closed_on_fill_mismatch():
    service = OrderReconciliationService()

    result = service.reconcile(
        broker_orders=[
            BrokerOrderState(order_id="o1", symbol="INFY", status="COMPLETE", filled_quantity=1),
        ],
        internal_orders=[
            InternalOrderState(order_id="o1", symbol="INFY", status="COMPLETE", expected_quantity=2),
        ],
    )

    assert not result.ok
    assert result.reason_code == "FILL_MISMATCH"
    assert result.must_stop_trading

