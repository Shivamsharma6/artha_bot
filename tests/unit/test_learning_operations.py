import json
from decimal import Decimal

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.backtest import BacktestReport
from arthabot.common import Mode
from arthabot.learning import ProposedChange
from arthabot.learning_operations import BacktestRerunRequest, LearningRerunWorkflow


def make_report(net: str) -> BacktestReport:
    return BacktestReport(
        net_profit=Decimal(net),
        gross_profit=Decimal(net),
        total_costs=Decimal("0"),
        win_rate=Decimal("0.5"),
        number_of_trades=4,
        number_of_rejected_trades=1,
        max_drawdown=Decimal("10"),
    )


def test_learning_rerun_workflow_runs_injected_backtest_and_stores_artifact(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    seen: list[BacktestRerunRequest] = []

    def fake_runner(request: BacktestRerunRequest) -> BacktestReport:
        seen.append(request)
        return make_report("25")

    workflow = LearningRerunWorkflow(audit=audit, artifact_dir=tmp_path / "artifacts", runner=fake_runner)
    result = workflow.run(
        ProposedChange(
            name="rerun v1",
            target="backtest.rerun.v1",
            value=Decimal("1"),
            mode=Mode.PAPER,
        )
    )

    assert seen == [BacktestRerunRequest(strategy_version="v1")]
    assert result.report.net_profit == Decimal("25")
    assert result.artifact_path.exists()
    artifact = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert artifact["strategy_version"] == "v1"
    assert artifact["net_profit"] == "25"
    assert audit.read_all()[0].event_type == "learning_backtest_rerun"


def test_learning_rerun_workflow_rejects_live_mode_change(tmp_path):
    workflow = LearningRerunWorkflow(
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
        artifact_dir=tmp_path / "artifacts",
        runner=lambda request: make_report("1"),
    )

    with pytest.raises(PermissionError):
        workflow.run(
            ProposedChange(
                name="live rerun",
                target="backtest.rerun.v1",
                value=Decimal("1"),
                mode=Mode.LIVE,
            )
        )


def test_learning_rerun_workflow_rejects_non_rerun_target(tmp_path):
    workflow = LearningRerunWorkflow(
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
        artifact_dir=tmp_path / "artifacts",
        runner=lambda request: make_report("1"),
    )

    with pytest.raises(ValueError, match="backtest.rerun"):
        workflow.run(
            ProposedChange(
                name="change close weight",
                target="strategy.window_weight.close",
                value=Decimal("0.5"),
                mode=Mode.PAPER,
            )
        )

