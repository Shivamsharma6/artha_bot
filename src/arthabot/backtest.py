from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from decimal import Decimal, localcontext

from arthabot.brokerage import BrokerageCalculator, TradeSide
from arthabot.common import Direction


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class HistoricalDataset:
    symbol: str
    resolution: str
    candles: list[Candle]


class BacktestEngine:
    def __init__(self, *, min_years: int = 3) -> None:
        self.min_years = min_years

    def validate_dataset(self, dataset: HistoricalDataset, *, strict: bool) -> None:
        if not dataset.candles:
            raise ValueError("historical dataset must contain candles")
        ordered = sorted(dataset.candles, key=lambda candle: candle.timestamp)
        span_days = (ordered[-1].timestamp - ordered[0].timestamp).days
        required_days = self.min_years * 365
        if strict and span_days < required_days:
            raise ValueError(f"historical dataset must cover at least {self.min_years} years")
        if dataset.resolution not in {"1m", "5m", "15m", "1d"}:
            raise ValueError("dataset resolution must be explicit and supported")


@dataclass(frozen=True)
class BacktestTrade:
    symbol: str
    direction: Direction
    entry_date: date
    exit_date: date
    gross_pnl: Decimal
    total_costs: Decimal
    rejected: bool
    entry_time_label: str = "unknown"
    entry_timestamp: datetime | None = None

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.total_costs


@dataclass(frozen=True)
class BacktestReport:
    net_profit: Decimal
    gross_profit: Decimal
    total_costs: Decimal
    win_rate: Decimal
    number_of_trades: int
    number_of_rejected_trades: int
    max_drawdown: Decimal
    number_of_missed_trades: int = 0
    long_net_pnl: Decimal = Decimal("0")
    short_net_pnl: Decimal = Decimal("0")
    average_win: Decimal = Decimal("0")
    average_loss: Decimal = Decimal("0")
    profit_factor: Decimal = Decimal("0")
    expectancy: Decimal = Decimal("0")
    best_day: Decimal = Decimal("0")
    worst_day: Decimal = Decimal("0")
    sharpe_like: Decimal = Decimal("0")
    open_window_net_pnl: Decimal = Decimal("0")
    close_window_net_pnl: Decimal = Decimal("0")
    time_window_net_pnl: dict[str, Decimal] = field(default_factory=dict)
    metadata: BacktestReportMetadata | None = None

    def require_promotion_metadata(self) -> BacktestReportMetadata:
        if self.metadata is None:
            raise ValueError("promotion metadata is required")
        return self.metadata


@dataclass(frozen=True)
class BacktestReportMetadata:
    strategy_version: str
    data_start: date
    data_end: date
    data_resolution: str

    def __post_init__(self) -> None:
        if not self.strategy_version.strip():
            raise ValueError("strategy_version is required")
        if self.data_end <= self.data_start:
            raise ValueError("data_end must be after data_start")
        if not self.data_resolution.strip() or self.data_resolution == "unknown":
            raise ValueError("data_resolution must be explicit")


class BacktestAccounting:
    def __init__(self, *, starting_capital: Decimal) -> None:
        self.starting_capital = starting_capital

    def summarize(
        self,
        trades: list[BacktestTrade],
        *,
        metadata: BacktestReportMetadata | None = None,
    ) -> BacktestReport:
        accepted = [trade for trade in trades if not trade.rejected]
        rejected = [trade for trade in trades if trade.rejected]
        gross_profit = sum((trade.gross_pnl for trade in accepted), Decimal("0"))
        total_costs = sum((trade.total_costs for trade in accepted), Decimal("0"))
        net_profit = gross_profit - total_costs
        wins = sum(1 for trade in accepted if trade.net_pnl > 0)
        win_rate = Decimal(wins) / Decimal(len(accepted)) if accepted else Decimal("0")
        max_drawdown = self._max_drawdown(accepted)
        long_net = sum((trade.net_pnl for trade in accepted if trade.direction == Direction.LONG), Decimal("0"))
        short_net = sum((trade.net_pnl for trade in accepted if trade.direction == Direction.SHORT), Decimal("0"))
        wins = [trade.net_pnl for trade in accepted if trade.net_pnl > 0]
        losses = [trade.net_pnl for trade in accepted if trade.net_pnl < 0]
        average_win = sum(wins, Decimal("0")) / Decimal(len(wins)) if wins else Decimal("0")
        average_loss = abs(sum(losses, Decimal("0")) / Decimal(len(losses))) if losses else Decimal("0")
        gross_wins = sum(wins, Decimal("0"))
        gross_losses = abs(sum(losses, Decimal("0")))
        if gross_wins == 0:
            profit_factor = Decimal("0")
        elif gross_losses == 0:
            profit_factor = Decimal("Infinity")
        else:
            profit_factor = gross_wins / gross_losses
        expectancy = net_profit / Decimal(len(accepted)) if accepted else Decimal("0")
        daily_pnl = self._group_net_pnl(accepted, key=lambda trade: trade.exit_date)
        daily_values = list(daily_pnl.values())
        best_day = max(daily_values) if daily_values else Decimal("0")
        worst_day = min(daily_values) if daily_values else Decimal("0")
        time_window_pnl = self._group_net_pnl(accepted, key=self._time_window_label)
        return BacktestReport(
            net_profit=net_profit,
            gross_profit=gross_profit,
            total_costs=total_costs,
            win_rate=win_rate,
            number_of_trades=len(accepted),
            number_of_rejected_trades=len(rejected),
            number_of_missed_trades=0,
            max_drawdown=max_drawdown,
            long_net_pnl=long_net,
            short_net_pnl=short_net,
            average_win=average_win,
            average_loss=average_loss,
            profit_factor=profit_factor,
            expectancy=expectancy,
            best_day=best_day,
            worst_day=worst_day,
            sharpe_like=self._sharpe_like(daily_values),
            open_window_net_pnl=time_window_pnl.get("open", Decimal("0")),
            close_window_net_pnl=time_window_pnl.get("close", Decimal("0")),
            time_window_net_pnl=dict(sorted(time_window_pnl.items())),
            metadata=metadata,
        )

    @staticmethod
    def _group_net_pnl(trades: list[BacktestTrade], *, key) -> dict[object, Decimal]:
        grouped: dict[object, Decimal] = {}
        for trade in trades:
            group = key(trade)
            grouped[group] = grouped.get(group, Decimal("0")) + trade.net_pnl
        return grouped

    @staticmethod
    def _sharpe_like(daily_values: list[Decimal]) -> Decimal:
        if len(daily_values) < 2:
            return Decimal("0")
        mean = sum(daily_values, Decimal("0")) / Decimal(len(daily_values))
        variance = sum(((value - mean) ** 2 for value in daily_values), Decimal("0")) / Decimal(
            len(daily_values)
        )
        if variance == 0:
            return Decimal("0")
        with localcontext() as context:
            context.prec = 28
            return mean / variance.sqrt()

    @staticmethod
    def _time_window_label(trade: BacktestTrade) -> str:
        if trade.entry_time_label != "unknown" or trade.entry_timestamp is None:
            return trade.entry_time_label
        entry_time = trade.entry_timestamp.time().replace(tzinfo=None)
        if time(9, 15) <= entry_time <= time(10, 15):
            return "open"
        if time(14, 30) <= entry_time <= time(15, 30):
            return "close"
        return "midday"

    def _max_drawdown(self, trades: list[BacktestTrade]) -> Decimal:
        equity = self.starting_capital
        peak = equity
        max_drawdown = Decimal("0")
        for trade in trades:
            equity += trade.net_pnl
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        return max_drawdown


@dataclass(frozen=True)
class BacktestSignal:
    symbol: str
    direction: Direction
    entry_date: date
    entry_price: Decimal
    exit_price: Decimal
    quantity: int


class BacktestExecutionEngine:
    def __init__(self, *, starting_capital: Decimal, brokerage: BrokerageCalculator) -> None:
        self.starting_capital = starting_capital
        self.brokerage = brokerage

    def run(self, signals: list[BacktestSignal]) -> BacktestReport:
        trades: list[BacktestTrade] = []
        missed = 0
        for signal in signals:
            if signal.quantity <= 0:
                trades.append(
                    BacktestTrade(
                        symbol=signal.symbol,
                        direction=signal.direction,
                        entry_date=signal.entry_date,
                        exit_date=signal.entry_date,
                        gross_pnl=Decimal("0"),
                        total_costs=Decimal("0"),
                        rejected=True,
                        entry_time_label="unknown",
                    )
                )
                continue
            if signal.entry_price <= 0 or signal.exit_price <= 0:
                missed += 1
                continue
            side = TradeSide.LONG if signal.direction == Direction.LONG else TradeSide.SHORT
            costs = self.brokerage.estimate_intraday_equity(
                side=side,
                entry_price=signal.entry_price,
                exit_price=signal.exit_price,
                quantity=signal.quantity,
            )
            trades.append(
                BacktestTrade(
                    symbol=signal.symbol,
                    direction=signal.direction,
                    entry_date=signal.entry_date,
                    exit_date=signal.entry_date,
                    gross_pnl=costs.gross_pnl,
                    total_costs=costs.total_charges,
                    rejected=False,
                    entry_time_label="unknown",
                )
            )
        report = BacktestAccounting(starting_capital=self.starting_capital).summarize(trades)
        return replace(report, number_of_missed_trades=missed)
