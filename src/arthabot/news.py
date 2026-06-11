from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class NewsArticle:
    symbol: str
    headline: str
    source: str


@dataclass(frozen=True)
class SentimentScore:
    symbol: str
    score: Decimal
    article_count: int
    positive_matches: tuple[str, ...]
    negative_matches: tuple[str, ...]


@dataclass(frozen=True)
class NewsBackoffDecision:
    should_retry: bool
    delay_seconds: int
    must_stop_ingestion: bool
    reason_code: str


class NewsQueryBuilder:
    def __init__(self, *, company_terms: dict[str, list[str]]) -> None:
        self.company_terms = {symbol: list(terms) for symbol, terms in company_terms.items()}

    def query_for(self, symbol: str) -> str:
        terms = [symbol, *self.company_terms.get(symbol, [])]
        if len(terms) == 1:
            return symbol
        formatted_terms = [
            term if term == symbol else f'"{term}"'
            for term in terms
        ]
        return f"({' OR '.join(formatted_terms)})"


class NewsBackoffController:
    def __init__(self, *, base_delay_seconds: int, max_delay_seconds: int, max_failures: int) -> None:
        if base_delay_seconds <= 0:
            raise ValueError("base_delay_seconds must be positive")
        if max_delay_seconds < base_delay_seconds:
            raise ValueError("max_delay_seconds must be at least base_delay_seconds")
        if max_failures <= 0:
            raise ValueError("max_failures must be positive")
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.max_failures = max_failures
        self._failure_count = 0
        self.last_reason_code: str | None = None
        self.last_event_at: datetime | None = None

    def record_failure(self, *, reason_code: str, now: datetime) -> NewsBackoffDecision:
        self._failure_count += 1
        self.last_reason_code = reason_code
        self.last_event_at = now
        if self._failure_count >= self.max_failures:
            return NewsBackoffDecision(
                should_retry=False,
                delay_seconds=0,
                must_stop_ingestion=True,
                reason_code="NEWS_PROVIDER_UNSTABLE",
            )
        delay = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** (self._failure_count - 1)),
        )
        return NewsBackoffDecision(
            should_retry=True,
            delay_seconds=delay,
            must_stop_ingestion=False,
            reason_code=reason_code,
        )

    def record_success(self, *, now: datetime) -> NewsBackoffDecision:
        self._failure_count = 0
        self.last_reason_code = "NEWS_PROVIDER_OK"
        self.last_event_at = now
        return NewsBackoffDecision(
            should_retry=False,
            delay_seconds=0,
            must_stop_ingestion=False,
            reason_code="NEWS_PROVIDER_OK",
        )


class NewsSentimentEngine:
    def __init__(self, *, positive_terms: set[str], negative_terms: set[str]) -> None:
        self.positive_terms = {term.lower() for term in positive_terms}
        self.negative_terms = {term.lower() for term in negative_terms}

    def score(self, symbol: str, articles: list[NewsArticle]) -> SentimentScore:
        relevant = [article for article in articles if article.symbol == symbol]
        positive_matches: set[str] = set()
        negative_matches: set[str] = set()
        for article in relevant:
            words = set(article.headline.lower().replace(",", " ").split())
            positive_matches.update(words & self.positive_terms)
            negative_matches.update(words & self.negative_terms)
        score = Decimal(len(positive_matches) - len(negative_matches))
        return SentimentScore(
            symbol=symbol,
            score=score,
            article_count=len(relevant),
            positive_matches=tuple(sorted(positive_matches)),
            negative_matches=tuple(sorted(negative_matches)),
        )
