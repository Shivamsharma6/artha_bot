from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from arthabot.audit_store import JsonlAuditStore
from arthabot.http_clients import NewsHttpClient


@dataclass(frozen=True)
class NewsApiSmokeResult:
    ok: bool
    article_count: int


class NewsApiSmokeRunner:
    def __init__(self, *, client: NewsHttpClient, audit: JsonlAuditStore) -> None:
        self.client = client
        self.audit = audit

    def run(
        self,
        *,
        symbol: str,
        from_time: datetime,
        to_time: datetime,
    ) -> NewsApiSmokeResult:
        articles = self.client.fetch_newsapi_everything(
            symbol=symbol,
            from_time=from_time,
            to_time=to_time,
            page_size=1,
        )
        result = NewsApiSmokeResult(ok=True, article_count=len(articles))
        self.audit.append(
            event_type="news_api_smoke_probe_completed",
            payload={
                "provider": "newsapi",
                "ok": result.ok,
                "article_count": result.article_count,
            },
        )
        return result
