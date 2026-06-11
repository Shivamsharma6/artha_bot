from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from arthabot.audit_store import JsonlAuditStore
from arthabot.data_providers import NewsProviderRequest, build_news_provider
from arthabot.instruments import (
    InstrumentTokenCache,
    InstrumentTokenStore,
    PreMarketInstrumentRefreshJob,
    PreMarketRefreshPlanner,
)
from arthabot.news import NewsArticle, NewsQueryBuilder
from arthabot.scheduler import ScheduledJob, TimeOfDaySchedule
from arthabot.secrets import SecretConfig


@dataclass(frozen=True)
class RuntimeJobFactory:
    audit: JsonlAuditStore

    def instrument_refresh_job(
        self,
        *,
        name: str,
        cache: InstrumentTokenCache,
        store: InstrumentTokenStore,
        exchange: str,
        run_at: time,
    ) -> ScheduledJob:
        refresh_job = PreMarketInstrumentRefreshJob(
            cache=cache,
            store=store,
            planner=PreMarketRefreshPlanner(refresh_time=run_at),
            audit=self.audit,
        )

        def action(now: datetime):
            return refresh_job.run(exchange=exchange, today=now.date(), now=now)

        return ScheduledJob(
            name=name,
            schedule=TimeOfDaySchedule(run_at=run_at),
            action=action,
            critical=True,
        )

    def news_ingestion_job(
        self,
        *,
        name: str,
        secret_config: SecretConfig,
        news_client,
        symbols: list[str],
        run_at: time,
        from_time: datetime,
        to_time: datetime,
        query_builder: NewsQueryBuilder | None = None,
    ) -> ScheduledJob:
        def action(now: datetime):
            articles: list[NewsArticle] = []
            for symbol in symbols:
                provider = build_news_provider(
                    secret_config=secret_config,
                    news_client=news_client,
                    from_time=from_time,
                    to_time=to_time,
                    query_builder=query_builder,
                )
                articles.extend(provider.fetch(NewsProviderRequest(symbol=symbol)))
            return {
                "article_count": len(articles),
                "symbols": list(symbols),
                "articles": articles,
            }

        return ScheduledJob(
            name=name,
            schedule=TimeOfDaySchedule(run_at=run_at),
            action=action,
            critical=False,
        )
