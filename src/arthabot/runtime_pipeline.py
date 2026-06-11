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
        self.available_capital = starting_capital
        self.trades_today = 0
        self.open_symbols: set[str] = set()

    def on_tick(self, tick: Tick) -> None:
        self.feed.record_tick(tick)

    def process_candidate(self, candidate: TradeCandidate, *, now: datetime) -> OrderResult | None:
        proposal = self.hermes.evaluate(candidate, now=now)
        self.audit.append(
            event_type="decision",
            payload={
                "symbol": candidate.symbol,
                "direction": candidate.direction.value,
                "strategy_version": proposal.strategy_version,
            },
        )
        health = self.feed.health(candidate.symbol, now=now)
        if not health.ok:
            self.session.reject(symbol=candidate.symbol, reason=health.reason_code)
            self.audit.append(
                event_type="risk_rejection",
                payload={"symbol": candidate.symbol, "reason_code": health.reason_code},
            )
            return None
        tick = self.feed.latest_tick(candidate.symbol)
        decision = self.risk.evaluate(
            proposal=proposal,
            quote=tick,
            mode=Mode.PAPER,
            available_capital=self.available_capital,
            daily_realized_pnl=Decimal("0"),
            trades_today=self.trades_today,
            open_symbols=self.open_symbols,
            now=now,
        )
        if not decision.approved:
            self.session.reject(symbol=candidate.symbol, reason=decision.reason_code)
            self.audit.append(
                event_type="risk_rejection",
                payload={"symbol": candidate.symbol, "reason_code": decision.reason_code},
            )
            return None
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
        self.trades_today += 1
        self.audit.append(
            event_type="paper_signal_executed",
            payload={"symbol": candidate.symbol, "order_id": result.order_id, "simulated": result.simulated},
        )
        return result

    def daily_report(self):
        return self.session.daily_report()
