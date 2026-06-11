from datetime import datetime, time, timezone

from arthabot.audit_store import JsonlAuditStore
from arthabot.deployment_config import DeploymentJobConfig
from arthabot.deployment_command import build_paper_deployment_service
from arthabot.deployment_registry import DeploymentRegistryDependencies, build_provider_job_registry
from arthabot.instruments import InstrumentTokenCache, InstrumentTokenStore
from arthabot.scheduler import SchedulerRunner
from arthabot.secrets import SecretConfig


def test_provider_job_registry_builds_instrument_refresh_and_news_jobs(tmp_path):
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
    seen_news_queries = []

    class FakeNewsClient:
        def fetch_newsapi_everything(self, *, symbol, from_time, to_time):
            seen_news_queries.append((symbol, from_time.date(), to_time.date()))
            return [{"headline": "Infosys wins deal", "source": "Example"}]

    registry = build_provider_job_registry(
        DeploymentRegistryDependencies(
            audit=audit,
            instrument_cache=cache,
            instrument_store=store,
            secret_config=SecretConfig(news_api_key="news-key"),
            news_client=FakeNewsClient(),
            live_feed_supervision=lambda now: {"feed": "ok"},
            learning_rerun=lambda now: {"rerun": "ok"},
        )
    )

    instrument_job = registry.build(
        DeploymentJobConfig(
            name="instrument-refresh-nse",
            type="instrument_refresh",
            enabled=True,
            critical=True,
            run_at="08:30",
        )
    )
    news_job = registry.build(
        DeploymentJobConfig(
            name="news-ingest-core-watchlist",
            type="news_ingestion",
            enabled=True,
            critical=False,
            run_at="08:45",
            symbols=["INFY"],
        )
    )
    now = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)

    instrument_result = SchedulerRunner(audit=audit).run(instrument_job, now=now)
    news_result = SchedulerRunner(audit=audit).run(news_job, now=now)

    assert instrument_job.critical
    assert instrument_result.payload.refreshed
    assert news_result.payload["article_count"] == 1
    assert seen_news_queries == [("INFY", now.date(), now.date())]


def test_provider_job_registry_uses_injected_operational_handlers(tmp_path):
    calls = []
    registry = build_provider_job_registry(
        DeploymentRegistryDependencies(
            audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
            instrument_cache=InstrumentTokenCache(client=lambda exchange: []),
            instrument_store=InstrumentTokenStore(tmp_path / "instruments.json"),
            secret_config=SecretConfig(news_api_key="news-key"),
            news_client=object(),
            live_feed_supervision=lambda now: calls.append(("feed", now.time())),
            learning_rerun=lambda now: calls.append(("learning", now.time())),
            strategy_calibration=lambda now: calls.append(("calibration", now.time())),
        )
    )
    now = datetime(2026, 1, 5, 16, 30, tzinfo=timezone.utc)

    feed_job = registry.build(
        DeploymentJobConfig("feed", "live_feed_supervision", True, True, "09:00")
    )
    learning_job = registry.build(
        DeploymentJobConfig("learning", "learning_rerun", True, False, "16:00")
    )
    calibration_job = registry.build(
        DeploymentJobConfig("calibration", "strategy_calibration", True, False, "16:30")
    )

    SchedulerRunner(audit=JsonlAuditStore(tmp_path / "audit2.jsonl")).run(feed_job, now=now)
    SchedulerRunner(audit=JsonlAuditStore(tmp_path / "audit3.jsonl")).run(learning_job, now=now)
    SchedulerRunner(audit=JsonlAuditStore(tmp_path / "audit4.jsonl")).run(calibration_job, now=now)

    assert feed_job.critical
    assert not learning_job.critical
    assert not calibration_job.critical
    assert calls == [
        ("feed", time(16, 30)),
        ("learning", time(16, 30)),
        ("calibration", time(16, 30)),
    ]


def test_paper_deployment_service_accepts_strategy_calibration_handler(tmp_path):
    calls = []

    class FakeTransport:
        def __call__(self, request):
            if request.path.startswith("/instruments"):
                return (
                    "instrument_token,tradingsymbol,name,instrument_type,segment,exchange\n"
                    "408065,INFY,INFOSYS,EQ,NSE,NSE\n"
                )
            return {"status": "ok", "articles": []}

    service = build_paper_deployment_service(
        config_dir="config",
        audit_path=tmp_path / "audit.jsonl",
        instrument_store_path=tmp_path / "instruments.json",
        live_feed_supervision=lambda now: {"feed": "ok"},
        learning_rerun=lambda now: {"learning": "ok"},
        strategy_calibration=lambda now: calls.append(("calibration", now.time())),
        zerodha_transport=FakeTransport(),
        news_transport=FakeTransport(),
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
            news_api_key="news",
        ),
        clock=lambda: datetime(2026, 1, 5, 17, 0, tzinfo=timezone.utc),
        sleep=lambda seconds: None,
    )

    result = service.run(max_ticks=1)

    assert not result.must_stop_trading
    assert calls == [("calibration", time(17, 0))]
