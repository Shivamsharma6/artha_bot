from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from arthabot.audit_store import JsonlAuditStore
from arthabot.common import Mode
from arthabot.execution import ExecutionEngine, OrderResult
from arthabot.live_feed import LiveFeedMonitor, Tick
from arthabot.paper_session import PaperSession, PaperTradeIntent
from arthabot.position_tracker import PositionTracker
from arthabot.risk import RiskEngine, TradeProposal
from arthabot.strategies import TradeCandidate


@dataclass(frozen=True)
class HermesAdapter:
    proposal_factory: Callable[[TradeCandidate, datetime], TradeProposal]

    def evaluate(self, candidate: TradeCandidate, *, now: datetime) -> TradeProposal:
        return self.proposal_factory(candidate, now)


class PaperRuntimePipeline:
    def __init__(
        self,
        *,
        trading_date: date,
        starting_capital: Decimal,
        execution: ExecutionEngine,
        risk: RiskEngine,
        hermes: HermesAdapter,
        audit: JsonlAuditStore,
        max_tick_age_seconds: int,
        position_tracker: PositionTracker,
        state_changed: Callable[[], None] | None = None,
    ) -> None:
        self.feed = LiveFeedMonitor(max_tick_age_seconds=max_tick_age_seconds)
        self.session = PaperSession(
            trading_date=trading_date,
            starting_capital=starting_capital,
            execution=execution,
        )
        self.risk = risk
        self.hermes = hermes
        self.audit = audit
        self.tracker = position_tracker
        self.state_changed = state_changed

    def on_tick(self, tick: Tick) -> None:
        self.feed.record_tick(tick)
        positions = {position.symbol: position for position in self.tracker.snapshot().open_positions}
        position = positions.get(tick.symbol)
        if position is not None:
            self.session.require_trade_ids([position.trade_id])
        exit_event = self.tracker.on_tick(
            symbol=tick.symbol, price=tick.price, now=tick.timestamp,
        )
        if exit_event is not None:
            self.session.record_exit(exit_event)
            self.audit.append(
                event_type="position_closed",
                payload={
                    "symbol": exit_event.symbol,
                    "direction": exit_event.direction.value,
                    "entry_price": str(exit_event.entry_price),
                    "exit_price": str(exit_event.exit_price),
                    "quantity": exit_event.quantity,
                    "net_pnl": str(exit_event.net_pnl),
                    "total_costs": str(exit_event.total_costs),
                    "reason": exit_event.reason,
                },
            )
            if self.state_changed is not None:
                self.state_changed()

    def process_candidate(self, candidate: TradeCandidate, *, now: datetime) -> OrderResult | None:
        health = self.feed.health(candidate.symbol, now=now)
        if not health.ok:
            self.session.reject(symbol=candidate.symbol, reason=health.reason_code)
            self.audit.append(
                event_type="risk_rejection",
                payload={"symbol": candidate.symbol, "reason_code": health.reason_code},
            )
            return None
        proposal = self.hermes.evaluate(candidate, now=now)
        self.audit.append(
            event_type="decision",
            payload={
                "symbol": candidate.symbol,
                "direction": candidate.direction.value,
                "strategy_version": proposal.strategy_version,
            },
        )
        tick = self.feed.latest_tick(candidate.symbol)
        snapshot = self.tracker.snapshot()
        decision = self.risk.evaluate(
            proposal=proposal,
            quote=tick,
            mode=Mode.PAPER,
            available_capital=snapshot.available_capital,
            daily_realized_pnl=snapshot.daily_realized_pnl,
            trades_today=snapshot.trades_today,
            open_symbols=snapshot.open_symbols,
            now=now,
        )
        if not decision.approved:
            self.session.reject(symbol=candidate.symbol, reason=decision.reason_code)
            self.audit.append(
                event_type="risk_rejection",
                payload={"symbol": candidate.symbol, "reason_code": decision.reason_code},
            )
            return None
        trade_id = uuid4().hex
        self.tracker.validate_open_position(
            trade_id=trade_id, symbol=candidate.symbol,
            entry_price=proposal.entry_price, quantity=decision.quantity,
            stop_loss=proposal.stop_loss,
            trailing_stop_step=proposal.trailing_stop_step,
        )
        self.audit.append(
            event_type="risk_approved",
            payload={"symbol": candidate.symbol, "quantity": decision.quantity},
        )
        result = self.session.submit(
            PaperTradeIntent(
                symbol=candidate.symbol,
                direction=candidate.direction,
                quantity=decision.quantity,
                entry_price=proposal.entry_price,
                exit_price=proposal.target_price,
                total_costs=decision.estimated_total_costs,
                trade_id=trade_id,
            )
        )
        self.tracker.open_position(
            trade_id=trade_id,
            symbol=candidate.symbol,
            direction=candidate.direction,
            entry_price=proposal.entry_price,
            quantity=decision.quantity,
            stop_loss=proposal.stop_loss,
            trailing_stop_step=proposal.trailing_stop_step,
            now=now,
        )
        self.audit.append(
            event_type="paper_signal_executed",
            payload={"symbol": candidate.symbol, "order_id": result.order_id, "simulated": result.simulated},
        )
        if self.state_changed is not None:
            self.state_changed()
        return result

    def square_off(self, *, now: datetime):
        positions = self.tracker.snapshot().open_positions
        self.session.require_trade_ids([position.trade_id for position in positions])
        prices: dict[str, Decimal] = {}
        for position in positions:
            if not self.feed.health(position.symbol, now=now).ok:
                raise RuntimeError(f"fresh price required to square off {position.symbol}")
            prices[position.symbol] = self.feed.latest_tick(position.symbol).price
        events = self.tracker.close_all_positions(prices=prices, reason="square_off", now=now)
        for event in events:
            self.session.record_exit(event)
            self.audit.append(
                event_type="position_closed",
                payload={
                    "trade_id": event.trade_id,
                    "symbol": event.symbol,
                    "direction": event.direction.value,
                    "entry_price": str(event.entry_price),
                    "exit_price": str(event.exit_price),
                    "quantity": event.quantity,
                    "net_pnl": str(event.net_pnl),
                    "total_costs": str(event.total_costs),
                    "reason": event.reason,
                },
            )
        if events and self.state_changed is not None:
            self.state_changed()
        return events

    def start_new_day(self, trading_date: date) -> None:
        self.tracker.start_new_day()
        self.session.start_new_day(trading_date)
        if self.state_changed is not None:
            self.state_changed()

    def daily_report(self):
        session_report = self.session.daily_report()
        snapshot = self.tracker.snapshot()
        report = session_report.summarize()
        report["available_capital"] = snapshot.available_capital
        report["daily_realized_pnl"] = snapshot.daily_realized_pnl
        report["unrealized_pnl"] = Decimal("0")  # computed separately with live prices
        report["open_positions"] = len(snapshot.open_positions)
        return report
