from decimal import Decimal

import pytest

from arthabot.common import Direction, Mode
from arthabot.execution import ExecutionEngine, OrderIntent
from arthabot.observability import AuditLogger


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

