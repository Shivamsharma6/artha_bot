from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.broker_gateway import BrokerModifyRequest, BrokerOrderResponse, ZerodhaGateway
from arthabot.common import Direction
from arthabot.live_approval import HumanApprovalRecord, HumanApprovalWorkflow
from arthabot.live_promotion import LivePromotionChecklist, LivePromotionGate
from arthabot.operational_audit import AuditedRuntime
from arthabot.secrets import SecretConfig
from arthabot.stop_workflow import BrokerStopOrderState, BrokerTrailingStopWorkflow, OpenPositionState
from arthabot.trailing_stop import TrailingStopPolicy, TrailingStopState


def test_audited_runtime_records_decision_risk_and_execution_events(tmp_path):
    store = JsonlAuditStore(tmp_path / "audit.jsonl")
    runtime = AuditedRuntime(store)

    runtime.record_decision(symbol="INFY", decision={"confidence": "0.75"})
    runtime.record_risk_rejection(symbol="INFY", reason_code="STALE_MARKET_DATA")
    runtime.record_execution_update(symbol="INFY", order_id="o1", status="REJECTED")

    assert [event.event_type for event in store.read_all()] == [
        "decision",
        "risk_rejection",
        "execution_update",
    ]


def test_broker_trailing_stop_workflow_modifies_after_all_safety_checks(tmp_path):
    modified: list[BrokerModifyRequest] = []

    gateway = ZerodhaGateway(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        modify_order=lambda request: modified.append(request)
        or BrokerOrderResponse(order_id=request.order_id, status="OPEN", raw={}),
    )
    workflow = BrokerTrailingStopWorkflow(
        gateway=gateway,
        policy=TrailingStopPolicy(step=Decimal("1"), cooldown_seconds=30, max_modifications_per_trade=3),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    )
    now = datetime(2026, 1, 5, 10, 1, tzinfo=timezone.utc)

    new_state = workflow.maybe_modify(
        position=OpenPositionState(symbol="INFY", quantity=2, direction=Direction.LONG, open=True),
        stop_order=BrokerStopOrderState(order_id="sl1", status="OPEN", quantity=2),
        trailing=TrailingStopState(
            symbol="INFY",
            direction=Direction.LONG,
            current_stop=Decimal("98"),
            last_reference_price=Decimal("100"),
            last_modified_at=now - timedelta(seconds=31),
            modifications=0,
        ),
        price=Decimal("102"),
        quote_timestamp=now,
        now=now,
    )

    assert new_state is not None
    assert modified == [BrokerModifyRequest(order_id="sl1", price=Decimal("100"), quantity=2)]


def test_broker_trailing_stop_workflow_fails_closed_on_invalid_order_state(tmp_path):
    gateway = ZerodhaGateway(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        modify_order=lambda request: BrokerOrderResponse(order_id=request.order_id, status="OPEN", raw={}),
    )
    workflow = BrokerTrailingStopWorkflow(
        gateway=gateway,
        policy=TrailingStopPolicy(step=Decimal("1"), cooldown_seconds=0, max_modifications_per_trade=3),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    )
    now = datetime(2026, 1, 5, 10, 1, tzinfo=timezone.utc)

    with pytest.raises(RuntimeError, match="order state"):
        workflow.maybe_modify(
            position=OpenPositionState(symbol="INFY", quantity=2, direction=Direction.LONG, open=True),
            stop_order=BrokerStopOrderState(order_id="sl1", status="COMPLETE", quantity=2),
            trailing=TrailingStopState(
                symbol="INFY",
                direction=Direction.LONG,
                current_stop=Decimal("98"),
                last_reference_price=Decimal("100"),
                last_modified_at=now,
                modifications=0,
            ),
            price=Decimal("103"),
            quote_timestamp=now,
            now=now,
        )


def test_human_approval_workflow_requires_matching_strategy_and_approver(tmp_path):
    workflow = HumanApprovalWorkflow(JsonlAuditStore(tmp_path / "audit.jsonl"))
    checklist = LivePromotionChecklist.all_clear()
    record = HumanApprovalRecord(
        strategy_version="v1",
        approved_by="Shivam",
        approved_at="2026-06-10T10:00:00+05:30",
        checklist=checklist,
    )

    decision = workflow.approve(record)

    assert decision.approved
    assert LivePromotionGate().evaluate(record.checklist).approved
    assert workflow.latest_approval("v1") == record


def test_human_approval_workflow_rejects_blank_approver(tmp_path):
    workflow = HumanApprovalWorkflow(JsonlAuditStore(tmp_path / "audit.jsonl"))

    with pytest.raises(ValueError, match="approved_by"):
        workflow.approve(
            HumanApprovalRecord(
                strategy_version="v1",
                approved_by="",
                approved_at="2026-06-10T10:00:00+05:30",
                checklist=LivePromotionChecklist.all_clear(),
            )
        )

