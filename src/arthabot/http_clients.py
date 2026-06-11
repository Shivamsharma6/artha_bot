from __future__ import annotations

from collections.abc import Callable
import csv
from dataclasses import dataclass, field
from datetime import datetime
import json
from io import StringIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from arthabot.broker_gateway import (
    BrokerCancelRequest,
    BrokerModifyRequest,
    BrokerOrderRequest,
    BrokerOrderResponse,
    ZerodhaGateway,
)
from arthabot.secrets import SecretConfig
from arthabot.common import Direction
from arthabot.order_reconciliation import BrokerOrderState
from arthabot.reconciliation import BrokerPosition


SENSITIVE_HEADERS = {"authorization", "x-api-key"}


@dataclass(frozen=True, repr=False)
class HttpRequest:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, Any] = field(default_factory=dict)
    json: dict[str, Any] | None = None

    def __repr__(self) -> str:
        safe_headers = {
            key: ("[REDACTED]" if key.lower() in SENSITIVE_HEADERS else value)
            for key, value in self.headers.items()
        }
        return (
            "HttpRequest("
            f"method={self.method!r}, path={self.path!r}, "
            f"headers={safe_headers!r}, query={self.query!r}, json={self.json!r})"
        )


Transport = Callable[[HttpRequest], Any]
UrlOpener = Callable[..., Any]


class UrllibHttpTransport:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 5.0,
        opener: UrlOpener | None = None,
    ) -> None:
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must be an absolute http(s) URL")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout_seconds = timeout_seconds
        self.opener = opener or urlopen

    def __call__(self, request: HttpRequest) -> Any:
        url = urljoin(self.base_url, request.path.lstrip("/"))
        if request.query:
            url = f"{url}?{urlencode(request.query, doseq=True)}"

        headers = dict(request.headers)
        body: bytes | None = None
        if request.json is not None:
            body = json.dumps(request.json).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")

        url_request = Request(url, data=body, headers=headers, method=request.method.upper())
        try:
            response = self.opener(url_request, timeout=self.timeout_seconds)
            with response:
                status = response.getcode()
                raw_body = response.read()
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} for {request.method.upper()} {request.path}") from exc
        except URLError as exc:
            raise RuntimeError(f"HTTP transport failed for {request.method.upper()} {request.path}") from exc

        if status < 200 or status >= 300:
            raise RuntimeError(f"HTTP {status} for {request.method.upper()} {request.path}")
        if not raw_body:
            return {}
        decoded = raw_body.decode("utf-8")
        try:
            return json.loads(decoded)
        except Exception:
            return decoded


class ZerodhaHttpClient:
    def __init__(self, *, secret_config: SecretConfig, transport: Transport) -> None:
        self.secret_config = secret_config
        self.transport = transport

    def place_order(self, order: BrokerOrderRequest) -> BrokerOrderResponse:
        if not self.secret_config.has_zerodha_credentials:
            raise PermissionError("Zerodha credentials are required")
        raw = self.transport(
            HttpRequest(
                method="POST",
                path=f"/orders/{order.variety}",
                headers=self._headers(),
                json={
                    "tradingsymbol": order.symbol,
                    "transaction_type": "BUY" if order.direction.value == "long" else "SELL",
                    "quantity": order.quantity,
                    "product": order.product,
                    "order_type": order.order_type,
                    **({"price": str(order.price)} if order.order_type != "MARKET" else {}),
                },
            )
        )
        return self._order_response(raw, default_status="SUBMITTED")

    def modify_order(self, order: BrokerModifyRequest, *, variety: str = "regular") -> BrokerOrderResponse:
        if not self.secret_config.has_zerodha_credentials:
            raise PermissionError("Zerodha credentials are required")
        raw = self.transport(
            HttpRequest(
                method="PUT",
                path=f"/orders/{variety}/{order.order_id}",
                headers=self._headers(),
                json={
                    "quantity": order.quantity,
                    "price": str(order.price),
                },
            )
        )
        return self._order_response(raw, default_status="MODIFIED")

    def cancel_order(self, order: BrokerCancelRequest, *, variety: str = "regular") -> BrokerOrderResponse:
        if not self.secret_config.has_zerodha_credentials:
            raise PermissionError("Zerodha credentials are required")
        raw = self.transport(
            HttpRequest(
                method="DELETE",
                path=f"/orders/{variety}/{order.order_id}",
                headers=self._headers(),
            )
        )
        return self._order_response(raw, default_status="CANCELLED")

    @staticmethod
    def _order_response(raw: Any, *, default_status: str) -> BrokerOrderResponse:
        payload = dict(raw)
        data = dict(payload.get("data") or {})
        order_id = data.get("order_id", payload.get("order_id"))
        if not order_id:
            raise RuntimeError("Zerodha order response did not include an order_id")
        status = data.get("status") or payload.get("order_status")
        if status is None and payload.get("status") not in {None, "success"}:
            status = payload["status"]
        return BrokerOrderResponse(
            order_id=str(order_id),
            status=str(status or default_status),
            raw=payload,
        )

    def fetch_margin_balance(self, *, segment: str = "equity") -> dict[str, str]:
        if not self.secret_config.has_zerodha_credentials:
            raise PermissionError("Zerodha credentials are required")
        raw = self.transport(
            HttpRequest(
                method="GET",
                path=f"/user/margins/{segment}",
                headers=self._headers(),
            )
        )
        available = dict(raw["data"]["available"])
        if "live_balance" not in available:
            raise ValueError("Zerodha margin response missing available.live_balance")
        return {"available_cash": str(available["live_balance"])}

    def fetch_orders(self) -> list[BrokerOrderState]:
        self._require_credentials()
        raw = self.transport(HttpRequest(method="GET", path="/orders", headers=self._headers()))
        rows = raw.get("data") or []
        if not isinstance(rows, list):
            raise RuntimeError("Zerodha orders response data must be a list")
        return [
            BrokerOrderState(
                order_id=str(row["order_id"]),
                symbol=str(row["tradingsymbol"]),
                status=str(row["status"]),
                filled_quantity=int(row.get("filled_quantity", 0)),
            )
            for row in rows
        ]

    def fetch_positions(self) -> list[BrokerPosition]:
        self._require_credentials()
        raw = self.transport(HttpRequest(method="GET", path="/portfolio/positions", headers=self._headers()))
        data = raw.get("data") or {}
        rows = data.get("net") or []
        if not isinstance(rows, list):
            raise RuntimeError("Zerodha positions response net data must be a list")
        positions: list[BrokerPosition] = []
        for row in rows:
            quantity = int(row.get("quantity", 0))
            if quantity == 0 or str(row.get("product", "")) != "MIS":
                continue
            positions.append(
                BrokerPosition(
                    symbol=str(row["tradingsymbol"]),
                    quantity=abs(quantity),
                    direction=Direction.LONG if quantity > 0 else Direction.SHORT,
                )
            )
        return positions

    def _require_credentials(self) -> None:
        if not self.secret_config.has_zerodha_credentials:
            raise PermissionError("Zerodha credentials are required")

    def fetch_instruments(self, *, exchange: str | None = None) -> list[dict[str, str]]:
        if not self.secret_config.has_zerodha_credentials:
            raise PermissionError("Zerodha credentials are required")
        raw = self.transport(
            HttpRequest(
                method="GET",
                path=f"/instruments/{exchange}" if exchange else "/instruments",
                headers=self._headers(),
            )
        )
        if not isinstance(raw, str):
            raise ValueError("Zerodha instruments response must be CSV text")
        return list(csv.DictReader(StringIO(raw)))

    def fetch_quotes(self, symbols: list[str]) -> dict[str, Any]:
        if not self.secret_config.has_zerodha_credentials:
            raise PermissionError("Zerodha credentials are required")
        if not symbols:
            return {}
        raw = self.transport(
            HttpRequest(
                method="GET",
                path="/quote",
                headers=self._headers(),
                query={"i": symbols},
            )
        )
        if isinstance(raw, dict) and "data" in raw:
            return dict(raw["data"])
        return dict(raw)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.secret_config.zerodha_api_key}:{self.secret_config.zerodha_access_token}",
            "X-Kite-Version": "3",
        }


class HistoricalHttpClient:
    KITE_INTERVALS = {
        "1m": "minute",
        "minute": "minute",
        "3m": "3minute",
        "3minute": "3minute",
        "5m": "5minute",
        "5minute": "5minute",
        "10m": "10minute",
        "10minute": "10minute",
        "15m": "15minute",
        "15minute": "15minute",
        "30m": "30minute",
        "30minute": "30minute",
        "60m": "60minute",
        "60minute": "60minute",
        "1d": "day",
        "day": "day",
    }

    def __init__(self, *, base_path: str, transport: Transport) -> None:
        self.base_path = base_path.rstrip("/")
        self.transport = transport

    def fetch(self, *, symbol: str, resolution: str) -> list[dict[str, Any]]:
        raw = self.transport(
            HttpRequest(
                method="GET",
                path=f"{self.base_path}/{symbol}",
                query={"resolution": resolution},
            )
        )
        return list(raw)

    def fetch_kite_historical(
        self,
        *,
        instrument_token: int,
        resolution: str,
        from_time: datetime,
        to_time: datetime,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict[str, Any]]:
        interval = self.KITE_INTERVALS.get(resolution)
        if interval is None:
            raise ValueError(f"unsupported historical resolution: {resolution}")
        raw = self.transport(
            HttpRequest(
                method="GET",
                path=f"/instruments/historical/{instrument_token}/{interval}",
                query={
                    "from": self._format_kite_time(from_time),
                    "to": self._format_kite_time(to_time),
                    "continuous": "1" if continuous else "0",
                    "oi": "1" if oi else "0",
                },
            )
        )
        return [
            {
                "timestamp": candle[0],
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5],
            }
            for candle in raw["data"]["candles"]
        ]

    @staticmethod
    def _format_kite_time(value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")


class NewsHttpClient:
    def __init__(self, *, secret_config: SecretConfig, transport: Transport) -> None:
        self.secret_config = secret_config
        self.transport = transport

    def fetch(self, *, symbol: str) -> list[dict[str, Any]]:
        if not self.secret_config.news_api_key:
            raise PermissionError("NEWS_API_KEY is required")
        raw = self.transport(
            HttpRequest(
                method="GET",
                path="/news",
                headers={"X-Api-Key": self.secret_config.news_api_key},
                query={"q": symbol},
            )
        )
        return list(raw)

    def fetch_newsapi_everything(
        self,
        *,
        symbol: str,
        from_time: datetime,
        to_time: datetime,
        domains: list[str] | None = None,
        language: str = "en",
        sort_by: str = "publishedAt",
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        if not self.secret_config.news_api_key:
            raise PermissionError("NEWS_API_KEY is required")
        raw = self.transport(
            HttpRequest(
                method="GET",
                path="/v2/everything",
                headers={"X-Api-Key": self.secret_config.news_api_key},
                query={
                    "q": symbol,
                    "from": self._format_newsapi_time(from_time),
                    "to": self._format_newsapi_time(to_time),
                    "language": language,
                    "sortBy": sort_by,
                    "pageSize": str(page_size),
                    **({"domains": ",".join(domains)} if domains else {}),
                },
            )
        )
        if raw.get("status") == "error":
            raise RuntimeError(f"News API error: {raw.get('code', 'unknown')}")
        return [
            {
                "headline": str(article.get("title", "")),
                "source": str(dict(article.get("source") or {}).get("name", "")),
                "published_at": str(article.get("publishedAt", "")),
            }
            for article in raw.get("articles", [])
        ]

    @staticmethod
    def _format_newsapi_time(value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_zerodha_http_client(
    *,
    secret_config: SecretConfig,
    base_url: str = "https://api.kite.trade",
    timeout_seconds: float = 3.0,
) -> ZerodhaHttpClient:
    return ZerodhaHttpClient(
        secret_config=secret_config,
        transport=UrllibHttpTransport(base_url=base_url, timeout_seconds=timeout_seconds),
    )


def build_zerodha_gateway(
    *,
    secret_config: SecretConfig,
    base_url: str = "https://api.kite.trade",
    timeout_seconds: float = 3.0,
) -> ZerodhaGateway:
    client = build_zerodha_http_client(
        secret_config=secret_config,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    return ZerodhaGateway(
        secret_config=secret_config,
        submit_order=client.place_order,
        modify_order=client.modify_order,
        cancel_order=client.cancel_order,
    )


def build_historical_http_client(
    *,
    base_url: str,
    base_path: str = "/history",
    timeout_seconds: float = 5.0,
) -> HistoricalHttpClient:
    return HistoricalHttpClient(
        base_path=base_path,
        transport=UrllibHttpTransport(base_url=base_url, timeout_seconds=timeout_seconds),
    )


def build_news_http_client(
    *,
    secret_config: SecretConfig,
    base_url: str,
    timeout_seconds: float = 5.0,
) -> NewsHttpClient:
    return NewsHttpClient(
        secret_config=secret_config,
        transport=UrllibHttpTransport(base_url=base_url, timeout_seconds=timeout_seconds),
    )
