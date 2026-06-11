from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arthabot.common import Direction, Mode


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    direction: Direction
    quantity: int
    price: Decimal


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    simulated: bool
    status: str


class ExecutionEngine:
    def __init__(self) -> None:
        self.real_orders_submitted: list[OrderIntent] = []

    def submit(
        self,
        intent: OrderIntent,
        *,
        mode: Mode,
        risk_approved: bool,
        live_enabled: bool = False,
    ) -> OrderResult:
        if not risk_approved:
            raise PermissionError("Risk Engine approval is required before execution")
        if intent.quantity <= 0:
            raise ValueError("quantity must be positive")
        if mode in {Mode.BACKTEST, Mode.PAPER}:
            return OrderResult(
                order_id=f"sim-{mode.value.lower()}-{intent.symbol}",
                simulated=True,
                status="accepted",
            )
        if not live_enabled:
            raise PermissionError("LIVE mode requires explicit configuration")
        raise NotImplementedError("Zerodha live order gateway is not implemented in this scaffold")

