from datetime import datetime
from decimal import Decimal

import pytest

from arthabot.backtest import BacktestExecutionEngine, Candle, HistoricalDataset
from arthabot.brokerage import BrokerageCalculator, BrokerageConfig
from arthabot.strategy_engines import BreakoutSignalEngine
from arthabot.strategies import MomentumSignalEngine
from arthabot.historical_strategy_backtest import (
    HistoricalStrategyBacktestBuilder,
    build_calibration_inputs_from_historical_backtests,
)


def candle(day: str, *, open_price: str, close: str, volume: int = 10_000) -> Candle:
    return Candle(
        timestamp=datetime.fromisoformat(f"{day}T09:15:00+00:00"),
        open=Decimal(open_price),
        high=max(Decimal(open_price), Decimal(close)),
        low=min(Decimal(open_price), Decimal(close)),
        close=Decimal(close),
        volume=volume,
    )


def execution_engine() -> BacktestExecutionEngine:
    return BacktestExecutionEngine(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig(slippage_rate=Decimal("0"))),
    )


def test_historical_strategy_backtest_builder_runs_momentum_signals_with_costs():
    builder = HistoricalStrategyBacktestBuilder(
        signal_engine=MomentumSignalEngine(min_move_pct=Decimal("0.02")),
        execution_engine=execution_engine(),
        quantity=2,
    )
    dataset = HistoricalDataset(
        symbol="INFY",
        resolution="1m",
        candles=[
            candle("2026-01-05", open_price="100", close="103"),
            candle("2026-01-06", open_price="103", close="106"),
        ],
    )

    report = builder.run([dataset])

    assert report.number_of_trades == 1
    assert report.number_of_rejected_trades == 0
    assert report.total_costs > 0
    assert report.net_profit < Decimal("6")


def test_historical_strategy_backtest_builder_supports_breakout_versions():
    builder = HistoricalStrategyBacktestBuilder(
        signal_engine=BreakoutSignalEngine(
            resistance_by_symbol={"TCS": Decimal("100")},
            min_breakout_pct=Decimal("0.01"),
        ),
        execution_engine=execution_engine(),
        quantity=1,
    )
    dataset = HistoricalDataset(
        symbol="TCS",
        resolution="1m",
        candles=[
            candle("2026-01-05", open_price="100", close="102"),
            candle("2026-01-06", open_price="102", close="104"),
        ],
    )

    report = builder.run([dataset])

    assert report.number_of_trades == 1
    assert report.total_costs > 0


def test_historical_strategy_backtest_builder_rejects_missing_historical_candles():
    builder = HistoricalStrategyBacktestBuilder(
        signal_engine=MomentumSignalEngine(min_move_pct=Decimal("0.02")),
        execution_engine=execution_engine(),
        quantity=1,
    )

    with pytest.raises(ValueError, match="historical candles"):
        builder.run([HistoricalDataset(symbol="INFY", resolution="1m", candles=[])])


def test_build_calibration_inputs_from_historical_backtests_generates_cost_aware_reports():
    version = "momentum-v1"
    inputs = build_calibration_inputs_from_historical_backtests(
        datasets_by_version={
            version: [
                HistoricalDataset(
                    symbol="INFY",
                    resolution="1m",
                    candles=[
                        candle("2026-01-05", open_price="100", close="103"),
                        candle("2026-01-06", open_price="103", close="106"),
                    ],
                )
            ]
        },
        signal_engines_by_version={version: MomentumSignalEngine(min_move_pct=Decimal("0.02"))},
        execution_engines_by_version={version: execution_engine()},
        quantity_by_version={version: 2},
        walk_forward_windows_by_version={version: 4},
        out_of_sample_tested_by_version={version: True},
        survivorship_bias_checked_by_version={version: True},
    )

    assert inputs.reports_by_version[version].number_of_trades == 1
    assert inputs.reports_by_version[version].total_costs > 0
    assert inputs.walk_forward_windows_by_version[version] == 4


def test_build_calibration_inputs_from_historical_backtests_fails_closed_for_missing_engine():
    with pytest.raises(ValueError, match="missing signal engine for momentum-v1"):
        build_calibration_inputs_from_historical_backtests(
            datasets_by_version={"momentum-v1": [HistoricalDataset(symbol="INFY", resolution="1m", candles=[])]},
            signal_engines_by_version={},
            execution_engines_by_version={"momentum-v1": execution_engine()},
            quantity_by_version={"momentum-v1": 1},
            walk_forward_windows_by_version={"momentum-v1": 4},
            out_of_sample_tested_by_version={"momentum-v1": True},
            survivorship_bias_checked_by_version={"momentum-v1": True},
        )
