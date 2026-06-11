from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, ROUND_FLOOR

from arthabot.brokerage import BrokerageCalculator, TradeSide
from arthabot.common import Direction, MarketQuote, Mode


@dataclass(frozen=True)
class RiskConfig:
    starting_capital: Decimal = Decimal("5000")
    max_risk_per_trade_pct: Decimal = Decimal("0.01")
    max_daily_loss_pct: Decimal = Decimal("0.03")
    min_allocation_pct: Decimal = Decimal("0.05")
    max_trades_per_day: int = 3
    quote_max_age_seconds: int = 3
    square_off_time: str = "15:15"


@dataclass(frozen=True)
class TradeProposal:
    symbol: str
    direction: Direction
    entry_price: Decimal
    stop_loss: Decimal
    target_price: Decimal
    confidence: Decimal
    trailing_stop_step: Decimal
    timestamp: datetime
    strategy_version: str


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason_code: str
    quantity: int = 0
    notional: Decimal = Decimal("0")
    max_loss: Decimal = Decimal("0")
    estimated_total_costs: Decimal = Decimal("0")


class RiskEngine:
    def __init__(self, *, config: RiskConfig, brokerage: BrokerageCalculator) -> None:
        self.config = config
        self.brokerage = brokerage

    def evaluate(
        self,
        *,
        proposal: TradeProposal,
        quote: MarketQuote,
        mode: Mode,
        available_capital: Decimal,
        daily_realized_pnl: Decimal,
        trades_today: int,
        open_symbols: set[str],
        now: datetime,
        live_enabled: bool = False,
    ) -> RiskDecision:
        if mode == Mode.LIVE and not live_enabled:
            return RiskDecision(False, "LIVE_NOT_ENABLED")
        if quote.symbol != proposal.symbol:
            return RiskDecision(False, "QUOTE_SYMBOL_MISMATCH")
        if abs((now - quote.timestamp).total_seconds()) > self.config.quote_max_age_seconds:
            return RiskDecision(False, "STALE_MARKET_DATA")
        if proposal.symbol in open_symbols:
            return RiskDecision(False, "DUPLICATE_POSITION")
        if trades_today >= self.config.max_trades_per_day:
            return RiskDecision(False, "MAX_TRADES_REACHED")
        if daily_realized_pnl <= -(available_capital * self.config.max_daily_loss_pct):
            return RiskDecision(False, "MAX_DAILY_LOSS_REACHED")
        if now.time() >= self._square_off_time():
            return RiskDecision(False, "SQUARE_OFF_WINDOW")
        if proposal.trailing_stop_step <= 0:
            return RiskDecision(False, "INVALID_TRAILING_STOP")
        stop_distance = abs(proposal.entry_price - proposal.stop_loss)
        if stop_distance <= 0:
            return RiskDecision(False, "INVALID_STOP_LOSS")

        max_loss_amount = available_capital * self.config.max_risk_per_trade_pct
        risk_quantity = int((max_loss_amount / stop_distance).to_integral_value(rounding=ROUND_FLOOR))
        min_notional = available_capital * self.config.min_allocation_pct
        min_quantity = int((min_notional / proposal.entry_price).to_integral_value(rounding=ROUND_FLOOR))
        if min_quantity * proposal.entry_price < min_notional:
            min_quantity += 1
        capital_quantity = int((available_capital / proposal.entry_price).to_integral_value(rounding=ROUND_FLOOR))
        quantity = min(risk_quantity, capital_quantity)
        if quantity <= 0:
            return RiskDecision(False, "INSUFFICIENT_CAPITAL")
        if quantity < min_quantity:
            return RiskDecision(False, "MIN_ALLOCATION_CONFLICTS_WITH_RISK")

        side = TradeSide.LONG if proposal.direction == Direction.LONG else TradeSide.SHORT
        costs = self.brokerage.estimate_intraday_equity(
            side=side,
            entry_price=proposal.entry_price,
            exit_price=proposal.target_price,
            quantity=quantity,
        )
        max_loss = (stop_distance * quantity).quantize(Decimal("0.01"))
        notional = (proposal.entry_price * quantity).quantize(Decimal("0.01"))
        if notional > available_capital:
            return RiskDecision(False, "LEVERAGE_REQUIRED")

        return RiskDecision(
            approved=True,
            reason_code="APPROVED",
            quantity=quantity,
            notional=notional,
            max_loss=max_loss,
            estimated_total_costs=costs.total_charges,
        )

    def _square_off_time(self) -> time:
        hour, minute = self.config.square_off_time.split(":", maxsplit=1)
        return time(int(hour), int(minute))

