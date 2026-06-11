import json
from decimal import Decimal

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.common import Mode
from arthabot.learning_report import LearningReport, StrategyObservation
from arthabot.live_promotion import LivePromotionGate
from arthabot.validation import ValidationEvidence, ValidationHarness


def test_jsonl_audit_store_persists_redacted_events(tmp_path):
    path = tmp_path / "audit.jsonl"
    store = JsonlAuditStore(path)

    store.append(
        event_type="order_rejected",
        payload={
            "symbol": "INFY",
            "reason": "STALE_MARKET_DATA",
            "access_token": "secret-token",
        },
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    assert event["event_type"] == "order_rejected"
    assert event["payload"]["access_token"] == "[REDACTED]"
    assert event["payload"]["reason"] == "STALE_MARKET_DATA"


def test_jsonl_audit_store_reads_events_in_order(tmp_path):
    path = tmp_path / "audit.jsonl"
    store = JsonlAuditStore(path)

    store.append(event_type="decision", payload={"symbol": "INFY"})
    store.append(event_type="risk_rejection", payload={"symbol": "TCS"})

    assert [event.event_type for event in store.read_all()] == ["decision", "risk_rejection"]


def test_learning_report_detects_degradation_and_recommends_paper_only_change():
    report = LearningReport(
        strategy_version="bootstrap-v1",
        observations=[
            StrategyObservation(window="open", expectancy=Decimal("0.20"), max_drawdown=Decimal("20")),
            StrategyObservation(window="close", expectancy=Decimal("-0.10"), max_drawdown=Decimal("80")),
        ],
    )

    summary = report.summarize()

    assert summary.strategy_version == "bootstrap-v1"
    assert summary.degraded_windows == ("close",)
    assert summary.proposed_change.mode == Mode.PAPER
    assert summary.proposed_change.target == "strategy.window_weight.close"


def test_learning_report_rejects_live_risk_control_proposal():
    report = LearningReport(strategy_version="bootstrap-v1", observations=[])

    with pytest.raises(PermissionError):
        report.propose_change(name="disable stop loss", target="risk.stop_loss_required", value=False, mode=Mode.LIVE)


def test_validation_harness_builds_live_promotion_checklist_from_evidence():
    evidence = ValidationEvidence(
        backtested=True,
        data_years=Decimal("3.2"),
        brokerage_and_slippage_included=True,
        positive_expectancy_after_costs=True,
        drawdown_within_limit=True,
        paper_traded_successfully=True,
        strategy_calibrated=True,
        unresolved_execution_bugs=0,
        unresolved_order_reconciliation_bugs=0,
        unresolved_risk_rule_violations=0,
        stale_data_issues=0,
        live_safety_issues=0,
        human_approval=True,
    )

    checklist = ValidationHarness().build_live_checklist(evidence)
    decision = LivePromotionGate().evaluate(checklist)

    assert decision.approved


def test_validation_harness_blocks_when_data_depth_or_bugs_are_missing():
    evidence = ValidationEvidence(
        backtested=True,
        data_years=Decimal("1.5"),
        brokerage_and_slippage_included=True,
        positive_expectancy_after_costs=True,
        drawdown_within_limit=True,
        paper_traded_successfully=True,
        strategy_calibrated=True,
        unresolved_execution_bugs=1,
        unresolved_order_reconciliation_bugs=0,
        unresolved_risk_rule_violations=0,
        stale_data_issues=0,
        live_safety_issues=0,
        human_approval=True,
    )

    checklist = ValidationHarness().build_live_checklist(evidence)
    decision = LivePromotionGate().evaluate(checklist)

    assert not decision.approved
    assert "three_years_where_available" in decision.missing
    assert "no_execution_bugs" in decision.missing


def test_validation_harness_blocks_when_strategy_calibration_is_missing():
    evidence = ValidationEvidence(
        backtested=True,
        data_years=Decimal("3.2"),
        brokerage_and_slippage_included=True,
        positive_expectancy_after_costs=True,
        drawdown_within_limit=True,
        paper_traded_successfully=True,
        strategy_calibrated=False,
        unresolved_execution_bugs=0,
        unresolved_order_reconciliation_bugs=0,
        unresolved_risk_rule_violations=0,
        stale_data_issues=0,
        live_safety_issues=0,
        human_approval=True,
    )

    checklist = ValidationHarness().build_live_checklist(evidence)
    decision = LivePromotionGate().evaluate(checklist)

    assert not decision.approved
    assert "no_live_safety_issues" in decision.missing
