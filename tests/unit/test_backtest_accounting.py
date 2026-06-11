from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from arthabot.backtest import (
    BacktestAccounting,
    BacktestReportMetadata,
    BacktestTrade,
)
from arthabot.common import Direction


def test_backtest_accounting_reports_cost_adjusted_metrics_and_drawdown():
    accounting = BacktestAccounting(starting_capital=Decimal("5000"))
    trades = [
        BacktestTrade(
            symbol="INFY",
            direction=Direction.LONG,
            entry_date=date(2026, 1, 5),
            exit_date=date(2026, 1, 5),
            gross_pnl=Decimal("100"),
            total_costs=Decimal("10"),
            rejected=False,
        ),
        BacktestTrade(
            symbol="TCS",
            direction=Direction.SHORT,
            entry_date=date(2026, 1, 6),
            exit_date=date(2026, 1, 6),
            gross_pnl=Decimal("-50"),
            total_costs=Decimal("5"),
            rejected=False,
        ),
        BacktestTrade(
            symbol="SBIN",
            direction=Direction.LONG,
            entry_date=date(2026, 1, 6),
            exit_date=date(2026, 1, 6),
            gross_pnl=Decimal("0"),
            total_costs=Decimal("0"),
            rejected=True,
        ),
    ]

    report = accounting.summarize(trades)

    assert report.net_profit == Decimal("35")
    assert report.gross_profit == Decimal("50")
    assert report.total_costs == Decimal("15")
    assert report.number_of_trades == 2
    assert report.number_of_rejected_trades == 1
    assert report.win_rate == Decimal("0.50")
    assert report.max_drawdown == Decimal("55")
    assert report.long_net_pnl == Decimal("90")
    assert report.short_net_pnl == Decimal("-55")
    assert report.average_win == Decimal("90")
    assert report.average_loss == Decimal("55")
    assert report.profit_factor == Decimal("90") / Decimal("55")
    assert report.expectancy == Decimal("17.5")
    assert report.best_day == Decimal("90")
    assert report.worst_day == Decimal("-55")
    assert report.sharpe_like == Decimal("17.5") / Decimal("72.5")


def test_backtest_accounting_reports_zero_safe_metrics_for_no_accepted_trades():
    report = BacktestAccounting(starting_capital=Decimal("5000")).summarize([])

    assert report.average_win == 0
    assert report.average_loss == 0
    assert report.profit_factor == 0
    assert report.expectancy == 0
    assert report.best_day == 0
    assert report.worst_day == 0
    assert report.sharpe_like == 0


def test_backtest_accounting_represents_all_win_profit_factor_as_infinity():
    report = BacktestAccounting(starting_capital=Decimal("5000")).summarize(
        [
            BacktestTrade(
                symbol="INFY",
                direction=Direction.LONG,
                entry_date=date(2026, 1, 5),
                exit_date=date(2026, 1, 5),
                gross_pnl=Decimal("12"),
                total_costs=Decimal("2"),
                rejected=False,
            )
        ]
    )

    assert report.profit_factor == Decimal("Infinity")
    assert report.average_win == Decimal("10")
    assert report.average_loss == 0


def test_backtest_accounting_summarizes_time_windows_and_metadata():
    metadata = BacktestReportMetadata(
        strategy_version="momentum-v1",
        data_start=date(2023, 1, 1),
        data_end=date(2026, 1, 2),
        data_resolution="1m",
    )
    trades = [
        BacktestTrade(
            symbol="INFY",
            direction=Direction.LONG,
            entry_date=date(2026, 1, 5),
            exit_date=date(2026, 1, 5),
            gross_pnl=Decimal("20"),
            total_costs=Decimal("2"),
            rejected=False,
            entry_time_label="open",
            entry_timestamp=datetime(2026, 1, 5, 9, 20, tzinfo=timezone.utc),
        ),
        BacktestTrade(
            symbol="TCS",
            direction=Direction.SHORT,
            entry_date=date(2026, 1, 5),
            exit_date=date(2026, 1, 5),
            gross_pnl=Decimal("-8"),
            total_costs=Decimal("2"),
            rejected=False,
            entry_time_label="close",
        ),
        BacktestTrade(
            symbol="SBIN",
            direction=Direction.LONG,
            entry_date=date(2026, 1, 6),
            exit_date=date(2026, 1, 6),
            gross_pnl=Decimal("7"),
            total_costs=Decimal("2"),
            rejected=False,
            entry_time_label="midday",
        ),
    ]

    report = BacktestAccounting(starting_capital=Decimal("5000")).summarize(
        trades,
        metadata=metadata,
    )

    assert report.open_window_net_pnl == Decimal("18")
    assert report.close_window_net_pnl == Decimal("-10")
    assert report.time_window_net_pnl == {
        "close": Decimal("-10"),
        "midday": Decimal("5"),
        "open": Decimal("18"),
    }
    assert report.metadata == metadata
    assert report.require_promotion_metadata() == metadata


def test_backtest_report_requires_metadata_for_promotion():
    report = BacktestAccounting(starting_capital=Decimal("5000")).summarize([])

    with pytest.raises(ValueError, match="promotion metadata is required"):
        report.require_promotion_metadata()


def test_backtest_report_metadata_rejects_invalid_period():
    with pytest.raises(ValueError, match="data_end must be after data_start"):
        BacktestReportMetadata(
            strategy_version="momentum-v1",
            data_start=date(2026, 1, 2),
            data_end=date(2026, 1, 1),
            data_resolution="1m",
        )


def test_backtest_accounting_classifies_unknown_timestamp_into_open_and_close_windows():
    trades = [
        BacktestTrade(
            symbol="INFY",
            direction=Direction.LONG,
            entry_date=date(2026, 1, 5),
            exit_date=date(2026, 1, 5),
            gross_pnl=Decimal("10"),
            total_costs=Decimal("1"),
            rejected=False,
            entry_timestamp=datetime(2026, 1, 5, 9, 30),
        ),
        BacktestTrade(
            symbol="TCS",
            direction=Direction.LONG,
            entry_date=date(2026, 1, 5),
            exit_date=date(2026, 1, 5),
            gross_pnl=Decimal("6"),
            total_costs=Decimal("1"),
            rejected=False,
            entry_timestamp=datetime(2026, 1, 5, 15, 0),
        ),
    ]

    report = BacktestAccounting(starting_capital=Decimal("5000")).summarize(trades)

    assert report.open_window_net_pnl == Decimal("9")
    assert report.close_window_net_pnl == Decimal("5")
