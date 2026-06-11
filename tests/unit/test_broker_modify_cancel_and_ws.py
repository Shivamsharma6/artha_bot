from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from arthabot.broker_gateway import (
    BrokerCancelRequest,
    BrokerModifyRequest,
    BrokerOrderResponse,
    ZerodhaGateway,
)
from arthabot.common import Direction
from arthabot.audit_store import JsonlAuditStore
from arthabot.live_feed import FeedReconnectController, LiveFeedMonitor, LiveFeedSupervisor, Tick, ZerodhaWebSocketFeedClient
from arthabot.secrets import SecretConfig


def test_gateway_modify_requires_credentials_and_injected_adapter():
    gateway = ZerodhaGateway(secret_config=SecretConfig())

    with pytest.raises(PermissionError, match="credentials"):
        gateway.modify_order(BrokerModifyRequest(order_id="o1", price=Decimal("101"), quantity=1))


def test_gateway_cancel_uses_injected_adapter_without_real_network_call():
    seen: list[BrokerCancelRequest] = []

    def fake_cancel(request: BrokerCancelRequest) -> BrokerOrderResponse:
        seen.append(request)
        return BrokerOrderResponse(order_id=request.order_id, status="CANCELLED", raw={})

    gateway = ZerodhaGateway(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        cancel_order=fake_cancel,
    )

    response = gateway.cancel_order(BrokerCancelRequest(order_id="o1"))

    assert response.status == "CANCELLED"
    assert seen == [BrokerCancelRequest(order_id="o1")]


def test_gateway_modify_rejects_non_positive_quantity():
    gateway = ZerodhaGateway(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        modify_order=lambda request: BrokerOrderResponse(order_id=request.order_id, status="OPEN", raw={}),
    )

    with pytest.raises(ValueError, match="quantity"):
        gateway.modify_order(BrokerModifyRequest(order_id="o1", price=Decimal("101"), quantity=0))


def test_live_feed_monitor_tracks_fresh_ticks_and_flags_stale_feed():
    monitor = LiveFeedMonitor(max_tick_age_seconds=3)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    monitor.record_tick(
        Tick(
            symbol="INFY",
            price=Decimal("1500"),
            volume=100,
            timestamp=now - timedelta(seconds=2),
        )
    )

    assert monitor.is_fresh("INFY", now=now)
    assert not monitor.is_fresh("INFY", now=now + timedelta(seconds=5))
    assert monitor.health("INFY", now=now + timedelta(seconds=5)).reason_code == "STALE_TICK"


class FakeTicker:
    MODE_FULL = "full"

    def __init__(self) -> None:
        self.subscribed_tokens: list[int] = []
        self.mode_calls: list[tuple[str, list[int]]] = []
        self.connected = False
        self.on_ticks = None
        self.on_connect = None

    def subscribe(self, tokens: list[int]) -> None:
        self.subscribed_tokens.extend(tokens)

    def set_mode(self, mode: str, tokens: list[int]) -> None:
        self.mode_calls.append((mode, tokens))

    def connect(self, *, threaded: bool) -> None:
        self.connected = threaded
        if self.on_connect is not None:
            self.on_connect(self, {})


def test_zerodha_websocket_feed_requires_credentials():
    monitor = LiveFeedMonitor(max_tick_age_seconds=3)

    with pytest.raises(PermissionError, match="Zerodha credentials"):
        ZerodhaWebSocketFeedClient(
            secret_config=SecretConfig(),
            monitor=monitor,
            ticker_factory=lambda api_key, access_token: FakeTicker(),
            token_to_symbol={123: "INFY"},
        )


def test_zerodha_websocket_feed_subscribes_and_records_ticks():
    ticker = FakeTicker()
    monitor = LiveFeedMonitor(max_tick_age_seconds=3)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    client = ZerodhaWebSocketFeedClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        monitor=monitor,
        ticker_factory=lambda api_key, access_token: ticker,
        token_to_symbol={123: "INFY"},
    )

    client.connect(tokens=[123])
    ticker.on_ticks(
        ticker,
        [
            {
                "instrument_token": 123,
                "last_price": "1500.50",
                "volume_traded": 2000,
                "exchange_timestamp": now,
            }
        ],
    )

    assert ticker.connected
    assert ticker.subscribed_tokens == [123]
    assert ticker.mode_calls == [("full", [123])]
    assert monitor.latest_tick("INFY") == Tick(
        symbol="INFY",
        price=Decimal("1500.50"),
        volume=2000,
        timestamp=now,
    )


def test_zerodha_websocket_feed_rejects_unmapped_tick_token():
    ticker = FakeTicker()
    monitor = LiveFeedMonitor(max_tick_age_seconds=3)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    client = ZerodhaWebSocketFeedClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        monitor=monitor,
        ticker_factory=lambda api_key, access_token: ticker,
        token_to_symbol={},
    )

    client.connect(tokens=[123])

    with pytest.raises(KeyError, match="unmapped instrument token"):
        ticker.on_ticks(
            ticker,
            [{"instrument_token": 123, "last_price": "1500.50", "volume_traded": 2000, "exchange_timestamp": now}],
        )


def test_feed_reconnect_controller_schedules_bounded_backoff_after_disconnects():
    controller = FeedReconnectController(base_delay_seconds=1, max_delay_seconds=10, max_failures=5)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    first = controller.record_disconnect(reason_code="SOCKET_CLOSED", now=now)
    second = controller.record_disconnect(reason_code="SOCKET_CLOSED", now=now)
    fourth = controller.record_disconnect(reason_code="SOCKET_CLOSED", now=now)
    fifth = controller.record_disconnect(reason_code="SOCKET_CLOSED", now=now)

    assert first.should_reconnect
    assert first.delay_seconds == 1
    assert second.delay_seconds == 2
    assert fourth.delay_seconds == 4
    assert fifth.delay_seconds == 8
    assert not fifth.must_stop_trading


def test_feed_reconnect_controller_fails_closed_after_too_many_disconnects():
    controller = FeedReconnectController(base_delay_seconds=1, max_delay_seconds=10, max_failures=2)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    controller.record_disconnect(reason_code="SOCKET_CLOSED", now=now)
    decision = controller.record_disconnect(reason_code="SOCKET_CLOSED", now=now)

    assert not decision.should_reconnect
    assert decision.must_stop_trading
    assert decision.reason_code == "LIVE_FEED_UNSTABLE"


def test_feed_reconnect_controller_resets_after_successful_connection():
    controller = FeedReconnectController(base_delay_seconds=1, max_delay_seconds=10, max_failures=2)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    controller.record_disconnect(reason_code="SOCKET_CLOSED", now=now)
    controller.record_success(now=now)
    decision = controller.record_disconnect(reason_code="SOCKET_CLOSED", now=now)

    assert decision.should_reconnect
    assert decision.delay_seconds == 1
    assert not decision.must_stop_trading


class FakeFeedClient:
    def __init__(self) -> None:
        self.connect_calls: list[list[int]] = []
        self.fail_on_connect = False

    def connect(self, *, tokens: list[int], threaded: bool = True) -> None:
        self.connect_calls.append(tokens)
        if self.fail_on_connect:
            raise RuntimeError("socket down")


def test_live_feed_supervisor_connects_feed_and_audits_success(tmp_path):
    feed = FakeFeedClient()
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    supervisor = LiveFeedSupervisor(
        feed_client=feed,
        reconnect_controller=FeedReconnectController(base_delay_seconds=1, max_delay_seconds=10, max_failures=2),
        audit=audit,
    )
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    decision = supervisor.connect(tokens=[123], now=now)

    assert feed.connect_calls == [[123]]
    assert not decision.must_stop_trading
    assert decision.reason_code == "LIVE_FEED_CONNECTED"
    assert audit.read_all()[0].event_type == "live_feed_connected"


def test_live_feed_supervisor_audits_reconnect_decision_after_disconnect(tmp_path):
    feed = FakeFeedClient()
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    supervisor = LiveFeedSupervisor(
        feed_client=feed,
        reconnect_controller=FeedReconnectController(base_delay_seconds=2, max_delay_seconds=10, max_failures=3),
        audit=audit,
    )
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    decision = supervisor.on_disconnect(reason_code="SOCKET_CLOSED", now=now)

    assert decision.should_reconnect
    assert decision.delay_seconds == 2
    assert audit.read_all()[0].event_type == "live_feed_reconnect_scheduled"


def test_live_feed_supervisor_fails_closed_when_reconnect_budget_exhausted(tmp_path):
    feed = FakeFeedClient()
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    supervisor = LiveFeedSupervisor(
        feed_client=feed,
        reconnect_controller=FeedReconnectController(base_delay_seconds=1, max_delay_seconds=10, max_failures=2),
        audit=audit,
    )
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    supervisor.on_disconnect(reason_code="SOCKET_CLOSED", now=now)
    decision = supervisor.on_disconnect(reason_code="SOCKET_CLOSED", now=now)

    assert decision.must_stop_trading
    assert decision.reason_code == "LIVE_FEED_UNSTABLE"
    assert audit.read_all()[-1].event_type == "live_feed_failed_closed"
