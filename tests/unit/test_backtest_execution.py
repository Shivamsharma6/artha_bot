from datetime import date
from decimal import Decimal

from arthabot.backtest import BacktestExecutionEngine, BacktestSignal
from arthabot.brokerage import BrokerageCalculator, BrokerageConfig
from arthabot.common import Direction


def test_backtest_execution_counts_accepted_rejected_and_missed_trades_after_costs():
    engine = BacktestExecutionEngine(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig(slippage_rate=Decimal("0"))),
    )
    signals = [
        BacktestSignal(
            symbol="INFY",
            direction=Direction.LONG,
            entry_date=date(2026, 1, 5),
            entry_price=Decimal("100"),
            exit_price=Decimal("103"),
            quantity=2,
        ),
        BacktestSignal(
            symbol="TCS",
            direction=Direction.SHORT,
            entry_date=date(2026, 1, 5),
            entry_price=Decimal("100"),
            exit_price=Decimal("98"),
            quantity=0,
        ),
        BacktestSignal(
            symbol="SBIN",
            direction=Direction.LONG,
            entry_date=date(2026, 1, 5),
            entry_price=Decimal("0"),
            exit_price=Decimal("101"),
            quantity=1,
        ),
    ]

    report = engine.run(signals)

    assert report.number_of_trades == 1
    assert report.number_of_rejected_trades == 1
    assert report.number_of_missed_trades == 1
    assert report.net_profit < Decimal("6")
    assert report.total_costs > Decimal("0")
    assert report.average_win == report.net_profit
    assert report.expectancy == report.net_profit
    assert report.profit_factor == Decimal("Infinity")
    assert report.best_day == report.net_profit
