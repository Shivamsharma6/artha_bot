from decimal import Decimal

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.http_clients import HttpRequest, ZerodhaHttpClient
from arthabot.kite_smoke_tests import KiteSmokeTestRunner
from arthabot.secrets import SecretConfig


def secrets() -> SecretConfig:
    return SecretConfig(
        zerodha_api_key="kite-key",
        zerodha_api_secret="kite-secret",
        zerodha_access_token="kite-token",
    )


def test_kite_smoke_test_runner_checks_balance_reconciliation_boundary(tmp_path):
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return {"data": {"available": {"live_balance": "4998.75"}}}

    result = KiteSmokeTestRunner(
        client=ZerodhaHttpClient(secret_config=secrets(), transport=fake_transport),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    ).run_balance_probe()

    assert result.ok
    assert result.payload["available_cash"] == "4998.75"
    assert seen[0].method == "GET"
    assert seen[0].path == "/user/margins/equity"


def test_kite_smoke_test_runner_refuses_order_probe_without_non_live_approval(tmp_path):
    runner = KiteSmokeTestRunner(
        client=ZerodhaHttpClient(secret_config=secrets(), transport=lambda request: {}),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    )

    with pytest.raises(PermissionError, match="non-live order probe approval"):
        runner.run_order_adapter_probe(symbol="INFY", approved_non_live_order_probe=False)


def test_kite_smoke_test_runner_exercises_order_adapters_only_when_explicitly_approved(tmp_path):
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return {"order_id": "probe-1", "status": "OPEN"}

    result = KiteSmokeTestRunner(
        client=ZerodhaHttpClient(secret_config=secrets(), transport=fake_transport),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    ).run_order_adapter_probe(
        symbol="INFY",
        approved_non_live_order_probe=True,
        price=Decimal("100"),
        quantity=1,
    )

    assert result.ok
    assert [request.method for request in seen] == ["POST", "PUT", "DELETE"]
    assert seen[0].path == "/orders/regular"
    assert seen[0].json["product"] == "MIS"
    assert "Authorization': '[REDACTED]'" in repr(seen[0])
