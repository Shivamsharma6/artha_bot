from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from arthabot.common import Direction, Mode
from arthabot.execution import ExecutionEngine, OrderIntent, OrderResult
from arthabot.reporting import DailyReport, TradeRecord


@dataclass(frozen=True)
class PaperTradeIntent:
    symbol: str
    direction: Direction
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    total_costs: Decimal


class PaperSession:
    def __init__(self, *, trading_date: date, starting_capital: Decimal, execution: ExecutionEngine) -> None:
        self.trading_date = trading_date
        self.starting_capital = starting_capital
        self.execution = execution
        self._trades: list[TradeRecord] = []

    def submit(self, intent: PaperTradeIntent) -> OrderResult:
        result = self.execution.submit(
            OrderIntent(
                symbol=intent.symbol,
                direction=intent.direction,
                quantity=intent.quantity,
                price=intent.entry_price,
            ),
            mode=Mode.PAPER,
            risk_approved=True,
        )
        gross = self._gross_pnl(intent)
        self._trades.append(
            TradeRecord(
                symbol=intent.symbol,
                gross_pnl=gross,
                total_costs=intent.total_costs,
                accepted=True,
            )
        )
        return result

    def reject(self, *, symbol: str, reason: str) -> None:
        self._trades.append(TradeRecord(symbol=symbol, gross_pnl=Decimal("0"), total_costs=Decimal("0"), accepted=False))
        return None

    def restore_trades(self, trades: list[TradeRecord]) -> None:
        if self._trades:
            raise RuntimeError("paper trade ledger can only be restored into an empty session")
        self._trades = list(trades)

    @property
    def trades(self) -> tuple[TradeRecord, ...]:
        return tuple(self._trades)

    def daily_report(self) -> DailyReport:
        return DailyReport(
            date=self.trading_date.isoformat(),
            starting_capital=self.starting_capital,
            trades=list(self._trades),
        )

    @staticmethod
    def _gross_pnl(intent: PaperTradeIntent) -> Decimal:
        if intent.direction == Direction.LONG:
            return (intent.exit_price - intent.entry_price) * intent.quantity
        return (intent.entry_price - intent.exit_price) * intent.quantity
