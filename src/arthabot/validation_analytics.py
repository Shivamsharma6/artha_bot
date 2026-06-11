from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from arthabot.backtest import BacktestTrade


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: date
    train_end: date
    test_start: date
    test_end: date


class WalkForwardValidator:
    def __init__(self, *, train_days: int, test_days: int, step_days: int) -> None:
        if train_days <= 0 or test_days <= 0 or step_days <= 0:
            raise ValueError("window sizes must be positive")
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days

    def build_windows(self, *, start: date, end: date) -> list[WalkForwardWindow]:
        windows: list[WalkForwardWindow] = []
        cursor = start
        while True:
            train_end = cursor + timedelta(days=self.train_days - 1)
            test_start = train_end + timedelta(days=1)
            test_end = test_start + timedelta(days=self.test_days - 1)
            if test_end > end:
                break
            windows.append(
                WalkForwardWindow(
                    train_start=cursor,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                )
            )
            cursor += timedelta(days=self.step_days)
        return windows


@dataclass(frozen=True)
class OutOfSampleSplit:
    train: tuple[date, ...]
    test: tuple[date, ...]


class OutOfSampleSplitter:
    def __init__(self, *, train_ratio: Decimal) -> None:
        if train_ratio <= 0 or train_ratio >= 1:
            raise ValueError("train_ratio must be between 0 and 1")
        self.train_ratio = train_ratio

    def split(self, days: list[date]) -> OutOfSampleSplit:
        ordered = tuple(sorted(days))
        if len(ordered) < 2:
            raise ValueError("at least two dates are required")
        split_index = int(Decimal(len(ordered)) * self.train_ratio)
        split_index = max(1, min(split_index, len(ordered) - 1))
        train = ordered[:split_index]
        test = ordered[split_index:]
        if max(train) >= min(test):
            raise ValueError("test period must come after training period")
        return OutOfSampleSplit(train=train, test=test)


@dataclass(frozen=True)
class SurvivorshipCheckResult:
    ok: bool
    reason_code: str
    missing_symbols: tuple[str, ...]


class ConstituentMembership:
    def __init__(self, *, active_by_date: dict[date, set[str]]) -> None:
        self.active_by_date = active_by_date

    def check(self, *, symbols: set[str], start: date, end: date) -> SurvivorshipCheckResult:
        observed: set[str] = set()
        cursor = start
        while cursor <= end:
            observed.update(self.active_by_date.get(cursor, set()))
            cursor += timedelta(days=1)
        missing = tuple(sorted(symbols - observed))
        if missing:
            return SurvivorshipCheckResult(False, "MISSING_MEMBERSHIP_HISTORY", missing)
        return SurvivorshipCheckResult(True, "MEMBERSHIP_HISTORY_OK", ())


@dataclass(frozen=True)
class TimeWindowSummary:
    net_pnl: Decimal
    accepted_trades: int
    rejected_trades: int


class TimeWindowReporter:
    def summarize(self, trades: list[BacktestTrade]) -> dict[str, TimeWindowSummary]:
        buckets: dict[str, list[BacktestTrade]] = {}
        for trade in trades:
            buckets.setdefault(trade.entry_time_label, []).append(trade)
        return {
            label: TimeWindowSummary(
                net_pnl=sum((trade.net_pnl for trade in bucket if not trade.rejected), Decimal("0")),
                accepted_trades=sum(1 for trade in bucket if not trade.rejected),
                rejected_trades=sum(1 for trade in bucket if trade.rejected),
            )
            for label, bucket in buckets.items()
        }

