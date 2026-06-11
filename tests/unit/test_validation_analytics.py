from datetime import date
from decimal import Decimal

from arthabot.backtest import BacktestTrade
from arthabot.common import Direction
from arthabot.validation_analytics import (
    ConstituentMembership,
    OutOfSampleSplitter,
    TimeWindowReporter,
    WalkForwardValidator,
)


def test_walk_forward_validator_builds_ordered_train_test_windows():
    validator = WalkForwardValidator(train_days=10, test_days=5, step_days=5)

    windows = validator.build_windows(start=date(2026, 1, 1), end=date(2026, 2, 1))

    assert windows[0].train_start == date(2026, 1, 1)
    assert windows[0].train_end == date(2026, 1, 10)
    assert windows[0].test_start == date(2026, 1, 11)
    assert windows[0].test_end == date(2026, 1, 15)
    assert windows[1].train_start == date(2026, 1, 6)


def test_out_of_sample_splitter_keeps_test_period_after_training_period():
    splitter = OutOfSampleSplitter(train_ratio=Decimal("0.60"))
    days = [date(2026, 1, day) for day in range(1, 11)]

    split = splitter.split(days)

    assert split.train == tuple(days[:6])
    assert split.test == tuple(days[6:])
    assert max(split.train) < min(split.test)


def test_constituent_membership_flags_survivorship_bias_when_symbol_history_missing():
    membership = ConstituentMembership(
        active_by_date={
            date(2026, 1, 1): {"INFY", "TCS"},
            date(2026, 1, 2): {"INFY"},
        }
    )

    result = membership.check(
        symbols={"INFY", "RELIANCE"},
        start=date(2026, 1, 1),
        end=date(2026, 1, 2),
    )

    assert not result.ok
    assert result.reason_code == "MISSING_MEMBERSHIP_HISTORY"
    assert result.missing_symbols == ("RELIANCE",)


def test_time_window_reporter_groups_open_close_and_midday_performance():
    trades = [
        BacktestTrade(
            symbol="INFY",
            direction=Direction.LONG,
            entry_date=date(2026, 1, 5),
            exit_date=date(2026, 1, 5),
            gross_pnl=Decimal("10"),
            total_costs=Decimal("1"),
            rejected=False,
            entry_time_label="open",
        ),
        BacktestTrade(
            symbol="TCS",
            direction=Direction.SHORT,
            entry_date=date(2026, 1, 5),
            exit_date=date(2026, 1, 5),
            gross_pnl=Decimal("-5"),
            total_costs=Decimal("1"),
            rejected=False,
            entry_time_label="close",
        ),
        BacktestTrade(
            symbol="SBIN",
            direction=Direction.LONG,
            entry_date=date(2026, 1, 5),
            exit_date=date(2026, 1, 5),
            gross_pnl=Decimal("0"),
            total_costs=Decimal("0"),
            rejected=True,
            entry_time_label="midday",
        ),
    ]

    report = TimeWindowReporter().summarize(trades)

    assert report["open"].net_pnl == Decimal("9")
    assert report["close"].net_pnl == Decimal("-6")
    assert report["midday"].rejected_trades == 1

