from __future__ import annotations

from decimal import Decimal

from arthabot.common import Direction, Mode
from arthabot.execution import ExecutionEngine, OrderIntent, OrderResult


class PaperTradingEngine:
    def __init__(self, execution: ExecutionEngine) -> None:
        self.execution = execution

    def submit_fill(
        self,
        *,
        symbol: str,
        direction: Direction,
        quantity: int,
        price: Decimal,
    ) -> OrderResult:
        return self.execution.submit(
            OrderIntent(symbol=symbol, direction=direction, quantity=quantity, price=price),
            mode=Mode.PAPER,
            risk_approved=True,
        )

