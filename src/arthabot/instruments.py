from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
import json
from pathlib import Path
from typing import Any

from arthabot.audit_store import JsonlAuditStore


@dataclass(frozen=True)
class InstrumentTokenRecord:
    instrument_token: int
    tradingsymbol: str
    exchange: str
    segment: str
    instrument_type: str
    name: str
    as_of: date


InstrumentClient = Callable[..., list[dict[str, Any]]]


class InstrumentTokenCache:
    def __init__(self, *, client: InstrumentClient) -> None:
        self.client = client
        self._records: dict[tuple[str, str], InstrumentTokenRecord] = {}
        self._as_of_by_exchange: dict[str, date] = {}

    def refresh(self, *, exchange: str, as_of: date) -> None:
        rows = self.client(exchange=exchange)
        refreshed: dict[tuple[str, str], InstrumentTokenRecord] = {}
        for row in rows:
            row_exchange = str(row["exchange"])
            tradingsymbol = str(row["tradingsymbol"])
            key = (row_exchange, tradingsymbol)
            if key in refreshed:
                raise ValueError(f"duplicate instrument for {row_exchange}:{tradingsymbol}")
            refreshed[key] = InstrumentTokenRecord(
                instrument_token=int(row["instrument_token"]),
                tradingsymbol=tradingsymbol,
                exchange=row_exchange,
                segment=str(row["segment"]),
                instrument_type=str(row["instrument_type"]),
                name=str(row["name"]),
                as_of=as_of,
            )

        self._records = {
            key: record
            for key, record in self._records.items()
            if key[0] != exchange
        }
        self._records.update(refreshed)
        self._as_of_by_exchange[exchange] = as_of

    def load(self, *, exchange: str, as_of: date, store: "InstrumentTokenStore") -> None:
        records = store.load(exchange=exchange, as_of=as_of)
        refreshed = {
            (record.exchange, record.tradingsymbol): record
            for record in records
        }
        self._records = {
            key: record
            for key, record in self._records.items()
            if key[0] != exchange
        }
        self._records.update(refreshed)
        self._as_of_by_exchange[exchange] = as_of

    def lookup(self, *, exchange: str, tradingsymbol: str, as_of: date) -> InstrumentTokenRecord:
        self._require_fresh_exchange(exchange=exchange, as_of=as_of)
        record = self._records.get((exchange, tradingsymbol))
        if record is None:
            raise KeyError(f"missing instrument token for {exchange}:{tradingsymbol}")
        return record

    def as_token_map(self, *, exchange: str, symbols: list[str], as_of: date) -> dict[str, int]:
        return {
            symbol: self.lookup(exchange=exchange, tradingsymbol=symbol, as_of=as_of).instrument_token
            for symbol in symbols
        }

    def _require_fresh_exchange(self, *, exchange: str, as_of: date) -> None:
        cached_as_of = self._as_of_by_exchange.get(exchange)
        if cached_as_of != as_of:
            raise ValueError(f"instrument token cache is stale for {exchange}")


class InstrumentTokenStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def save(self, *, exchange: str, as_of: date, records: list[InstrumentTokenRecord]) -> None:
        payload = self._read_payload()
        key = self._key(exchange=exchange, as_of=as_of)
        payload[key] = [
            {
                "instrument_token": record.instrument_token,
                "tradingsymbol": record.tradingsymbol,
                "exchange": record.exchange,
                "segment": record.segment,
                "instrument_type": record.instrument_type,
                "name": record.name,
                "as_of": record.as_of.isoformat(),
            }
            for record in records
        ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def load(self, *, exchange: str, as_of: date) -> list[InstrumentTokenRecord]:
        payload = self._read_payload()
        key = self._key(exchange=exchange, as_of=as_of)
        rows = payload.get(key)
        if rows is None:
            raise KeyError(f"missing persisted instrument tokens for {exchange} on {as_of.isoformat()}")
        return [
            InstrumentTokenRecord(
                instrument_token=int(row["instrument_token"]),
                tradingsymbol=str(row["tradingsymbol"]),
                exchange=str(row["exchange"]),
                segment=str(row["segment"]),
                instrument_type=str(row["instrument_type"]),
                name=str(row["name"]),
                as_of=date.fromisoformat(str(row["as_of"])),
            )
            for row in rows
        ]

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return dict(json.loads(self.path.read_text(encoding="utf-8")))

    @staticmethod
    def _key(*, exchange: str, as_of: date) -> str:
        return f"{exchange}:{as_of.isoformat()}"


class PreMarketRefreshPlanner:
    def __init__(self, *, refresh_time: time) -> None:
        self.refresh_time = refresh_time

    def should_refresh(
        self,
        *,
        exchange: str,
        cached_as_of: date | None,
        today: date,
        now_time: time,
    ) -> bool:
        if cached_as_of != today:
            return True
        return now_time < self.refresh_time


@dataclass(frozen=True)
class InstrumentRefreshResult:
    refreshed: bool
    must_stop_trading: bool
    reason_code: str


class PreMarketInstrumentRefreshJob:
    def __init__(
        self,
        *,
        cache: InstrumentTokenCache,
        store: InstrumentTokenStore,
        planner: PreMarketRefreshPlanner,
        audit: JsonlAuditStore,
    ) -> None:
        self.cache = cache
        self.store = store
        self.planner = planner
        self.audit = audit

    def run(self, *, exchange: str, today: date, now: datetime) -> InstrumentRefreshResult:
        cached_as_of = self.cache._as_of_by_exchange.get(exchange)
        should_refresh = self.planner.should_refresh(
            exchange=exchange,
            cached_as_of=cached_as_of,
            today=today,
            now_time=now.time(),
        )
        if not should_refresh:
            self.audit.append(
                event_type="instrument_refresh_skipped",
                payload={"exchange": exchange, "as_of": today.isoformat(), "reason_code": "INSTRUMENT_REFRESH_NOT_DUE"},
            )
            return InstrumentRefreshResult(
                refreshed=False,
                must_stop_trading=False,
                reason_code="INSTRUMENT_REFRESH_NOT_DUE",
            )

        try:
            self.cache.refresh(exchange=exchange, as_of=today)
            records = [
                record
                for (record_exchange, _symbol), record in self.cache._records.items()
                if record_exchange == exchange
            ]
            self.store.save(exchange=exchange, as_of=today, records=records)
            self.cache.load(exchange=exchange, as_of=today, store=self.store)
        except Exception as exc:
            self.audit.append(
                event_type="instrument_refresh_failed",
                payload={
                    "exchange": exchange,
                    "as_of": today.isoformat(),
                    "reason_code": "INSTRUMENT_REFRESH_FAILED",
                    "error": str(exc),
                },
            )
            return InstrumentRefreshResult(
                refreshed=False,
                must_stop_trading=True,
                reason_code="INSTRUMENT_REFRESH_FAILED",
            )

        self.audit.append(
            event_type="instrument_refresh_completed",
            payload={"exchange": exchange, "as_of": today.isoformat(), "record_count": len(records)},
        )
        return InstrumentRefreshResult(
            refreshed=True,
            must_stop_trading=False,
            reason_code="INSTRUMENT_REFRESHED",
        )
