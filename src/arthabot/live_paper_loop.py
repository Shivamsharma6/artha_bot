from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.common import Direction
from arthabot.execution import ExecutionEngine, OrderResult
from arthabot.live_feed import LiveFeedMonitor, Tick
from arthabot.paper_session import PaperSession, PaperTradeIntent


@dataclass(frozen=True)
class LivePaperSignal:
    symbol: str
    direction: Direction
    quantity: int
    target_exit_price: Decimal
    total_costs: Decimal


class LivePaperLoop:
    def __init__(
        self,
        *,
        trading_date: date,
        starting_capital: Decimal,
        execution: ExecutionEngine,
        audit: JsonlAuditStore,
        max_tick_age_seconds: int,
    ) -> None:
        self.feed = LiveFeedMonitor(max_tick_age_seconds=max_tick_age_seconds)
        self.session = PaperSession(
            trading_date=trading_date,
            starting_capital=starting_capital,
            execution=execution,
        )
        self.audit = audit
        self.missed_trades = 0

    def on_tick(self, tick: Tick) -> None:
        self.feed.record_tick(tick)

    def process_signal(self, signal: LivePaperSignal, *, now: datetime) -> OrderResult | None:
        health = self.feed.health(signal.symbol, now=now)
        if not health.ok:
            self.missed_trades += 1
            self.session.reject(symbol=signal.symbol, reason=health.reason_code)
            self.audit.append(
                event_type="paper_signal_rejected",
                payload={"symbol": signal.symbol, "reason_code": health.reason_code},
            )
            return None
        tick = self.feed.latest_tick(signal.symbol)
        result = self.session.submit(
            PaperTradeIntent(
                symbol=signal.symbol,
                direction=signal.direction,
                quantity=signal.quantity,
                entry_price=tick.price,
                exit_price=signal.target_exit_price,
                total_costs=signal.total_costs,
            )
        )
        self.audit.append(
            event_type="paper_signal_executed",
            payload={"symbol": signal.symbol, "order_id": result.order_id, "simulated": result.simulated},
        )
        return result

    def daily_report(self):
        return self.session.daily_report()
