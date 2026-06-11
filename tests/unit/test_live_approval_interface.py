from pathlib import Path
import subprocess

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.live_approval_interface import ApprovalInterface, ApprovalPayload


def test_approval_interface_renders_all_required_checklist_fields(tmp_path):
    interface = ApprovalInterface(JsonlAuditStore(tmp_path / "audit.jsonl"))

    text = interface.render_request(strategy_version="v1")

    assert "strategy_version: v1" in text
    assert "human_approval" in text
    assert "no_live_safety_issues" in text
    assert "approved_by" in text


def test_approval_interface_accepts_complete_payload_and_audits(tmp_path):
    interface = ApprovalInterface(JsonlAuditStore(tmp_path / "audit.jsonl"))
    payload = ApprovalPayload(
        strategy_version="v1",
        approved_by="Shivam",
        approved_at="2026-06-10T10:00:00+05:30",
        checklist={
            "backtested": True,
            "three_years_where_available": True,
            "brokerage_and_slippage_included": True,
            "positive_expectancy_after_costs": True,
            "drawdown_within_limit": True,
            "paper_traded_successfully": True,
            "no_execution_bugs": True,
            "no_order_reconciliation_bugs": True,
            "no_risk_rule_violations": True,
            "no_stale_data_issues": True,
            "no_live_safety_issues": True,
            "human_approval": True,
        },
    )

    decision = interface.submit(payload)

    assert decision.approved
    assert interface.workflow.latest_approval("v1") is not None
    assert interface.audit.read_all()[0].event_type == "human_live_approval"


def test_approval_interface_rejects_missing_checklist_key(tmp_path):
    interface = ApprovalInterface(JsonlAuditStore(tmp_path / "audit.jsonl"))
    payload = ApprovalPayload(
        strategy_version="v1",
        approved_by="Shivam",
        approved_at="2026-06-10T10:00:00+05:30",
        checklist={"backtested": True},
    )

    with pytest.raises(ValueError, match="missing checklist fields"):
        interface.submit(payload)


def test_approval_interface_loads_payload_from_json_file(tmp_path):
    path = tmp_path / "approval.json"
    path.write_text(
        """
{
  "strategy_version": "v1",
  "approved_by": "Shivam",
  "approved_at": "2026-06-10T10:00:00+05:30",
  "checklist": {
    "backtested": true,
    "three_years_where_available": true,
    "brokerage_and_slippage_included": true,
    "positive_expectancy_after_costs": true,
    "drawdown_within_limit": true,
    "paper_traded_successfully": true,
    "no_execution_bugs": true,
    "no_order_reconciliation_bugs": true,
    "no_risk_rule_violations": true,
    "no_stale_data_issues": true,
    "no_live_safety_issues": true,
    "human_approval": true
  }
}
""",
        encoding="utf-8",
    )

    payload = ApprovalInterface.load_payload(Path(path))

    assert payload.strategy_version == "v1"
    assert payload.checklist["human_approval"] is True


def test_approval_cli_render_outputs_payload_template():
    result = subprocess.run(
        [".venv/bin/python", "scripts/approve_live.py", "--render", "v1"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "strategy_version: v1" in result.stdout
    assert "human_approval" in result.stdout
