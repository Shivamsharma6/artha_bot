from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from arthabot.audit_store import JsonlAuditStore
from arthabot.instruments import InstrumentTokenStore
from arthabot.secrets import SecretConfig


@dataclass(frozen=True)
class Tick:
    symbol: str
    price: Decimal
    volume: int
    timestamp: datetime


@dataclass(frozen=True)
class FeedHealth:
    ok: bool
    reason_code: str


@dataclass(frozen=True)
class ReconnectDecision:
    should_reconnect: bool
    delay_seconds: int
    must_stop_trading: bool
    reason_code: str


class LiveFeedMonitor:
    def __init__(self, *, max_tick_age_seconds: int) -> None:
        self.max_tick_age_seconds = max_tick_age_seconds
        self._ticks: dict[str, Tick] = {}

    def record_tick(self, tick: Tick) -> None:
        if tick.price <= 0:
            raise ValueError("tick price must be positive")
        if tick.volume < 0:
            raise ValueError("tick volume must not be negative")
        self._ticks[tick.symbol] = tick

    def is_fresh(self, symbol: str, *, now: datetime) -> bool:
        return self.health(symbol, now=now).ok

    def latest_tick(self, symbol: str) -> Tick:
        tick = self._ticks.get(symbol)
        if tick is None:
            raise KeyError(f"missing tick for {symbol}")
        return tick

    def health(self, symbol: str, *, now: datetime) -> FeedHealth:
        tick = self._ticks.get(symbol)
        if tick is None:
            return FeedHealth(False, "MISSING_TICK")
        age = (now - tick.timestamp).total_seconds()
        if age < 0:
            return FeedHealth(False, "FUTURE_TICK")
        if age > self.max_tick_age_seconds:
            return FeedHealth(False, "STALE_TICK")
        return FeedHealth(True, "FRESH_TICK")


class FeedReconnectController:
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

    def record_disconnect(self, *, reason_code: str, now: datetime) -> ReconnectDecision:
        self._failure_count += 1
        self.last_reason_code = reason_code
        self.last_event_at = now
        if self._failure_count >= self.max_failures:
            return ReconnectDecision(
                should_reconnect=False,
                delay_seconds=0,
                must_stop_trading=True,
                reason_code="LIVE_FEED_UNSTABLE",
            )
        delay = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** (self._failure_count - 1)),
        )
        return ReconnectDecision(
            should_reconnect=True,
            delay_seconds=delay,
            must_stop_trading=False,
            reason_code=reason_code,
        )

    def record_success(self, *, now: datetime) -> ReconnectDecision:
        self._failure_count = 0
        self.last_reason_code = "LIVE_FEED_CONNECTED"
        self.last_event_at = now
        return ReconnectDecision(
            should_reconnect=False,
            delay_seconds=0,
            must_stop_trading=False,
            reason_code="LIVE_FEED_CONNECTED",
        )


class LiveFeedSupervisor:
    def __init__(
        self,
        *,
        feed_client: Any,
        reconnect_controller: FeedReconnectController,
        audit: JsonlAuditStore,
    ) -> None:
        self.feed_client = feed_client
        self.reconnect_controller = reconnect_controller
        self.audit = audit

    def connect(self, *, tokens: list[int], now: datetime) -> ReconnectDecision:
        try:
            self.feed_client.connect(tokens=tokens)
        except Exception as exc:
            decision = self.reconnect_controller.record_disconnect(reason_code="CONNECT_FAILED", now=now)
            self._audit_decision(decision=decision, event_error=str(exc))
            return decision

        decision = self.reconnect_controller.record_success(now=now)
        self.audit.append(
            event_type="live_feed_connected",
            payload={"reason_code": decision.reason_code, "token_count": len(tokens)},
        )
        return decision

    def on_disconnect(self, *, reason_code: str, now: datetime) -> ReconnectDecision:
        decision = self.reconnect_controller.record_disconnect(reason_code=reason_code, now=now)
        self._audit_decision(decision=decision)
        return decision

    def _audit_decision(self, *, decision: ReconnectDecision, event_error: str | None = None) -> None:
        event_type = "live_feed_failed_closed" if decision.must_stop_trading else "live_feed_reconnect_scheduled"
        payload: dict[str, Any] = {
            "reason_code": decision.reason_code,
            "delay_seconds": decision.delay_seconds,
            "should_reconnect": decision.should_reconnect,
            "must_stop_trading": decision.must_stop_trading,
        }
        if event_error is not None:
            payload["error"] = event_error
        self.audit.append(event_type=event_type, payload=payload)


TickerFactory = Callable[[str, str], Any]


class ZerodhaWebSocketFeedClient:
    def __init__(
        self,
        *,
        secret_config: SecretConfig,
        monitor: LiveFeedMonitor,
        ticker_factory: TickerFactory,
        token_to_symbol: dict[int, str],
        tick_handler: Callable[[Tick], Any] | None = None,
        order_update_handler: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        if not secret_config.has_zerodha_credentials:
            raise PermissionError("Zerodha credentials are required for live feed access")
        self.secret_config = secret_config
        self.monitor = monitor
        self.ticker_factory = ticker_factory
        self.token_to_symbol = dict(token_to_symbol)
        self.tick_handler = tick_handler
        self.order_update_handler = order_update_handler
        self.last_order_update_result: Any | None = None
        self.ticker: Any | None = None

    def connect(self, *, tokens: list[int], threaded: bool = True) -> None:
        if not tokens:
            raise ValueError("at least one instrument token is required")
        ticker = self.ticker_factory(
            self.secret_config.zerodha_api_key or "",
            self.secret_config.zerodha_access_token or "",
        )
        ticker.on_ticks = self._on_ticks
        ticker.on_connect = self._on_connect(tokens)
        if self.order_update_handler is not None:
            ticker.on_order_update = self._on_order_update
        self.ticker = ticker
        ticker.connect(threaded=threaded)

    def disconnect(self) -> None:
        if self.ticker is not None and hasattr(self.ticker, "close"):
            self.ticker.close()

    def _on_connect(self, tokens: list[int]):
        def subscribe(ticker, response) -> None:
            ticker.subscribe(tokens)
            if hasattr(ticker, "set_mode"):
                mode = getattr(ticker, "MODE_FULL", "full")
                ticker.set_mode(mode, tokens)

        return subscribe

    def _on_ticks(self, ticker, ticks: list[dict[str, Any]]) -> None:
        for raw_tick in ticks:
            token = int(raw_tick["instrument_token"])
            symbol = self.token_to_symbol.get(token)
            if symbol is None:
                raise KeyError(f"unmapped instrument token: {token}")
            timestamp = raw_tick.get("exchange_timestamp") or raw_tick.get("timestamp")
            if not isinstance(timestamp, datetime):
                raise ValueError("tick timestamp is required")
            volume = raw_tick.get("volume_traded", raw_tick.get("volume"))
            if volume is None:
                raise ValueError("tick volume is required")
            tick = Tick(
                symbol=symbol,
                price=Decimal(str(raw_tick["last_price"])),
                volume=int(volume),
                timestamp=timestamp,
            )
            if self.tick_handler is None:
                self.monitor.record_tick(tick)
            else:
                self.tick_handler(tick)

    def _on_order_update(self, ticker, update: dict[str, Any]) -> None:
        if self.order_update_handler is None:
            return
        self.last_order_update_result = self.order_update_handler(update)


class ZerodhaLiveFeedSchedulerHandler:
    def __init__(
        self,
        *,
        secret_config: SecretConfig,
        instrument_store: InstrumentTokenStore,
        symbols: tuple[str, ...],
        audit: JsonlAuditStore,
        ticker_factory: TickerFactory,
        market_timezone: str,
        exchange: str = "NSE",
        max_tick_age_seconds: int = 3,
        order_update_handler: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        if not symbols:
            raise ValueError("at least one live-feed symbol is required")
        self.secret_config = secret_config
        self.instrument_store = instrument_store
        self.symbols = symbols
        self.audit = audit
        self.ticker_factory = ticker_factory
        self.market_timezone = ZoneInfo(market_timezone)
        self.exchange = exchange
        self.monitor = LiveFeedMonitor(max_tick_age_seconds=max_tick_age_seconds)
        self.order_update_handler = order_update_handler
        self.client: ZerodhaWebSocketFeedClient | None = None
        self.supervisor: LiveFeedSupervisor | None = None

    def __call__(self, now: datetime) -> dict[str, Any]:
        market_now = now.astimezone(self.market_timezone)
        records = self.instrument_store.load(exchange=self.exchange, as_of=market_now.date())
        records_by_symbol = {record.tradingsymbol: record for record in records}
        missing = next((symbol for symbol in self.symbols if symbol not in records_by_symbol), None)
        if missing is not None:
            raise KeyError(f"missing instrument token for {self.exchange}:{missing}")
        token_to_symbol = {
            records_by_symbol[symbol].instrument_token: symbol
            for symbol in self.symbols
        }
        self.client = ZerodhaWebSocketFeedClient(
            secret_config=self.secret_config,
            monitor=self.monitor,
            ticker_factory=self.ticker_factory,
            token_to_symbol=token_to_symbol,
            order_update_handler=self.order_update_handler,
        )
        self.supervisor = LiveFeedSupervisor(
            feed_client=self.client,
            reconnect_controller=FeedReconnectController(
                base_delay_seconds=1,
                max_delay_seconds=30,
                max_failures=3,
            ),
            audit=self.audit,
        )
        decision = self.supervisor.connect(tokens=list(token_to_symbol), now=market_now)
        return {
            "reason_code": decision.reason_code,
            "must_stop_trading": decision.must_stop_trading,
            "should_reconnect": decision.should_reconnect,
            "delay_seconds": decision.delay_seconds,
            "symbols": list(self.symbols),
            "timestamp": market_now.isoformat(),
        }
