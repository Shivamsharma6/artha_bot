from datetime import datetime, timezone
from decimal import Decimal

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.broker_gateway import BrokerCancelRequest, BrokerOrderRequest, BrokerOrderResponse, ZerodhaGateway
from arthabot.common import Direction
from arthabot.internal_state_store import InternalTradingSnapshot, InternalTradingStateStore, InternalTradingStateTransitions
from arthabot.order_reconciliation import InternalOrderState
from arthabot.reconciliation import InternalPosition
from arthabot.secrets import SecretConfig
from arthabot.square_off import ForcedSquareOffService


def test_square_off_cancels_orders_and_exits_positions(tmp_path):
    store = InternalTradingStateStore(tmp_path / "state.json")
    store.save(
        InternalTradingSnapshot(
            available_cash=Decimal("5000"),
            orders=(InternalOrderState("o1", "INFY", "OPEN", 5),),
            positions=(InternalPosition("INFY", 5, Direction.LONG, Decimal("100")),),
            updated_at=datetime.now(timezone.utc),
        )
    )
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    
    cancels = []
    def mock_cancel(req):
        cancels.append(req.order_id)
        return BrokerOrderResponse(req.order_id, "CANCELLED", {})
        
    submits = []
    def mock_submit(req):
        submits.append(req)
        return BrokerOrderResponse("exit-o2", "OPEN", {})

    gateway = ZerodhaGateway(
        secret_config=SecretConfig(zerodha_api_key="k", zerodha_api_secret="s", zerodha_access_token="t"),
        cancel_order=mock_cancel,
        submit_order=mock_submit,
    )
    
    service = ForcedSquareOffService(
        gateway=gateway,
        state_store=store,
        transitions=InternalTradingStateTransitions(store=store),
        audit=audit,
    )

    result = service.run(now=datetime.now(timezone.utc))

    assert "o1" in result.cancelled_orders
    assert "exit-o2" in result.submitted_orders
    assert len(cancels) == 1
    assert cancels[0] == "o1"
    assert len(submits) == 1
    assert submits[0].symbol == "INFY"
    assert submits[0].direction == Direction.SHORT
    assert submits[0].quantity == 5
    assert submits[0].order_type == "MARKET"

    audit_records = audit.read_all()
    assert any(r.event_type == "forced_square_off_completed" for r in audit_records)
