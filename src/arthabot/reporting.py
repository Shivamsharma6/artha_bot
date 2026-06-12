from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TradeRecord:
    symbol: str
    gross_pnl: Decimal
    total_costs: Decimal
    accepted: bool
    trade_id: str = ""

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.total_costs


@dataclass(frozen=True)
class DailyReport:
    date: str
    starting_capital: Decimal
    trades: list[TradeRecord]

    def summarize(self) -> dict[str, Decimal | int | str]:
        gross_pnl = sum((trade.gross_pnl for trade in self.trades), Decimal("0"))
        total_costs = sum((trade.total_costs for trade in self.trades), Decimal("0"))
        net_pnl = gross_pnl - total_costs
        accepted = sum(1 for trade in self.trades if trade.accepted)
        rejected = sum(1 for trade in self.trades if not trade.accepted)
        return {
            "date": self.date,
            "starting_capital": self.starting_capital,
            "gross_pnl": gross_pnl,
            "total_costs": total_costs,
            "net_pnl": net_pnl,
            "accepted_trades": accepted,
            "rejected_trades": rejected,
            "ending_capital": self.starting_capital + net_pnl,
        }
