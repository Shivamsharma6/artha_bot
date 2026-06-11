from datetime import date, datetime, time, timezone

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.instruments import (
    InstrumentTokenCache,
    InstrumentTokenRecord,
    InstrumentTokenStore,
    PreMarketInstrumentRefreshJob,
    PreMarketRefreshPlanner,
)


def test_instrument_token_cache_refreshes_and_indexes_by_exchange_symbol():
    seen = []

    def fake_client(*, exchange: str):
        seen.append(exchange)
        return [
            {
                "instrument_token": "408065",
                "tradingsymbol": "INFY",
                "name": "INFOSYS",
                "instrument_type": "EQ",
                "segment": "NSE",
                "exchange": exchange,
            }
        ]

    cache = InstrumentTokenCache(client=fake_client)

    cache.refresh(exchange="NSE", as_of=date(2026, 1, 5))

    assert seen == ["NSE"]
    assert cache.lookup(exchange="NSE", tradingsymbol="INFY", as_of=date(2026, 1, 5)) == InstrumentTokenRecord(
        instrument_token=408065,
        tradingsymbol="INFY",
        exchange="NSE",
        segment="NSE",
        instrument_type="EQ",
        name="INFOSYS",
        as_of=date(2026, 1, 5),
    )


def test_instrument_token_cache_fails_closed_when_cache_is_stale():
    cache = InstrumentTokenCache(
        client=lambda exchange: [
            {
                "instrument_token": "408065",
                "tradingsymbol": "INFY",
                "name": "INFOSYS",
                "instrument_type": "EQ",
                "segment": "NSE",
                "exchange": exchange,
            }
        ]
    )
    cache.refresh(exchange="NSE", as_of=date(2026, 1, 5))

    with pytest.raises(ValueError, match="instrument token cache is stale"):
        cache.lookup(exchange="NSE", tradingsymbol="INFY", as_of=date(2026, 1, 6))


def test_instrument_token_cache_builds_symbol_token_map_for_historical_provider():
    cache = InstrumentTokenCache(
        client=lambda exchange: [
            {
                "instrument_token": "408065",
                "tradingsymbol": "INFY",
                "name": "INFOSYS",
                "instrument_type": "EQ",
                "segment": "NSE",
                "exchange": exchange,
            },
            {
                "instrument_token": "738561",
                "tradingsymbol": "RELIANCE",
                "name": "RELIANCE INDUSTRIES",
                "instrument_type": "EQ",
                "segment": "NSE",
                "exchange": exchange,
            },
        ]
    )
    cache.refresh(exchange="NSE", as_of=date(2026, 1, 5))

    token_map = cache.as_token_map(exchange="NSE", symbols=["INFY", "RELIANCE"], as_of=date(2026, 1, 5))

    assert token_map == {"INFY": 408065, "RELIANCE": 738561}


def test_instrument_token_cache_rejects_duplicate_exchange_symbol_rows():
    cache = InstrumentTokenCache(
        client=lambda exchange: [
            {
                "instrument_token": "1",
                "tradingsymbol": "INFY",
                "name": "INFOSYS",
                "instrument_type": "EQ",
                "segment": "NSE",
                "exchange": exchange,
            },
            {
                "instrument_token": "2",
                "tradingsymbol": "INFY",
                "name": "INFOSYS",
                "instrument_type": "EQ",
                "segment": "NSE",
                "exchange": exchange,
            },
        ]
    )

    with pytest.raises(ValueError, match="duplicate instrument"):
        cache.refresh(exchange="NSE", as_of=date(2026, 1, 5))


def test_instrument_token_store_persists_and_reloads_records(tmp_path):
    store = InstrumentTokenStore(tmp_path / "instruments.json")
    records = [
        InstrumentTokenRecord(
            instrument_token=408065,
            tradingsymbol="INFY",
            exchange="NSE",
            segment="NSE",
            instrument_type="EQ",
            name="INFOSYS",
            as_of=date(2026, 1, 5),
        )
    ]

    store.save(exchange="NSE", as_of=date(2026, 1, 5), records=records)

    assert store.load(exchange="NSE", as_of=date(2026, 1, 5)) == records


def test_instrument_token_cache_can_load_from_persistent_store(tmp_path):
    store = InstrumentTokenStore(tmp_path / "instruments.json")
    stored_record = InstrumentTokenRecord(
        instrument_token=408065,
        tradingsymbol="INFY",
        exchange="NSE",
        segment="NSE",
        instrument_type="EQ",
        name="INFOSYS",
        as_of=date(2026, 1, 5),
    )
    store.save(exchange="NSE", as_of=date(2026, 1, 5), records=[stored_record])
    cache = InstrumentTokenCache(client=lambda exchange: [])

    cache.load(exchange="NSE", as_of=date(2026, 1, 5), store=store)

    assert cache.lookup(exchange="NSE", tradingsymbol="INFY", as_of=date(2026, 1, 5)) == stored_record


def test_pre_market_refresh_planner_requires_refresh_before_configured_time():
    planner = PreMarketRefreshPlanner(refresh_time=time(8, 30))

    assert planner.should_refresh(exchange="NSE", cached_as_of=None, today=date(2026, 1, 5), now_time=time(8, 15))
    assert planner.should_refresh(
        exchange="NSE",
        cached_as_of=date(2026, 1, 4),
        today=date(2026, 1, 5),
        now_time=time(8, 45),
    )


def test_pre_market_refresh_planner_skips_when_today_cache_is_fresh_after_refresh_time():
    planner = PreMarketRefreshPlanner(refresh_time=time(8, 30))

    assert not planner.should_refresh(
        exchange="NSE",
        cached_as_of=date(2026, 1, 5),
        today=date(2026, 1, 5),
        now_time=time(8, 45),
    )


def test_pre_market_instrument_refresh_job_refreshes_persists_loads_and_audits(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    store = InstrumentTokenStore(tmp_path / "instruments.json")
    cache = InstrumentTokenCache(
        client=lambda exchange: [
            {
                "instrument_token": "408065",
                "tradingsymbol": "INFY",
                "name": "INFOSYS",
                "instrument_type": "EQ",
                "segment": "NSE",
                "exchange": exchange,
            }
        ]
    )
    job = PreMarketInstrumentRefreshJob(
        cache=cache,
        store=store,
        planner=PreMarketRefreshPlanner(refresh_time=time(8, 30)),
        audit=audit,
    )

    result = job.run(
        exchange="NSE",
        today=date(2026, 1, 5),
        now=datetime(2026, 1, 5, 8, 15, tzinfo=timezone.utc),
    )

    assert result.refreshed
    assert not result.must_stop_trading
    assert cache.lookup(exchange="NSE", tradingsymbol="INFY", as_of=date(2026, 1, 5)).instrument_token == 408065
    assert store.load(exchange="NSE", as_of=date(2026, 1, 5))[0].tradingsymbol == "INFY"
    assert audit.read_all()[0].event_type == "instrument_refresh_completed"


def test_pre_market_instrument_refresh_job_skips_when_cache_is_current(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    store = InstrumentTokenStore(tmp_path / "instruments.json")
    record = InstrumentTokenRecord(
        instrument_token=408065,
        tradingsymbol="INFY",
        exchange="NSE",
        segment="NSE",
        instrument_type="EQ",
        name="INFOSYS",
        as_of=date(2026, 1, 5),
    )
    store.save(exchange="NSE", as_of=date(2026, 1, 5), records=[record])
    cache = InstrumentTokenCache(client=lambda exchange: [])
    cache.load(exchange="NSE", as_of=date(2026, 1, 5), store=store)
    job = PreMarketInstrumentRefreshJob(
        cache=cache,
        store=store,
        planner=PreMarketRefreshPlanner(refresh_time=time(8, 30)),
        audit=audit,
    )

    result = job.run(
        exchange="NSE",
        today=date(2026, 1, 5),
        now=datetime(2026, 1, 5, 8, 45, tzinfo=timezone.utc),
    )

    assert not result.refreshed
    assert result.reason_code == "INSTRUMENT_REFRESH_NOT_DUE"
    assert audit.read_all()[0].event_type == "instrument_refresh_skipped"


def test_pre_market_instrument_refresh_job_fails_closed_on_refresh_error(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    cache = InstrumentTokenCache(client=lambda exchange: (_ for _ in ()).throw(RuntimeError("network down")))
    job = PreMarketInstrumentRefreshJob(
        cache=cache,
        store=InstrumentTokenStore(tmp_path / "instruments.json"),
        planner=PreMarketRefreshPlanner(refresh_time=time(8, 30)),
        audit=audit,
    )

    result = job.run(
        exchange="NSE",
        today=date(2026, 1, 5),
        now=datetime(2026, 1, 5, 8, 15, tzinfo=timezone.utc),
    )

    assert not result.refreshed
    assert result.must_stop_trading
    assert result.reason_code == "INSTRUMENT_REFRESH_FAILED"
    assert audit.read_all()[0].event_type == "instrument_refresh_failed"
