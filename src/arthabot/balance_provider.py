from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from arthabot.reconciliation import AccountSnapshot
from arthabot.secrets import SecretConfig


@dataclass(frozen=True)
class BalanceProviderRequest:
    segment: str = "equity"


class BrokerBalanceProvider:
    def __init__(
        self,
        *,
        secret_config: SecretConfig,
        client: Callable[[BalanceProviderRequest], dict[str, Any]] | None,
    ) -> None:
        self.secret_config = secret_config
        self.client = client

    def fetch(self, request: BalanceProviderRequest) -> AccountSnapshot:
        if not self.secret_config.has_zerodha_credentials:
            raise PermissionError("Zerodha credentials are required for broker balance fetch")
        if self.client is None:
            raise NotImplementedError("broker balance client must be injected explicitly")
        raw = self.client(request)
        return AccountSnapshot(available_cash=Decimal(str(raw["available_cash"])))


def build_broker_balance_provider(
    *,
    secret_config: SecretConfig,
    margin_client=None,
    base_url: str = "https://api.kite.trade",
) -> BrokerBalanceProvider:
    if margin_client is None:
        from arthabot.http_clients import build_zerodha_http_client

        margin_client = build_zerodha_http_client(secret_config=secret_config, base_url=base_url)

    return BrokerBalanceProvider(
        secret_config=secret_config,
        client=lambda request: margin_client.fetch_margin_balance(segment=request.segment),
    )
