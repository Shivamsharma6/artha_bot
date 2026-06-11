from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from arthabot.common import Direction
from arthabot.execution import ExecutionEngine
from arthabot.paper_session import PaperSession, PaperTradeIntent


@dataclass(frozen=True)
class ReplaySignal:
    symbol: str
    direction: Direction
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    total_costs: Decimal
    timestamp: datetime


@dataclass(frozen=True)
class ReplayResult:
    report: dict[str, Any]
    missed_trades: int


class ReplayPaperRunner:
    def __init__(self, *, trading_date: date, starting_capital: Decimal, execution: ExecutionEngine) -> None:
        self.session = PaperSession(
            trading_date=trading_date,
            starting_capital=starting_capital,
            execution=execution,
        )

    def run(self, signals: list[ReplaySignal]) -> ReplayResult:
        missed = 0
        for signal in sorted(signals, key=lambda item: item.timestamp):
            if signal.quantity <= 0 or signal.entry_price <= 0 or signal.exit_price <= 0:
                self.session.reject(symbol=signal.symbol, reason="UNEXECUTABLE_REPLAY_SIGNAL")
                missed += 1
                continue
            self.session.submit(
                PaperTradeIntent(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    quantity=signal.quantity,
                    entry_price=signal.entry_price,
                    exit_price=signal.exit_price,
                    total_costs=signal.total_costs,
                )
            )
        return ReplayResult(report=self.session.daily_report().summarize(), missed_trades=missed)

