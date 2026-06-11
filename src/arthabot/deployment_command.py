from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from time import sleep as default_sleep

from arthabot.audit_store import JsonlAuditStore
from arthabot.common import Mode
from arthabot.deployment_config import load_deployment_config
from arthabot.deployment_registry import DeploymentRegistryDependencies, build_provider_job_registry
from arthabot.deployment_service import DeploymentSchedulerService
from arthabot.deployment_worker import DeploymentSchedulerWorker
from arthabot.http_clients import NewsHttpClient, Transport, UrllibHttpTransport, ZerodhaHttpClient
from arthabot.instruments import InstrumentTokenCache, InstrumentTokenStore
from arthabot.news import NewsQueryBuilder
from arthabot.news_curation import load_news_curation_config
from arthabot.secrets import SecretConfig


def build_paper_deployment_service(
    *,
    config_dir: str | Path,
    audit_path: str | Path,
    instrument_store_path: str | Path,
    live_feed_supervision: Callable[[datetime], object],
    learning_rerun: Callable[[datetime], object],
    strategy_calibration: Callable[[datetime], object],
    broker_reconciliation: Callable[[datetime], object],
    interval_seconds: int = 60,
    zerodha_transport: Transport | None = None,
    news_transport: Transport | None = None,
    secret_config: SecretConfig | None = None,
    clock: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] = default_sleep,
) -> DeploymentSchedulerService:
    deployment = load_deployment_config(config_dir)
    if deployment.mode != Mode.PAPER:
        raise PermissionError("deployment command only supports PAPER deployment")

    secrets = secret_config or SecretConfig.from_env(require_zerodha=True)
    if not secrets.news_api_key:
        raise ValueError("NEWS_API_KEY is required for provider-backed PAPER deployment")

    zerodha_client = ZerodhaHttpClient(
        secret_config=secrets,
        transport=zerodha_transport
        or UrllibHttpTransport(base_url="https://api.kite.trade", timeout_seconds=3.0),
    )
    news_curation = load_news_curation_config(config_dir)
    news_client = NewsHttpClient(
        secret_config=secrets,
        transport=news_transport
        or UrllibHttpTransport(base_url="https://newsapi.org", timeout_seconds=5.0),
    )
    audit = JsonlAuditStore(audit_path)
    registry = build_provider_job_registry(
        DeploymentRegistryDependencies(
            audit=audit,
            instrument_cache=InstrumentTokenCache(client=lambda exchange: zerodha_client.fetch_instruments(exchange=exchange)),
            instrument_store=InstrumentTokenStore(instrument_store_path),
            secret_config=secrets,
            news_client=news_client,
            live_feed_supervision=live_feed_supervision,
            learning_rerun=learning_rerun,
            strategy_calibration=strategy_calibration,
            broker_reconciliation=broker_reconciliation,
            news_query_builder=NewsQueryBuilder(company_terms=news_curation.company_terms),
            news_curation=news_curation,
        )
    )
    worker = DeploymentSchedulerWorker(
        audit=audit,
        registry=registry,
        job_configs=deployment.scheduler.jobs,
        timezone_name=deployment.scheduler.timezone,
    )
    return DeploymentSchedulerService(
        worker=worker,
        audit=audit,
        interval_seconds=interval_seconds,
        clock=clock or (lambda: datetime.now(timezone.utc)),
        sleep=sleep,
    )
