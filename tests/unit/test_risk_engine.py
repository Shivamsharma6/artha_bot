from datetime import datetime, timedelta, timezone
from decimal import Decimal

from arthabot.brokerage import BrokerageCalculator, BrokerageConfig
from arthabot.common import Direction, MarketQuote, Mode
from arthabot.risk import RiskConfig, RiskEngine, TradeProposal


def make_engine() -> RiskEngine:
    return RiskEngine(
        config=RiskConfig(
            starting_capital=Decimal("5000"),
            max_risk_per_trade_pct=Decimal("0.01"),
            max_daily_loss_pct=Decimal("0.03"),
            min_allocation_pct=Decimal("0.05"),
            max_trades_per_day=3,
            quote_max_age_seconds=3,
            square_off_time="15:15",
        ),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )


def make_proposal(**overrides) -> TradeProposal:
    data = {
        "symbol": "INFY",
        "direction": Direction.LONG,
        "entry_price": Decimal("100"),
        "stop_loss": Decimal("98"),
        "target_price": Decimal("104"),
        "confidence": Decimal("0.75"),
        "trailing_stop_step": Decimal("1"),
        "timestamp": datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        "strategy_version": "test-strategy-v1",
    }
    data.update(overrides)
    return TradeProposal(**data)


def test_risk_rejects_stale_market_data():
    engine = make_engine()
    proposal = make_proposal()
    quote = MarketQuote(
        symbol="INFY",
        last_price=Decimal("100"),
        timestamp=proposal.timestamp - timedelta(seconds=10),
    )

    decision = engine.evaluate(
        proposal=proposal,
        quote=quote,
        mode=Mode.PAPER,
        available_capital=Decimal("5000"),
        daily_realized_pnl=Decimal("0"),
        trades_today=0,
        open_symbols=set(),
        now=proposal.timestamp,
    )

    assert not decision.approved
    assert decision.reason_code == "STALE_MARKET_DATA"


def test_risk_sizes_position_without_leverage_and_with_minimum_allocation():
    engine = make_engine()
    proposal = make_proposal()
    quote = MarketQuote(symbol="INFY", last_price=Decimal("100"), timestamp=proposal.timestamp)

    decision = engine.evaluate(
        proposal=proposal,
        quote=quote,
        mode=Mode.PAPER,
        available_capital=Decimal("5000"),
        daily_realized_pnl=Decimal("0"),
        trades_today=0,
        open_symbols=set(),
        now=proposal.timestamp,
    )

    assert decision.approved
    assert decision.quantity >= 3
    assert decision.notional <= Decimal("5000")
    assert decision.max_loss <= Decimal("50")
    assert decision.estimated_total_costs > Decimal("0")


def test_risk_rejects_live_without_explicit_live_permission():
    engine = make_engine()
    proposal = make_proposal()
    quote = MarketQuote(symbol="INFY", last_price=Decimal("100"), timestamp=proposal.timestamp)

    decision = engine.evaluate(
        proposal=proposal,
        quote=quote,
        mode=Mode.LIVE,
        available_capital=Decimal("5000"),
        daily_realized_pnl=Decimal("0"),
        trades_today=0,
        open_symbols=set(),
        now=proposal.timestamp,
        live_enabled=False,
    )

    assert not decision.approved
    assert decision.reason_code == "LIVE_NOT_ENABLED"

