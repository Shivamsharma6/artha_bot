from arthabot.audit_store import JsonlAuditStore
from arthabot.operational_audit_coverage import REQUIRED_RUNTIME_AUDIT_EVENTS
from arthabot.operational_audit_coverage_cli import main


def test_operational_audit_coverage_cli_returns_zero_when_coverage_is_complete(tmp_path):
    store = JsonlAuditStore(tmp_path / "audit.jsonl")
    for event_type in REQUIRED_RUNTIME_AUDIT_EVENTS:
        store.append(event_type=event_type, payload={})

    assert main(["--audit-path", str(store.path)]) == 0


def test_operational_audit_coverage_cli_returns_one_when_coverage_is_missing(tmp_path):
    store = JsonlAuditStore(tmp_path / "audit.jsonl")
    store.append(event_type="decision", payload={})

    assert main(["--audit-path", str(store.path)]) == 1
