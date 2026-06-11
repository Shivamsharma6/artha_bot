from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.balance_provider import BrokerBalanceProvider, BalanceProviderRequest, build_broker_balance_provider
from arthabot.common import Direction
from arthabot.execution import ExecutionEngine
from arthabot.live_feed import Tick
from arthabot.live_paper_loop import LivePaperLoop, LivePaperSignal
from arthabot.paper_session import PaperTradeIntent
from arthabot.reconciliation import ReconciliationService
from arthabot.secrets import SecretConfig


def test_broker_balance_provider_requires_credentials_for_live_client():
    provider = BrokerBalanceProvider(secret_config=SecretConfig(), client=lambda request: {"available_cash": "5000"})

    with pytest.raises(PermissionError, match="Zerodha credentials"):
        provider.fetch(BalanceProviderRequest())


def test_broker_balance_provider_normalizes_available_cash():
    provider = BrokerBalanceProvider(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        client=lambda request: {"available_cash": "4999.50"},
    )

    snapshot = provider.fetch(BalanceProviderRequest())

    assert snapshot.available_cash == Decimal("4999.50")


def test_live_paper_loop_executes_only_fresh_signal_ticks_and_audits(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    loop = LivePaperLoop(
        trading_date=date(2026, 1, 5),
        starting_capital=Decimal("5000"),
        execution=ExecutionEngine(),
        audit=audit,
        max_tick_age_seconds=3,
    )
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    signal = LivePaperSignal(
        symbol="INFY",
        direction=Direction.LONG,
        quantity=2,
        target_exit_price=Decimal("102"),
        total_costs=Decimal("1"),
    )

    loop.on_tick(Tick(symbol="INFY", price=Decimal("100"), volume=100, timestamp=now))
    result = loop.process_signal(signal, now=now + timedelta(seconds=2))

    assert result is not None
    assert loop.daily_report().summarize()["accepted_trades"] == 1
    assert [event.event_type for event in audit.read_all()] == ["paper_signal_executed"]


def test_live_paper_loop_rejects_stale_tick_as_missed_trade(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    loop = LivePaperLoop(
        trading_date=date(2026, 1, 5),
        starting_capital=Decimal("5000"),
        execution=ExecutionEngine(),
        audit=audit,
        max_tick_age_seconds=3,
    )
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    loop.on_tick(Tick(symbol="INFY", price=Decimal("100"), volume=100, timestamp=now - timedelta(seconds=5)))

    result = loop.process_signal(
        LivePaperSignal(
            symbol="INFY",
            direction=Direction.LONG,
            quantity=2,
            target_exit_price=Decimal("102"),
            total_costs=Decimal("1"),
        ),
        now=now,
    )

    assert result is None
    assert loop.missed_trades == 1
    assert loop.daily_report().summarize()["rejected_trades"] == 1
    assert audit.read_all()[0].payload["reason_code"] == "STALE_TICK"


def test_balance_provider_snapshot_reconciles_with_internal_cash():
    provider = BrokerBalanceProvider(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        client=lambda request: {"available_cash": "5000"},
    )
    snapshot = provider.fetch(BalanceProviderRequest())
    result = ReconciliationService().reconcile(
        account=snapshot,
        internal_cash=Decimal("5000"),
        broker_positions=[],
        internal_positions=[],
    )

    assert result.ok


def test_build_broker_balance_provider_uses_zerodha_http_client_boundary():
    seen: list[BalanceProviderRequest] = []

    class FakeMarginClient:
        def fetch_margin_balance(self, *, segment: str):
            seen.append(BalanceProviderRequest(segment=segment))
            return {"available_cash": "4998.75"}

    provider = build_broker_balance_provider(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        margin_client=FakeMarginClient(),
    )

    snapshot = provider.fetch(BalanceProviderRequest(segment="equity"))

    assert snapshot.available_cash == Decimal("4998.75")
    assert seen == [BalanceProviderRequest(segment="equity")]
