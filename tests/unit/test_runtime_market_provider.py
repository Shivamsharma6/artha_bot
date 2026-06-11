from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.market_eligibility import (
    MarketEligibilityError,
    MarketEligibilityGuard,
    load_market_eligibility_config,
)
from arthabot.runtime_market_provider import (
    RuntimeMarketSnapshotProvider,
    RuntimeStrategyCandidateComposer,
    build_guarded_runtime_candidate_composer,
)
from arthabot.runtime_strategy_provider import load_runtime_strategy_config


def test_runtime_market_snapshot_provider_normalizes_top_mover_rows_and_checks_freshness():
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    seen_limit = []

    def client(*, limit):
        seen_limit.append(limit)
        return [
            {
                "symbol": "INFY",
                "last_price": "102",
                "open_price": "100",
                "volume": "20000",
                "timestamp": now.isoformat(),
            }
        ]

    snapshots = RuntimeMarketSnapshotProvider(
        top_movers_client=client,
        max_age_seconds=3,
    ).fetch_top_movers(limit=20, now=now)

    assert seen_limit == [20]
    assert snapshots[0].symbol == "INFY"
    assert snapshots[0].last_price == Decimal("102")
    assert snapshots[0].open_price == Decimal("100")


def test_runtime_market_snapshot_provider_rejects_stale_top_mover_rows():
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="stale top-mover snapshot"):
        RuntimeMarketSnapshotProvider(
            top_movers_client=lambda *, limit: [
                {
                    "symbol": "INFY",
                    "last_price": "102",
                    "open_price": "100",
                    "volume": "20000",
                    "timestamp": (now - timedelta(seconds=10)).isoformat(),
                }
            ],
            max_age_seconds=3,
        ).fetch_top_movers(limit=10, now=now)


def test_runtime_strategy_candidate_composer_fetches_snapshots_and_generates_candidates():
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    market_provider = RuntimeMarketSnapshotProvider(
        top_movers_client=lambda *, limit: [
            {
                "symbol": "INFY",
                "last_price": "102",
                "open_price": "100",
                "volume": "20000",
                "timestamp": now.isoformat(),
            }
        ],
        max_age_seconds=3,
    )

    candidates = RuntimeStrategyCandidateComposer(
        market_provider=market_provider,
        strategy_config=load_runtime_strategy_config("config/strategy.yaml"),
    ).generate_from_top_movers(limit=10, now=now)

    assert any(candidate.symbol == "INFY" for candidate in candidates)
    assert any(candidate.strategy_version == "momentum-v1" for candidate in candidates)
    assert not hasattr(candidates[0], "order_id")


def test_runtime_market_provider_rejects_closed_market_before_mover_request(tmp_path):
    calls = []
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    guard = MarketEligibilityGuard(
        config=load_market_eligibility_config("config/market.yaml"),
        corporate_action_provider=lambda symbol, trading_date: False,
    )
    provider = RuntimeMarketSnapshotProvider(
        top_movers_client=lambda *, limit: calls.append(limit) or [],
        max_age_seconds=3,
        eligibility_guard=guard,
        audit=audit,
    )

    with pytest.raises(MarketEligibilityError, match="MARKET_WEEKEND"):
        provider.fetch_top_movers(
            limit=10,
            now=datetime(2026, 1, 4, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        )

    assert calls == []
    event = audit.read_all()[-1]
    assert event.event_type == "market_eligibility_rejected"
    assert event.payload["reason_code"] == "MARKET_WEEKEND"
    assert event.payload["symbol"] is None


def test_runtime_market_provider_rejects_symbol_with_active_corporate_action(tmp_path):
    now = datetime(2026, 1, 5, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    guard = MarketEligibilityGuard(
        config=load_market_eligibility_config("config/market.yaml"),
        corporate_action_provider=lambda symbol, trading_date: symbol == "INFY",
    )
    provider = RuntimeMarketSnapshotProvider(
        top_movers_client=lambda *, limit: [
            {
                "symbol": "INFY",
                "last_price": "102",
                "open_price": "100",
                "volume": "20000",
                "timestamp": now.isoformat(),
            }
        ],
        max_age_seconds=3,
        eligibility_guard=guard,
        audit=audit,
    )

    with pytest.raises(MarketEligibilityError, match="CORPORATE_ACTION_ACTIVE"):
        provider.fetch_top_movers(limit=10, now=now)

    event = audit.read_all()[-1]
    assert event.payload["reason_code"] == "CORPORATE_ACTION_ACTIVE"
    assert event.payload["symbol"] == "INFY"


def test_guarded_runtime_candidate_composer_factory_enforces_market_policy(tmp_path):
    calls = []
    composer = build_guarded_runtime_candidate_composer(
        top_movers_client=lambda *, limit: calls.append(limit) or [],
        corporate_action_provider=lambda symbol, trading_date: False,
        max_age_seconds=3,
        market_config_path="config/market.yaml",
        strategy_config_path="config/strategy.yaml",
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    )

    with pytest.raises(MarketEligibilityError, match="MARKET_WEEKEND"):
        composer.generate_from_top_movers(
            limit=10,
            now=datetime(2026, 1, 4, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        )

    assert calls == []
