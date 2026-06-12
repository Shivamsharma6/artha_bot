from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from arthabot.common import Direction
from arthabot.execution import ExecutionEngine
from arthabot.paper_session import PaperSession, PaperTradeIntent
from arthabot.position_tracker import ExitEvent


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
            trade_id = uuid4().hex
            self.session.submit(
                PaperTradeIntent(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    quantity=signal.quantity,
                    entry_price=signal.entry_price,
                    exit_price=signal.exit_price,
                    total_costs=signal.total_costs,
                    trade_id=trade_id,
                )
            )
            gross_pnl = (
                (signal.exit_price - signal.entry_price) * signal.quantity
                if signal.direction == Direction.LONG
                else (signal.entry_price - signal.exit_price) * signal.quantity
            )
            self.session.record_exit(ExitEvent(
                trade_id=trade_id, symbol=signal.symbol, direction=signal.direction,
                entry_price=signal.entry_price, exit_price=signal.exit_price,
                quantity=signal.quantity, gross_pnl=gross_pnl,
                total_costs=signal.total_costs, net_pnl=gross_pnl - signal.total_costs,
                reason="replay_exit", timestamp=signal.timestamp,
            ))
        return ReplayResult(report=self.session.daily_report().summarize(), missed_trades=missed)
