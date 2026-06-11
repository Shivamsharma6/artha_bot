from datetime import date, datetime, time, timezone

from arthabot.audit_store import JsonlAuditStore
from arthabot.instruments import InstrumentTokenCache, InstrumentTokenStore
from arthabot.news import NewsArticle, NewsQueryBuilder
from arthabot.runtime_jobs import RuntimeJobFactory
from arthabot.scheduler import SchedulerRunner
from arthabot.secrets import SecretConfig


def test_runtime_job_factory_builds_critical_instrument_refresh_job(tmp_path):
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
    factory = RuntimeJobFactory(audit=audit)

    job = factory.instrument_refresh_job(
        name="instrument-refresh-nse",
        cache=cache,
        store=store,
        exchange="NSE",
        run_at=time(8, 30),
    )

    result = SchedulerRunner(audit=audit).run(job, now=datetime(2026, 1, 5, 8, 45, tzinfo=timezone.utc))

    assert job.critical
    assert result.executed
    assert not result.must_stop_trading
    assert cache.lookup(exchange="NSE", tradingsymbol="INFY", as_of=date(2026, 1, 5)).instrument_token == 408065


def test_runtime_job_factory_builds_news_ingestion_job_with_query_builder(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    seen = []

    class FakeNewsClient:
        def fetch_newsapi_everything(self, *, symbol, from_time, to_time):
            seen.append((symbol, from_time, to_time))
            return [{"headline": "Infosys wins deal", "source": "Example"}]

    factory = RuntimeJobFactory(audit=audit)
    job = factory.news_ingestion_job(
        name="news-ingest",
        secret_config=SecretConfig(news_api_key="news-key"),
        news_client=FakeNewsClient(),
        symbols=["INFY"],
        run_at=time(8, 45),
        from_time=datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
        to_time=datetime(2026, 1, 5, 23, 59, tzinfo=timezone.utc),
        query_builder=NewsQueryBuilder(company_terms={"INFY": ["Infosys"]}),
    )

    result = SchedulerRunner(audit=audit).run(job, now=datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))

    assert not job.critical
    assert result.payload["article_count"] == 1
    assert result.payload["symbols"] == ["INFY"]
    assert seen == [('(INFY OR "Infosys")', datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc), datetime(2026, 1, 5, 23, 59, tzinfo=timezone.utc))]


def test_runtime_job_factory_news_job_returns_articles_without_live_trading(tmp_path):
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")

    class FakeNewsClient:
        def fetch_newsapi_everything(self, *, symbol, from_time, to_time):
            return [{"headline": "Infosys upgrade", "source": "Example"}]

    job = RuntimeJobFactory(audit=audit).news_ingestion_job(
        name="news-ingest",
        secret_config=SecretConfig(news_api_key="news-key"),
        news_client=FakeNewsClient(),
        symbols=["INFY"],
        run_at=time(8, 45),
        from_time=datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
        to_time=datetime(2026, 1, 5, 23, 59, tzinfo=timezone.utc),
    )

    result = SchedulerRunner(audit=audit).run(job, now=datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc))

    assert all(isinstance(article, NewsArticle) for article in result.payload["articles"])
    assert result.payload["articles"][0].headline == "Infosys upgrade"
