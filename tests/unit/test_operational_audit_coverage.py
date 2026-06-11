from arthabot.audit_store import JsonlAuditStore
from arthabot.operational_audit_coverage import (
    OperationalAuditCoverageChecker,
    REQUIRED_RUNTIME_AUDIT_EVENTS,
)


def test_operational_audit_coverage_checker_accepts_required_runtime_events(tmp_path):
    store = JsonlAuditStore(tmp_path / "audit.jsonl")
    for event_type in REQUIRED_RUNTIME_AUDIT_EVENTS:
        store.append(event_type=event_type, payload={"ok": True})

    result = OperationalAuditCoverageChecker(
        required_events=REQUIRED_RUNTIME_AUDIT_EVENTS,
    ).evaluate(store.read_all())

    assert result.ok
    assert result.missing_event_types == ()
    assert result.reason_code == "AUDIT_COVERAGE_OK"


def test_operational_audit_coverage_checker_reports_missing_runtime_events(tmp_path):
    store = JsonlAuditStore(tmp_path / "audit.jsonl")
    store.append(event_type="decision", payload={"symbol": "INFY"})

    result = OperationalAuditCoverageChecker(
        required_events=("decision", "risk_rejection", "paper_signal_executed"),
    ).evaluate(store.read_all())

    assert not result.ok
    assert result.missing_event_types == ("paper_signal_executed", "risk_rejection")
    assert result.reason_code == "AUDIT_COVERAGE_MISSING_EVENTS"


def test_operational_audit_coverage_checker_reads_jsonl_store(tmp_path):
    store = JsonlAuditStore(tmp_path / "audit.jsonl")
    store.append(event_type="deployment_scheduler_service_completed", payload={})

    result = OperationalAuditCoverageChecker(
        required_events=("deployment_scheduler_service_completed",),
    ).evaluate_store(store)

    assert result.ok
