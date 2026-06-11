from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from arthabot.common import Direction
from arthabot.secrets import SecretConfig


@dataclass(frozen=True)
class BrokerOrderRequest:
    symbol: str
    direction: Direction
    quantity: int
    price: Decimal
    product: str = "MIS"
    variety: str = "regular"
    order_type: str = "LIMIT"


@dataclass(frozen=True)
class BrokerOrderResponse:
    order_id: str
    status: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class BrokerModifyRequest:
    order_id: str
    price: Decimal
    quantity: int


@dataclass(frozen=True)
class BrokerCancelRequest:
    order_id: str


class ZerodhaGateway:
    def __init__(
        self,
        *,
        secret_config: SecretConfig,
        submit_order: Callable[[BrokerOrderRequest], BrokerOrderResponse] | None = None,
        modify_order: Callable[[BrokerModifyRequest], BrokerOrderResponse] | None = None,
        cancel_order: Callable[[BrokerCancelRequest], BrokerOrderResponse] | None = None,
    ) -> None:
        self.secret_config = secret_config
        self._submit_order = submit_order
        self._modify_order = modify_order
        self._cancel_order = cancel_order

    def place_intraday_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse:
        self._require_credentials()
        if request.product != "MIS":
            raise ValueError("only Zerodha MIS intraday product is allowed")
        if request.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self._submit_order is None:
            raise NotImplementedError("live Zerodha adapter must be injected explicitly")
        return self._submit_order(request)

    def modify_order(self, request: BrokerModifyRequest) -> BrokerOrderResponse:
        self._require_credentials()
        if request.quantity <= 0:
            raise ValueError("quantity must be positive")
        if request.price <= 0:
            raise ValueError("price must be positive")
        if self._modify_order is None:
            raise NotImplementedError("live Zerodha modify adapter must be injected explicitly")
        return self._modify_order(request)

    def cancel_order(self, request: BrokerCancelRequest) -> BrokerOrderResponse:
        self._require_credentials()
        if not request.order_id.strip():
            raise ValueError("order_id is required")
        if self._cancel_order is None:
            raise NotImplementedError("live Zerodha cancel adapter must be injected explicitly")
        return self._cancel_order(request)

    def _require_credentials(self) -> None:
        if not self.secret_config.has_zerodha_credentials:
            raise PermissionError("Zerodha credentials are required before broker operations")
