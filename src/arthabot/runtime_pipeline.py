from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

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

    def on_tick(self, tick: Tick) -> None:
        self.feed.record_tick(tick)
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
        self.tracker.open_position(
            symbol=candidate.symbol,
            direction=candidate.direction,
            entry_price=proposal.entry_price,
            quantity=decision.quantity,
            stop_loss=proposal.stop_loss,
            trailing_stop_step=proposal.trailing_stop_step,
            now=now,
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
            )
        )
        self.audit.append(
            event_type="paper_signal_executed",
            payload={"symbol": candidate.symbol, "order_id": result.order_id, "simulated": result.simulated},
        )
        return result

    def daily_report(self):
        session_report = self.session.daily_report()
        snapshot = self.tracker.snapshot()
        report = session_report.summarize()
        report["available_capital"] = snapshot.available_capital
        report["daily_realized_pnl"] = snapshot.daily_realized_pnl
        report["unrealized_pnl"] = Decimal("0")  # computed separately with live prices
        report["open_positions"] = len(snapshot.open_positions)
        return report
