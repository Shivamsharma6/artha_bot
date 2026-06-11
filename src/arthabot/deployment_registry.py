from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time

from arthabot.audit_store import JsonlAuditStore
from arthabot.data_providers import NewsProviderRequest, build_news_provider
from arthabot.deployment_config import DeploymentJobConfig
from arthabot.deployment_worker import DeploymentJobRegistry
from arthabot.instruments import InstrumentTokenCache, InstrumentTokenStore
from arthabot.news import NewsArticle, NewsQueryBuilder
from arthabot.news_curation import NewsCurationConfig
from arthabot.runtime_jobs import RuntimeJobFactory
from arthabot.scheduler import ScheduledJob, TimeOfDaySchedule
from arthabot.secrets import SecretConfig


OperationalHandler = Callable[[datetime], object]


@dataclass(frozen=True)
class DeploymentRegistryDependencies:
    audit: JsonlAuditStore
    instrument_cache: InstrumentTokenCache
    instrument_store: InstrumentTokenStore
    secret_config: SecretConfig
    news_client: object
    live_feed_supervision: OperationalHandler
    learning_rerun: OperationalHandler
    strategy_calibration: OperationalHandler | None = None
    broker_reconciliation: OperationalHandler | None = None
    forced_square_off: OperationalHandler | None = None
    exchange: str = "NSE"
    news_query_builder: NewsQueryBuilder | None = None
    news_curation: NewsCurationConfig | None = None


def build_provider_job_registry(dependencies: DeploymentRegistryDependencies) -> DeploymentJobRegistry:
    runtime_factory = RuntimeJobFactory(audit=dependencies.audit)
    return DeploymentJobRegistry(
        factories={
            "instrument_refresh": lambda config: runtime_factory.instrument_refresh_job(
                name=config.name,
                cache=dependencies.instrument_cache,
                store=dependencies.instrument_store,
                exchange=dependencies.exchange,
                run_at=_parse_run_at(config.run_at),
            ),
            "news_ingestion": lambda config: _build_news_job(config, dependencies),
            "live_feed_supervision": lambda config: _build_handler_job(
                config=config,
                handler=dependencies.live_feed_supervision,
            ),
            "learning_rerun": lambda config: _build_handler_job(
                config=config,
                handler=dependencies.learning_rerun,
            ),
            "strategy_calibration": lambda config: _build_handler_job(
                config=config,
                handler=_require_handler(
                    dependencies.strategy_calibration,
                    "strategy_calibration",
                ),
            ),
            "broker_reconciliation": lambda config: _build_handler_job(
                config=config,
                handler=_require_handler(dependencies.broker_reconciliation, "broker_reconciliation"),
            ),
            "forced_square_off": lambda config: _build_handler_job(
                config=config,
                handler=_require_handler(dependencies.forced_square_off, "forced_square_off"),
            ),
        }
    )


def _build_news_job(config: DeploymentJobConfig, dependencies: DeploymentRegistryDependencies) -> ScheduledJob:
    def action(now: datetime):
        articles: list[NewsArticle] = []
        from_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        to_time = now.replace(hour=23, minute=59, second=59, microsecond=0)
        for symbol in config.symbols:
            provider = build_news_provider(
                secret_config=dependencies.secret_config,
                news_client=dependencies.news_client,
                from_time=from_time,
                to_time=to_time,
                query_builder=dependencies.news_query_builder,
                domains=dependencies.news_curation.newsapi_domains if dependencies.news_curation else None,
            )
            articles.extend(provider.fetch(NewsProviderRequest(symbol=symbol)))
        return {
            "article_count": len(articles),
            "symbols": list(config.symbols),
            "articles": articles,
        }

    return ScheduledJob(
        name=config.name,
        schedule=TimeOfDaySchedule.from_string(config.run_at),
        action=action,
        critical=config.critical,
    )


def _build_handler_job(*, config: DeploymentJobConfig, handler: OperationalHandler) -> ScheduledJob:
    return ScheduledJob(
        name=config.name,
        schedule=TimeOfDaySchedule.from_string(config.run_at),
        action=handler,
        critical=config.critical,
    )


def _parse_run_at(value: str) -> time:
    return TimeOfDaySchedule.from_string(value).run_at


def _require_handler(handler: OperationalHandler | None, job_type: str) -> OperationalHandler:
    if handler is None:
        raise ValueError(f"{job_type} handler must be configured explicitly")
    return handler
