from datetime import datetime, date, timezone
from decimal import Decimal

from arthabot.backtest import BacktestExecutionEngine, BacktestSignal, Candle
from arthabot.brokerage import BrokerageCalculator, BrokerageConfig
from arthabot.common import Direction
from arthabot.trailing_stop import TrailingStopPolicy


def test_fixed_stop_hit():
    broker = BrokerageCalculator(BrokerageConfig())
    engine = BacktestExecutionEngine(
        starting_capital=Decimal("5000"), brokerage=broker,
    )
    candles = (
        Candle(timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
               open=Decimal("100"), high=Decimal("101"), low=Decimal("97"), close=Decimal("98"), volume=0),
        Candle(timestamp=datetime(2026, 1, 5, 10, 1, tzinfo=timezone.utc),
               open=Decimal("98"), high=Decimal("99"), low=Decimal("96"), close=Decimal("97"), volume=0),
    )
    signal = BacktestSignal(
        symbol="INFY", direction=Direction.LONG,
        entry_date=date(2026, 1, 5), entry_price=Decimal("100"),
        exit_price=Decimal("105"), quantity=10,
        stop_loss=Decimal("98"), candles=candles,
    )
    report = engine.run([signal])
    assert report.number_of_trades == 1
    assert report.max_drawdown > Decimal("0")


def test_no_stop_target_reached():
    broker = BrokerageCalculator(BrokerageConfig())
    engine = BacktestExecutionEngine(
        starting_capital=Decimal("5000"), brokerage=broker,
    )
    candles = (
        Candle(timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
               open=Decimal("100"), high=Decimal("106"), low=Decimal("99"), close=Decimal("105"), volume=0),
    )
    signal = BacktestSignal(
        symbol="INFY", direction=Direction.LONG,
        entry_date=date(2026, 1, 5), entry_price=Decimal("100"),
        exit_price=Decimal("105"), quantity=10,
        stop_loss=Decimal("98"), candles=candles,
    )
    report = engine.run([signal])
    assert report.number_of_trades == 1
    assert report.net_profit > Decimal("0")


def test_short_position_stop_hit():
    broker = BrokerageCalculator(BrokerageConfig())
    engine = BacktestExecutionEngine(
        starting_capital=Decimal("5000"), brokerage=broker,
    )
    candles = (
        Candle(timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
               open=Decimal("100"), high=Decimal("103"), low=Decimal("99"), close=Decimal("102"), volume=0),
    )
    signal = BacktestSignal(
        symbol="TCS", direction=Direction.SHORT,
        entry_date=date(2026, 1, 5), entry_price=Decimal("100"),
        exit_price=Decimal("95"), quantity=10,
        stop_loss=Decimal("102"), candles=candles,
    )
    report = engine.run([signal])
    assert report.number_of_trades == 1


def test_trailing_stop_exits_at_trail():
    broker = BrokerageCalculator(BrokerageConfig())
    policy = TrailingStopPolicy(
        step=Decimal("1"), cooldown_seconds=0, max_modifications_per_trade=5,
    )
    engine = BacktestExecutionEngine(
        starting_capital=Decimal("5000"), brokerage=broker,
        trailing_policy=policy,
    )
    candles = (
        Candle(timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
               open=Decimal("100"), high=Decimal("102"), low=Decimal("99"), close=Decimal("101"), volume=0),
        Candle(timestamp=datetime(2026, 1, 5, 10, 1, tzinfo=timezone.utc),
               open=Decimal("101"), high=Decimal("104"), low=Decimal("100"), close=Decimal("103"), volume=0),
        Candle(timestamp=datetime(2026, 1, 5, 10, 2, tzinfo=timezone.utc),
               open=Decimal("103"), high=Decimal("103"), low=Decimal("99"), close=Decimal("100"), volume=0),
    )
    signal = BacktestSignal(
        symbol="INFY", direction=Direction.LONG,
        entry_date=date(2026, 1, 5), entry_price=Decimal("100"),
        exit_price=Decimal("110"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("1"),
        candles=candles,
    )
    report = engine.run([signal])
    assert report.number_of_trades == 1