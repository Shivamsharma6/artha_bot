from decimal import Decimal

import pytest

from arthabot.common import Direction, Mode
from arthabot.execution import ExecutionEngine, OrderIntent
from arthabot.observability import AuditLogger
from arthabot.audit_store import JsonlAuditStore
from arthabot.broker_gateway import BrokerOrderRequest, BrokerOrderResponse, ZerodhaGateway
from arthabot.secrets import SecretConfig
from arthabot.internal_state_store import InternalTradingSnapshot, InternalTradingStateStore, InternalTradingStateTransitions
from arthabot.order_reconciliation import InternalOrderState
from datetime import datetime, timezone


def test_execution_never_places_real_orders_in_backtest_or_paper():
    engine = ExecutionEngine()
    intent = OrderIntent(symbol="TCS", direction=Direction.LONG, quantity=1, price=Decimal("100"))

    backtest_result = engine.submit(intent, mode=Mode.BACKTEST, risk_approved=True)
    paper_result = engine.submit(intent, mode=Mode.PAPER, risk_approved=True)

    assert backtest_result.simulated
    assert paper_result.simulated
    assert engine.real_orders_submitted == []


def test_execution_rejects_unapproved_live_order():
    engine = ExecutionEngine()
    intent = OrderIntent(symbol="TCS", direction=Direction.LONG, quantity=1, price=Decimal("100"))

    with pytest.raises(PermissionError):
        engine.submit(intent, mode=Mode.LIVE, risk_approved=False, live_enabled=True)


def test_execution_submits_audited_live_intraday_order_through_injected_gateway(tmp_path):
    requests: list[BrokerOrderRequest] = []
    gateway = ZerodhaGateway(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        submit_order=lambda request: requests.append(request)
        or BrokerOrderResponse(order_id="kite-1", status="OPEN", raw={"secret": "not-audited"}),
    )
    audit = JsonlAuditStore(tmp_path / "execution.audit.jsonl")
    state_store = InternalTradingStateStore(tmp_path / "state.json")
    state_store.save(InternalTradingSnapshot(Decimal("5000"), (), (), datetime.now(timezone.utc)))
    engine = ExecutionEngine(
        gateway=gateway,
        audit=audit,
        state_transitions=InternalTradingStateTransitions(store=state_store),
    )
    intent = OrderIntent(symbol="INFY", direction=Direction.SHORT, quantity=2, price=Decimal("1510.5"))

    result = engine.submit(intent, mode=Mode.LIVE, risk_approved=True, live_enabled=True)

    assert requests == [
        BrokerOrderRequest(
            symbol="INFY",
            direction=Direction.SHORT,
            quantity=2,
            price=Decimal("1510.5"),
        )
    ]
    assert result.order_id == "kite-1"
    assert result.status == "OPEN"
    assert result.simulated is False
    assert engine.real_orders_submitted == [intent]
    assert state_store.load().orders == (InternalOrderState("kite-1", "INFY", "OPEN", 2),)
    event = audit.read_all()[-1]
    assert event.event_type == "live_order_submitted"
    assert event.payload == {
        "symbol": "INFY",
        "direction": "short",
        "quantity": 2,
        "order_id": "kite-1",
        "status": "OPEN",
    }


def test_execution_rejects_live_order_without_gateway_or_audit():
    intent = OrderIntent(symbol="INFY", direction=Direction.LONG, quantity=1, price=Decimal("100"))

    with pytest.raises(RuntimeError, match="gateway, audit store, and state transitions"):
        ExecutionEngine().submit(intent, mode=Mode.LIVE, risk_approved=True, live_enabled=True)


def test_execution_rejects_nonpositive_limit_price_before_gateway_call(tmp_path):
    calls = []
    gateway = ZerodhaGateway(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        submit_order=lambda request: calls.append(request),
    )

    with pytest.raises(ValueError, match="price must be positive"):
        ExecutionEngine(gateway=gateway, audit=JsonlAuditStore(tmp_path / "audit.jsonl")).submit(
            OrderIntent(symbol="INFY", direction=Direction.LONG, quantity=1, price=Decimal("0")),
            mode=Mode.LIVE,
            risk_approved=True,
            live_enabled=True,
        )

    assert calls == []


def test_execution_audits_broker_failure_without_recording_submitted_order(tmp_path):
    gateway = ZerodhaGateway(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        submit_order=lambda request: (_ for _ in ()).throw(RuntimeError("broker unavailable")),
    )
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    state_store = InternalTradingStateStore(tmp_path / "state.json")
    state_store.save(InternalTradingSnapshot(Decimal("5000"), (), (), datetime.now(timezone.utc)))
    engine = ExecutionEngine(
        gateway=gateway,
        audit=audit,
        state_transitions=InternalTradingStateTransitions(store=state_store),
    )

    with pytest.raises(RuntimeError, match="broker unavailable"):
        engine.submit(
            OrderIntent(symbol="INFY", direction=Direction.LONG, quantity=1, price=Decimal("100")),
            mode=Mode.LIVE,
            risk_approved=True,
            live_enabled=True,
        )

    assert engine.real_orders_submitted == []
    assert audit.read_all()[-1].event_type == "live_order_submission_failed"


def test_execution_fails_closed_when_broker_accepts_but_state_persistence_fails(tmp_path):
    gateway = ZerodhaGateway(
        secret_config=SecretConfig("key", "secret", "token"),
        submit_order=lambda request: BrokerOrderResponse("kite-1", "OPEN", {}),
    )
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")

    class FailedTransitions:
        def record_order_submitted(self, **kwargs):
            raise OSError("disk full")

    engine = ExecutionEngine(gateway=gateway, audit=audit, state_transitions=FailedTransitions())

    with pytest.raises(RuntimeError, match="durable state update failed"):
        engine.submit(
            OrderIntent("INFY", Direction.LONG, 1, Decimal("100")),
            mode=Mode.LIVE,
            risk_approved=True,
            live_enabled=True,
        )

    assert engine.real_orders_submitted == []
    event = audit.read_all()[-1]
    assert event.event_type == "live_order_state_uncertain"
    assert event.payload["must_stop_trading"] is True


def test_audit_logger_redacts_sensitive_fields():
    logger = AuditLogger()

    event = logger.record(
        event_type="broker_response",
        payload={
            "symbol": "TCS",
            "zerodha_access_token": "secret-token",
            "api_key": "secret-key",
            "status": "rejected",
        },
    )

    assert event.payload["zerodha_access_token"] == "[REDACTED]"
    assert event.payload["api_key"] == "[REDACTED]"
    assert event.payload["status"] == "rejected"
