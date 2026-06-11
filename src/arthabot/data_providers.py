from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from arthabot.backtest import Candle, HistoricalDataset
from arthabot.news import NewsArticle, NewsQueryBuilder
from arthabot.secrets import SecretConfig


@dataclass(frozen=True)
class HistoricalProviderRequest:
    symbol: str
    resolution: str
    from_time: datetime | None = None
    to_time: datetime | None = None


@dataclass(frozen=True)
class NewsProviderRequest:
    symbol: str


class HistoricalDataProvider:
    def __init__(self, *, client: Callable[[HistoricalProviderRequest], list[dict[str, Any]]] | None) -> None:
        self.client = client

    def fetch(self, request: HistoricalProviderRequest) -> HistoricalDataset:
        if self.client is None:
            raise NotImplementedError("historical data client must be injected explicitly")
        rows = self.client(request)
        candles = [
            Candle(
                timestamp=datetime.fromisoformat(str(row["timestamp"])),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=int(row["volume"]),
            )
            for row in rows
        ]
        return HistoricalDataset(symbol=request.symbol, resolution=request.resolution, candles=candles)


class HistoricalRangeChunker:
    def __init__(self, *, max_days_by_resolution: dict[str, int]) -> None:
        self.max_days_by_resolution = dict(max_days_by_resolution)

    def split(
        self,
        *,
        resolution: str,
        from_time: datetime,
        to_time: datetime,
    ) -> list[tuple[datetime, datetime]]:
        if to_time <= from_time:
            raise ValueError("historical date range must have to_time after from_time")
        max_days = self.max_days_by_resolution.get(resolution)
        if max_days is None:
            return [(from_time, to_time)]
        if max_days <= 0:
            raise ValueError("max_days must be positive")

        chunks: list[tuple[datetime, datetime]] = []
        cursor = from_time
        step = timedelta(days=max_days)
        while cursor + step < to_time:
            next_cursor = cursor + step
            chunks.append((cursor, next_cursor))
            cursor = next_cursor
        chunks.append((cursor, to_time))
        return chunks


def build_historical_data_provider(
    *,
    historical_client,
    instrument_tokens: dict[str, int],
    chunker: HistoricalRangeChunker | None = None,
) -> HistoricalDataProvider:
    def fetch_rows(request: HistoricalProviderRequest) -> list[dict[str, Any]]:
        token = instrument_tokens.get(request.symbol)
        if token is None:
            raise KeyError(f"missing instrument token for {request.symbol}")
        if request.from_time is None or request.to_time is None:
            raise ValueError("historical date range is required")
        if historical_client is None:
            raise NotImplementedError("historical data client must be injected explicitly")
        chunks = (
            chunker.split(resolution=request.resolution, from_time=request.from_time, to_time=request.to_time)
            if chunker is not None
            else [(request.from_time, request.to_time)]
        )
        rows: list[dict[str, Any]] = []
        for chunk_start, chunk_end in chunks:
            rows.extend(
                historical_client.fetch_kite_historical(
                    instrument_token=token,
                    resolution=request.resolution,
                    from_time=chunk_start,
                    to_time=chunk_end,
                )
            )
        return rows

    return HistoricalDataProvider(client=fetch_rows)


class NewsProvider:
    def __init__(
        self,
        *,
        secret_config: SecretConfig,
        client: Callable[[NewsProviderRequest], list[dict[str, Any]]] | None,
        requires_api_key: bool,
    ) -> None:
        self.secret_config = secret_config
        self.client = client
        self.requires_api_key = requires_api_key

    def fetch(self, request: NewsProviderRequest) -> list[NewsArticle]:
        if self.requires_api_key and not self.secret_config.news_api_key:
            raise PermissionError("NEWS_API_KEY is required for this news provider")
        if self.client is None:
            raise NotImplementedError("news client must be injected explicitly")
        rows = self.client(request)
        return [
            NewsArticle(
                symbol=request.symbol,
                headline=str(row["headline"]),
                source=str(row["source"]),
            )
            for row in rows
        ]


def build_news_provider(
    *,
    secret_config: SecretConfig,
    news_client,
    from_time: datetime | None,
    to_time: datetime | None,
    query_builder: NewsQueryBuilder | None = None,
    domains: list[str] | None = None,
) -> NewsProvider:
    def fetch_rows(request: NewsProviderRequest) -> list[dict[str, Any]]:
        if from_time is None or to_time is None:
            raise ValueError("news date window is required")
        if news_client is None:
            raise NotImplementedError("news client must be injected explicitly")
        query = query_builder.query_for(request.symbol) if query_builder is not None else request.symbol
        kwargs: dict[str, Any] = {
            "symbol": query,
            "from_time": from_time,
            "to_time": to_time,
        }
        if domains is not None:
            kwargs["domains"] = domains
        return news_client.fetch_newsapi_everything(**kwargs)

    return NewsProvider(secret_config=secret_config, client=fetch_rows, requires_api_key=True)
