from datetime import datetime, timezone
from decimal import Decimal

import pytest

from arthabot.broker_gateway import BrokerCancelRequest, BrokerModifyRequest, BrokerOrderRequest
from arthabot.common import Direction
from arthabot.http_clients import (
    HistoricalHttpClient,
    HttpRequest,
    NewsHttpClient,
    UrllibHttpTransport,
    ZerodhaHttpClient,
    KiteAuthenticationError,
    build_historical_http_client,
    build_news_http_client,
    build_zerodha_http_client,
    build_zerodha_gateway,
)
from arthabot.broker_gateway import ZerodhaGateway
from arthabot.secrets import SecretConfig


def test_zerodha_http_client_requires_credentials():
    client = ZerodhaHttpClient(secret_config=SecretConfig(), transport=lambda request: {})

    with pytest.raises(PermissionError, match="Zerodha credentials"):
        client.place_order(BrokerOrderRequest(symbol="INFY", direction=Direction.LONG, quantity=1, price=Decimal("100")))


def test_zerodha_quote_failure_classifies_expired_session_for_reauthentication():
    def expired_transport(request):
        raise RuntimeError("HTTP 403 TokenException: Invalid session credentials")

    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key", zerodha_api_secret="secret", zerodha_access_token="expired"
        ),
        transport=expired_transport,
    )

    with pytest.raises(KiteAuthenticationError, match="KITE_REAUTH_REQUIRED"):
        client.fetch_quotes(["NSE:INFY"])


def test_zerodha_balance_failure_classifies_expired_session_for_reauthentication():
    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key", zerodha_api_secret="secret", zerodha_access_token="expired"
        ),
        transport=lambda request: (_ for _ in ()).throw(RuntimeError("HTTP 403 for GET /user/margins/equity")),
    )

    with pytest.raises(KiteAuthenticationError, match="KITE_REAUTH_REQUIRED"):
        client.fetch_margin_balance()


def test_urllib_transport_passes_timeout_as_keyword_argument():
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def getcode(self):
            return 200

        def read(self):
            return b"{}"

    def opener(request, *, timeout):
        seen.append(timeout)
        return Response()

    UrllibHttpTransport(base_url="https://example.test", opener=opener)(
        HttpRequest(method="GET", path="/health")
    )

    assert seen == [5.0]


def test_zerodha_http_client_builds_authorized_order_request_without_logging_secret():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return {"order_id": "o1", "status": "OPEN"}

    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        transport=fake_transport,
    )

    response = client.place_order(
        BrokerOrderRequest(symbol="INFY", direction=Direction.SHORT, quantity=2, price=Decimal("100"))
    )

    assert response.order_id == "o1"
    assert seen[0].method == "POST"
    assert seen[0].path == "/orders/regular"
    assert seen[0].headers["Authorization"] == "token key:token"
    assert "secret" not in repr(seen[0])


def test_zerodha_http_client_normalizes_kite_order_envelope():
    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        transport=lambda request: {"status": "success", "data": {"order_id": "kite-123"}},
    )

    response = client.place_order(
        BrokerOrderRequest(symbol="INFY", direction=Direction.LONG, quantity=1, price=Decimal("100"))
    )

    assert response.order_id == "kite-123"
    assert response.status == "SUBMITTED"


def test_zerodha_http_client_builds_modify_order_request():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return {"order_id": "o1", "status": "MODIFIED"}

    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        transport=fake_transport,
    )

    response = client.modify_order(BrokerModifyRequest(order_id="o1", price=Decimal("101.5"), quantity=2))

    assert response.status == "MODIFIED"
    assert seen[0].method == "PUT"
    assert seen[0].path == "/orders/regular/o1"
    assert seen[0].json == {"quantity": 2, "price": "101.5"}


def test_zerodha_http_client_builds_cancel_order_request():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return {"order_id": "o1", "status": "CANCELLED"}

    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        transport=fake_transport,
    )

    response = client.cancel_order(BrokerCancelRequest(order_id="o1"))

    assert response.status == "CANCELLED"
    assert seen[0].method == "DELETE"
    assert seen[0].path == "/orders/regular/o1"


def test_zerodha_http_client_fetches_equity_margin_live_balance():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return {
            "status": "success",
            "data": {
                "enabled": True,
                "available": {
                    "cash": 5000,
                    "live_balance": 4998.75,
                },
            },
        }

    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        transport=fake_transport,
    )

    balance = client.fetch_margin_balance(segment="equity")

    assert balance == {"available_cash": "4998.75"}
    assert seen[0].method == "GET"
    assert seen[0].path == "/user/margins/equity"


def test_zerodha_http_client_fetches_and_normalizes_orders_and_net_positions():
    seen = []

    def transport(request):
        seen.append(request)
        if request.path == "/orders":
            return {
                "status": "success",
                "data": [{"order_id": "o1", "tradingsymbol": "INFY", "status": "COMPLETE", "filled_quantity": 2}],
            }
        return {
            "status": "success",
            "data": {"net": [{"tradingsymbol": "INFY", "quantity": -2, "product": "MIS"}]},
        }

    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        transport=transport,
    )

    orders = client.fetch_orders()
    positions = client.fetch_positions()

    assert orders[0].order_id == "o1"
    assert orders[0].symbol == "INFY"
    assert orders[0].filled_quantity == 2
    assert positions[0].symbol == "INFY"
    assert positions[0].direction == Direction.SHORT
    assert positions[0].quantity == 2
    assert [request.path for request in seen] == ["/orders", "/portfolio/positions"]
    assert seen[0].headers["X-Kite-Version"] == "3"


def test_zerodha_http_client_rejects_margin_response_without_live_balance():
    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        transport=lambda request: {"status": "success", "data": {"available": {"cash": 5000}}},
    )

    with pytest.raises(ValueError, match="live_balance"):
        client.fetch_margin_balance(segment="equity")


def test_zerodha_http_client_fetches_and_parses_instruments_csv():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return (
            "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,"
            "tick_size,lot_size,instrument_type,segment,exchange\n"
            "408065,1594,INFY,INFOSYS,0,,,0.05,1,EQ,NSE,NSE\n"
        )

    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        transport=fake_transport,
    )

    rows = client.fetch_instruments(exchange="NSE")

    assert seen[0].method == "GET"
    assert seen[0].path == "/instruments/NSE"
    assert seen[0].headers["X-Kite-Version"] == "3"
    assert rows == [
        {
            "instrument_token": "408065",
            "exchange_token": "1594",
            "tradingsymbol": "INFY",
            "name": "INFOSYS",
            "last_price": "0",
            "expiry": "",
            "strike": "",
            "tick_size": "0.05",
            "lot_size": "1",
            "instrument_type": "EQ",
            "segment": "NSE",
            "exchange": "NSE",
        }
    ]


def test_zerodha_http_client_fetches_quotes():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return {
            "status": "success",
            "data": {
                "NSE:INFY": {"last_price": 1000},
                "NSE:TCS": {"last_price": 2000},
            }
        }

    client = ZerodhaHttpClient(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        transport=fake_transport,
    )

    quotes = client.fetch_quotes(symbols=["NSE:INFY", "NSE:TCS"])

    assert seen[0].method == "GET"
    assert seen[0].path == "/quote"
    assert seen[0].query == {"i": ["NSE:INFY", "NSE:TCS"]}
    assert quotes == {
        "NSE:INFY": {"last_price": 1000},
        "NSE:TCS": {"last_price": 2000},
    }


def test_historical_http_client_builds_request_and_normalizes_rows():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return [
            {
                "timestamp": "2026-01-05T10:00:00+00:00",
                "open": "100",
                "high": "101",
                "low": "99",
                "close": "100.5",
                "volume": 1000,
            }
        ]

    client = HistoricalHttpClient(base_path="/history", transport=fake_transport)

    rows = client.fetch(symbol="INFY", resolution="1m")

    assert seen[0].path == "/history/INFY"
    assert seen[0].query == {"resolution": "1m"}
    assert rows[0]["close"] == "100.5"


def test_historical_http_client_fetches_kite_candles_with_explicit_range():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return {
            "status": "success",
            "data": {
                "candles": [
                    ["2026-01-05T09:15:00+0530", 100, 101, 99, 100.5, 1000],
                ]
            },
        }

    client = HistoricalHttpClient(base_path="/history", transport=fake_transport)

    rows = client.fetch_kite_historical(
        instrument_token=408065,
        resolution="1m",
        from_time=datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc),
        to_time=datetime(2026, 1, 5, 15, 30, tzinfo=timezone.utc),
    )

    assert seen[0].path == "/instruments/historical/408065/minute"
    assert seen[0].query == {
        "from": "2026-01-05 09:15:00",
        "to": "2026-01-05 15:30:00",
        "continuous": "0",
        "oi": "0",
    }
    assert rows == [
        {
            "timestamp": "2026-01-05T09:15:00+0530",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100.5,
            "volume": 1000,
        }
    ]


def test_historical_http_client_rejects_unknown_kite_resolution():
    client = HistoricalHttpClient(base_path="/history", transport=lambda request: {})

    with pytest.raises(ValueError, match="unsupported historical resolution"):
        client.fetch_kite_historical(
            instrument_token=408065,
            resolution="2m",
            from_time=datetime(2026, 1, 5, 9, 15),
            to_time=datetime(2026, 1, 5, 15, 30),
        )


def test_news_http_client_requires_api_key_and_builds_query():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return [{"headline": "Infosys upgrade", "source": "example"}]

    client = NewsHttpClient(secret_config=SecretConfig(news_api_key="news-key"), transport=fake_transport)

    rows = client.fetch(symbol="INFY")

    assert rows[0]["headline"] == "Infosys upgrade"
    assert seen[0].headers["X-Api-Key"] == "news-key"
    assert seen[0].query == {"q": "INFY"}


def test_news_http_client_fetches_newsapi_everything_with_date_window():
    seen: list[HttpRequest] = []

    def fake_transport(request: HttpRequest):
        seen.append(request)
        return {
            "status": "ok",
            "totalResults": 1,
            "articles": [
                {
                    "title": "Infosys wins large banking deal",
                    "source": {"name": "Example Wire"},
                    "publishedAt": "2026-01-05T08:30:00Z",
                }
            ],
        }

    client = NewsHttpClient(secret_config=SecretConfig(news_api_key="news-key"), transport=fake_transport)

    rows = client.fetch_newsapi_everything(
        symbol="INFY",
        from_time=datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc),
        to_time=datetime(2026, 1, 5, 23, 59, tzinfo=timezone.utc),
    )

    assert rows == [
        {
            "headline": "Infosys wins large banking deal",
            "source": "Example Wire",
            "published_at": "2026-01-05T08:30:00Z",
        }
    ]
    assert seen[0].method == "GET"
    assert seen[0].path == "/v2/everything"
    assert seen[0].headers["X-Api-Key"] == "news-key"
    assert seen[0].query == {
        "q": "INFY",
        "from": "2026-01-05T00:00:00Z",
        "to": "2026-01-05T23:59:00Z",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": "20",
    }
    assert "news-key" not in repr(seen[0])


def test_news_http_client_rejects_newsapi_error_response():
    client = NewsHttpClient(
        secret_config=SecretConfig(news_api_key="news-key"),
        transport=lambda request: {"status": "error", "code": "rateLimited", "message": "too many requests"},
    )

    with pytest.raises(RuntimeError, match="News API error: rateLimited"):
        client.fetch_newsapi_everything(
            symbol="INFY",
            from_time=datetime(2026, 1, 5, 0, 0),
            to_time=datetime(2026, 1, 5, 23, 59),
        )


def test_news_http_client_rejects_missing_api_key():
    client = NewsHttpClient(secret_config=SecretConfig(), transport=lambda request: [])

    with pytest.raises(PermissionError, match="NEWS_API_KEY"):
        client.fetch(symbol="INFY")


class FakeHttpResponse:
    def __init__(self, *, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.body

    def getcode(self) -> int:
        return self.status


def test_urllib_transport_builds_url_headers_and_json_body_without_network():
    seen = []

    def fake_opener(request, timeout):
        seen.append((request, timeout))
        return FakeHttpResponse(body=b'{"ok": true}')

    transport = UrllibHttpTransport(
        base_url="https://api.example.test/root/",
        timeout_seconds=2.5,
        opener=fake_opener,
    )

    response = transport(
        HttpRequest(
            method="POST",
            path="/orders/regular",
            headers={"Authorization": "token key:access"},
            query={"variety": "regular"},
            json={"tradingsymbol": "INFY", "quantity": 1},
        )
    )

    request, timeout = seen[0]
    assert response == {"ok": True}
    assert timeout == 2.5
    assert request.full_url == "https://api.example.test/root/orders/regular?variety=regular"
    assert request.get_method() == "POST"
    assert request.headers["Authorization"] == "token key:access"
    assert request.headers["Content-type"] == "application/json"
    assert request.data == b'{"tradingsymbol": "INFY", "quantity": 1}'


def test_urllib_transport_raises_on_non_success_status():
    transport = UrllibHttpTransport(
        base_url="https://api.example.test",
        opener=lambda request, timeout: FakeHttpResponse(body=b'{"error": "bad"}', status=500),
    )

    with pytest.raises(RuntimeError, match="HTTP 500"):
        transport(HttpRequest(method="GET", path="/bad"))


def test_http_client_factories_wire_production_transport_boundaries():
    secrets = SecretConfig(
        zerodha_api_key="key",
        zerodha_api_secret="secret",
        zerodha_access_token="token",
        news_api_key="news-key",
    )

    assert isinstance(build_zerodha_http_client(secret_config=secrets), ZerodhaHttpClient)
    assert isinstance(build_historical_http_client(base_url="https://history.example.test"), HistoricalHttpClient)
    assert isinstance(build_news_http_client(secret_config=secrets, base_url="https://news.example.test"), NewsHttpClient)
    assert isinstance(build_zerodha_gateway(secret_config=secrets), ZerodhaGateway)
