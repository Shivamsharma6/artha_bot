from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from arthabot.common import Direction
from arthabot.data_providers import (
    HistoricalDataProvider,
    HistoricalProviderRequest,
    HistoricalRangeChunker,
    NewsProvider,
    NewsProviderRequest,
    build_historical_data_provider,
    build_news_provider,
)
from arthabot.execution import ExecutionEngine
from arthabot.news import NewsQueryBuilder
from arthabot.paper_replay import ReplaySignal, ReplayPaperRunner
from arthabot.secrets import SecretConfig


def test_historical_provider_requires_injected_client():
    provider = HistoricalDataProvider(client=None)

    with pytest.raises(NotImplementedError, match="historical data client"):
        provider.fetch(HistoricalProviderRequest(symbol="INFY", resolution="1m"))


def test_historical_provider_normalizes_client_rows_to_dataset():
    def fake_client(request: HistoricalProviderRequest):
        return [
            {
                "timestamp": "2026-01-05T10:00:00+00:00",
                "open": "100",
                "high": "101",
                "low": "99",
                "close": "100.50",
                "volume": 1000,
            }
        ]

    provider = HistoricalDataProvider(client=fake_client)

    dataset = provider.fetch(HistoricalProviderRequest(symbol="INFY", resolution="1m"))

    assert dataset.symbol == "INFY"
    assert dataset.resolution == "1m"
    assert dataset.candles[0].close == Decimal("100.50")


def test_build_historical_provider_uses_kite_token_mapping_and_date_range():
    seen = []

    class FakeHistoricalClient:
        def fetch_kite_historical(self, *, instrument_token, resolution, from_time, to_time):
            seen.append((instrument_token, resolution, from_time, to_time))
            return [
                {
                    "timestamp": "2026-01-05T09:15:00+00:00",
                    "open": "100",
                    "high": "101",
                    "low": "99",
                    "close": "100.50",
                    "volume": 1000,
                }
            ]

    from_time = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)
    to_time = datetime(2026, 1, 5, 15, 30, tzinfo=timezone.utc)
    provider = build_historical_data_provider(
        historical_client=FakeHistoricalClient(),
        instrument_tokens={"INFY": 408065},
    )

    dataset = provider.fetch(
        HistoricalProviderRequest(
            symbol="INFY",
            resolution="1m",
            from_time=from_time,
            to_time=to_time,
        )
    )

    assert dataset.candles[0].close == Decimal("100.50")
    assert seen == [(408065, "1m", from_time, to_time)]


def test_build_historical_provider_rejects_missing_symbol_token():
    provider = build_historical_data_provider(historical_client=None, instrument_tokens={})

    with pytest.raises(KeyError, match="missing instrument token"):
        provider.fetch(
            HistoricalProviderRequest(
                symbol="INFY",
                resolution="1m",
                from_time=datetime(2026, 1, 5, 9, 15),
                to_time=datetime(2026, 1, 5, 15, 30),
            )
        )


def test_build_historical_provider_requires_explicit_backtest_date_range():
    provider = build_historical_data_provider(historical_client=None, instrument_tokens={"INFY": 408065})

    with pytest.raises(ValueError, match="historical date range"):
        provider.fetch(HistoricalProviderRequest(symbol="INFY", resolution="1m"))


def test_historical_range_chunker_splits_minute_data_into_vendor_safe_windows():
    chunker = HistoricalRangeChunker(max_days_by_resolution={"1m": 60})
    start = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    end = datetime(2026, 5, 11, 15, 30, tzinfo=timezone.utc)

    chunks = chunker.split(resolution="1m", from_time=start, to_time=end)

    assert chunks == [
        (datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc), datetime(2026, 3, 2, 9, 15, tzinfo=timezone.utc)),
        (datetime(2026, 3, 2, 9, 15, tzinfo=timezone.utc), datetime(2026, 5, 1, 9, 15, tzinfo=timezone.utc)),
        (datetime(2026, 5, 1, 9, 15, tzinfo=timezone.utc), datetime(2026, 5, 11, 15, 30, tzinfo=timezone.utc)),
    ]


def test_build_historical_provider_fetches_long_ranges_in_chunks_and_merges_rows():
    seen = []

    class FakeHistoricalClient:
        def fetch_kite_historical(self, *, instrument_token, resolution, from_time, to_time):
            seen.append((instrument_token, resolution, from_time, to_time))
            return [
                {
                    "timestamp": from_time.isoformat(),
                    "open": "100",
                    "high": "101",
                    "low": "99",
                    "close": "100.50",
                    "volume": 1000,
                }
            ]

    provider = build_historical_data_provider(
        historical_client=FakeHistoricalClient(),
        instrument_tokens={"INFY": 408065},
        chunker=HistoricalRangeChunker(max_days_by_resolution={"1m": 60}),
    )

    dataset = provider.fetch(
        HistoricalProviderRequest(
            symbol="INFY",
            resolution="1m",
            from_time=datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc),
            to_time=datetime(2026, 5, 11, 15, 30, tzinfo=timezone.utc),
        )
    )

    assert len(dataset.candles) == 3
    assert seen[0][2] == datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    assert seen[-1][3] == datetime(2026, 5, 11, 15, 30, tzinfo=timezone.utc)


def test_historical_range_chunker_rejects_invalid_ranges():
    chunker = HistoricalRangeChunker(max_days_by_resolution={"1m": 60})

    with pytest.raises(ValueError, match="historical date range"):
        chunker.split(
            resolution="1m",
            from_time=datetime(2026, 1, 2, 9, 15),
            to_time=datetime(2026, 1, 1, 9, 15),
        )


def test_news_provider_requires_api_key_when_client_declares_live_access():
    provider = NewsProvider(secret_config=SecretConfig(), client=lambda request: [], requires_api_key=True)

    with pytest.raises(PermissionError, match="NEWS_API_KEY"):
        provider.fetch(NewsProviderRequest(symbol="INFY"))


def test_news_provider_normalizes_articles_without_exposing_api_key():
    def fake_news(request: NewsProviderRequest):
        return [
            {"headline": "Infosys upgrade after deal win", "source": "example"},
        ]

    provider = NewsProvider(secret_config=SecretConfig(news_api_key="news-secret"), client=fake_news, requires_api_key=True)

    articles = provider.fetch(NewsProviderRequest(symbol="INFY"))

    assert articles[0].symbol == "INFY"
    assert articles[0].headline == "Infosys upgrade after deal win"


def test_build_news_provider_uses_newsapi_date_window():
    seen = []

    class FakeNewsApiClient:
        def fetch_newsapi_everything(self, *, symbol, from_time, to_time):
            seen.append((symbol, from_time, to_time))
            return [
                {
                    "headline": "Infosys wins large banking deal",
                    "source": "Example Wire",
                    "published_at": "2026-01-05T08:30:00Z",
                }
            ]

    from_time = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    to_time = datetime(2026, 1, 5, 23, 59, tzinfo=timezone.utc)
    provider = build_news_provider(
        secret_config=SecretConfig(news_api_key="news-secret"),
        news_client=FakeNewsApiClient(),
        from_time=from_time,
        to_time=to_time,
    )

    articles = provider.fetch(NewsProviderRequest(symbol="INFY"))

    assert articles[0].headline == "Infosys wins large banking deal"
    assert articles[0].source == "Example Wire"
    assert seen == [("INFY", from_time, to_time)]


def test_build_news_provider_uses_query_builder_for_market_symbol_expansion():
    seen = []

    class FakeNewsApiClient:
        def fetch_newsapi_everything(self, *, symbol, from_time, to_time):
            seen.append(symbol)
            return [{"headline": "Infosys wins deal", "source": "Example Wire"}]

    provider = build_news_provider(
        secret_config=SecretConfig(news_api_key="news-secret"),
        news_client=FakeNewsApiClient(),
        from_time=datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
        to_time=datetime(2026, 1, 5, 23, 59, tzinfo=timezone.utc),
        query_builder=NewsQueryBuilder(company_terms={"INFY": ["Infosys"]}),
    )

    provider.fetch(NewsProviderRequest(symbol="INFY"))

    assert seen == ['(INFY OR "Infosys")']


def test_build_news_provider_requires_explicit_news_date_window():
    provider = build_news_provider(
        secret_config=SecretConfig(news_api_key="news-secret"),
        news_client=None,
        from_time=None,
        to_time=None,
    )

    with pytest.raises(ValueError, match="news date window"):
        provider.fetch(NewsProviderRequest(symbol="INFY"))


def test_replay_paper_runner_executes_valid_signals_and_counts_missed():
    runner = ReplayPaperRunner(
        trading_date=date(2026, 1, 5),
        starting_capital=Decimal("5000"),
        execution=ExecutionEngine(),
    )
    signals = [
        ReplaySignal(
            symbol="INFY",
            direction=Direction.LONG,
            quantity=2,
            entry_price=Decimal("100"),
            exit_price=Decimal("102"),
            total_costs=Decimal("1"),
            timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        ),
        ReplaySignal(
            symbol="TCS",
            direction=Direction.SHORT,
            quantity=0,
            entry_price=Decimal("100"),
            exit_price=Decimal("98"),
            total_costs=Decimal("1"),
            timestamp=datetime(2026, 1, 5, 10, 1, tzinfo=timezone.utc),
        ),
    ]

    result = runner.run(signals)

    assert result.report["accepted_trades"] == 1
    assert result.missed_trades == 1
    assert result.report["net_pnl"] == Decimal("3")
