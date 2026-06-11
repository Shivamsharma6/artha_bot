from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from arthabot.data_cache import CachedMarketDataStore, HistoricalBar
from arthabot.news import NewsArticle, NewsBackoffController, NewsQueryBuilder, NewsSentimentEngine


def test_market_data_cache_returns_only_fresh_snapshot():
    store = CachedMarketDataStore(max_age_seconds=5)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    store.put_snapshot("INFY", price=Decimal("1500"), volume=1000, timestamp=now - timedelta(seconds=4))

    snapshot = store.get_fresh_snapshot("INFY", now=now)

    assert snapshot.symbol == "INFY"
    assert snapshot.last_price == Decimal("1500")


def test_market_data_cache_blocks_stale_snapshot():
    store = CachedMarketDataStore(max_age_seconds=5)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    store.put_snapshot("INFY", price=Decimal("1500"), volume=1000, timestamp=now - timedelta(seconds=6))

    with pytest.raises(ValueError, match="stale"):
        store.get_fresh_snapshot("INFY", now=now)


def test_historical_cache_marks_resolution_and_period():
    store = CachedMarketDataStore(max_age_seconds=5)
    bar = HistoricalBar(
        symbol="INFY",
        timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.50"),
        volume=1000,
        resolution="1m",
    )

    store.put_historical_bar(bar)
    dataset = store.get_historical_dataset("INFY")

    assert dataset.resolution == "1m"
    assert dataset.candles[0].close == Decimal("100.50")


def test_news_sentiment_engine_scores_positive_negative_and_neutral_terms():
    engine = NewsSentimentEngine(
        positive_terms={"beat", "upgrade"},
        negative_terms={"fraud", "downgrade"},
    )
    articles = [
        NewsArticle(symbol="INFY", headline="Infosys beat estimates", source="test"),
        NewsArticle(symbol="INFY", headline="Analyst downgrade follows margin warning", source="test"),
        NewsArticle(symbol="INFY", headline="Board meeting scheduled", source="test"),
    ]

    result = engine.score("INFY", articles)

    assert result.symbol == "INFY"
    assert result.article_count == 3
    assert result.score == Decimal("0")
    assert "beat" in result.positive_matches
    assert "downgrade" in result.negative_matches


def test_news_query_builder_expands_market_symbol_to_company_terms():
    builder = NewsQueryBuilder(company_terms={"INFY": ["Infosys", "Infosys Ltd"]})

    assert builder.query_for("INFY") == '(INFY OR "Infosys" OR "Infosys Ltd")'


def test_news_query_builder_uses_symbol_when_no_expansion_exists():
    builder = NewsQueryBuilder(company_terms={})

    assert builder.query_for("TCS") == "TCS"


def test_news_backoff_controller_schedules_backoff_for_rate_limit():
    controller = NewsBackoffController(base_delay_seconds=30, max_delay_seconds=300, max_failures=3)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    decision = controller.record_failure(reason_code="rateLimited", now=now)

    assert decision.should_retry
    assert decision.delay_seconds == 30
    assert not decision.must_stop_ingestion
    assert decision.reason_code == "rateLimited"


def test_news_backoff_controller_fails_closed_after_repeated_provider_errors():
    controller = NewsBackoffController(base_delay_seconds=30, max_delay_seconds=300, max_failures=2)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    controller.record_failure(reason_code="rateLimited", now=now)
    decision = controller.record_failure(reason_code="rateLimited", now=now)

    assert not decision.should_retry
    assert decision.must_stop_ingestion
    assert decision.reason_code == "NEWS_PROVIDER_UNSTABLE"


def test_news_backoff_controller_resets_after_success():
    controller = NewsBackoffController(base_delay_seconds=30, max_delay_seconds=300, max_failures=2)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    controller.record_failure(reason_code="rateLimited", now=now)
    controller.record_success(now=now)
    decision = controller.record_failure(reason_code="rateLimited", now=now)

    assert decision.should_retry
    assert decision.delay_seconds == 30
    assert not decision.must_stop_ingestion
