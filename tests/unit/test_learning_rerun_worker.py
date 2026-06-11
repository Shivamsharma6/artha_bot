from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.backtest import BacktestReport
from arthabot.common import Mode
from arthabot.learning import ProposedChange
from arthabot.learning_operations import BacktestRerunRequest, LearningRerunWorkflow
from arthabot.learning_rerun_worker import LearningRerunSchedulerHandler, LearningRerunWorker


def make_report(net: str) -> BacktestReport:
    return BacktestReport(
        net_profit=Decimal(net),
        gross_profit=Decimal(net),
        total_costs=Decimal("1"),
        win_rate=Decimal("0.5"),
        number_of_trades=4,
        number_of_rejected_trades=1,
        max_drawdown=Decimal("10"),
    )


def change(version: str = "v1") -> ProposedChange:
    return ProposedChange(
        name=f"rerun {version}",
        target=f"backtest.rerun.{version}",
        value=Decimal("1"),
        mode=Mode.PAPER,
    )


def test_learning_rerun_worker_runs_changes_and_audits_summary(tmp_path):
    workflow = LearningRerunWorkflow(
        audit=JsonlAuditStore(tmp_path / "workflow.audit.jsonl"),
        artifact_dir=tmp_path / "artifacts",
        runner=lambda request: make_report("25"),
    )
    audit = JsonlAuditStore(tmp_path / "worker.audit.jsonl")

    result = LearningRerunWorker(
        workflow=workflow,
        audit=audit,
        max_attempts=2,
    ).run([change("v1"), change("v2")])

    assert result.completed == 2
    assert not result.must_stop_trading
    assert audit.read_all()[-1].event_type == "learning_rerun_worker_completed"
    assert audit.read_all()[-1].payload["completed"] == 2


def test_learning_rerun_worker_retries_transient_failures(tmp_path):
    attempts: list[BacktestRerunRequest] = []

    def flaky_runner(request: BacktestRerunRequest) -> BacktestReport:
        attempts.append(request)
        if len(attempts) == 1:
            raise RuntimeError("temporary provider failure")
        return make_report("10")

    workflow = LearningRerunWorkflow(
        audit=JsonlAuditStore(tmp_path / "workflow.audit.jsonl"),
        artifact_dir=tmp_path / "artifacts",
        runner=flaky_runner,
    )

    result = LearningRerunWorker(
        workflow=workflow,
        audit=JsonlAuditStore(tmp_path / "worker.audit.jsonl"),
        max_attempts=2,
    ).run([change("v1")])

    assert result.completed == 1
    assert len(attempts) == 2


def test_learning_rerun_worker_fails_closed_after_max_attempts(tmp_path):
    workflow = LearningRerunWorkflow(
        audit=JsonlAuditStore(tmp_path / "workflow.audit.jsonl"),
        artifact_dir=tmp_path / "artifacts",
        runner=lambda request: (_ for _ in ()).throw(RuntimeError("provider down")),
    )
    audit = JsonlAuditStore(tmp_path / "worker.audit.jsonl")

    result = LearningRerunWorker(
        workflow=workflow,
        audit=audit,
        max_attempts=2,
    ).run([change("v1")])

    assert result.completed == 0
    assert result.failed == 1
    assert result.must_stop_trading
    assert result.reason_code == "LEARNING_RERUN_FAILED"
    assert audit.read_all()[-1].event_type == "learning_rerun_worker_failed"


def test_learning_rerun_scheduler_handler_returns_scheduler_payload(tmp_path):
    workflow = LearningRerunWorkflow(
        audit=JsonlAuditStore(tmp_path / "workflow.audit.jsonl"),
        artifact_dir=tmp_path / "artifacts",
        runner=lambda request: make_report("12"),
    )
    worker = LearningRerunWorker(
        workflow=workflow,
        audit=JsonlAuditStore(tmp_path / "worker.audit.jsonl"),
        max_attempts=1,
    )

    payload = LearningRerunSchedulerHandler(
        worker=worker,
        changes=[change("v1")],
    )(now=None)

    assert payload["reason_code"] == "LEARNING_RERUNS_COMPLETED"
    assert payload["completed"] == 1
    assert payload["must_stop_trading"] is False
