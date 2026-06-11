from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from arthabot.backtest import BacktestEngine, Candle, HistoricalDataset
from arthabot.common import Direction, Mode
from arthabot.data import FreshnessPolicy, MarketSnapshot
from arthabot.execution import ExecutionEngine
from arthabot.learning import LearningEngine, ProposedChange
from arthabot.paper import PaperTradingEngine
from arthabot.strategies import MomentumSignalEngine


def test_data_snapshot_blocks_stale_live_decisions():
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    snapshot = MarketSnapshot(
        symbol="SBIN",
        last_price=Decimal("610"),
        volume=100_000,
        timestamp=now - timedelta(seconds=9),
    )

    assert not FreshnessPolicy(max_age_seconds=3).is_fresh(snapshot, now=now)


def test_strategy_generates_candidate_but_not_order():
    snapshot = MarketSnapshot(
        symbol="SBIN",
        last_price=Decimal("610"),
        volume=250_000,
        timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        open_price=Decimal("600"),
    )

    candidates = MomentumSignalEngine(min_move_pct=Decimal("0.01")).generate([snapshot])

    assert candidates[0].symbol == "SBIN"
    assert candidates[0].direction == Direction.LONG
    assert not hasattr(candidates[0], "order_id")


def test_backtest_rejects_dataset_shorter_than_required_years_when_strict():
    engine = BacktestEngine(min_years=3)
    dataset = HistoricalDataset(
        symbol="INFY",
        resolution="1m",
        candles=[
            Candle(
                timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=1000,
            )
        ],
    )

    with pytest.raises(ValueError, match="3 years"):
        engine.validate_dataset(dataset, strict=True)


def test_paper_engine_uses_simulated_execution_only():
    execution = ExecutionEngine()
    paper = PaperTradingEngine(execution)

    result = paper.submit_fill(symbol="TCS", direction=Direction.LONG, quantity=1, price=Decimal("100"))

    assert result.simulated
    assert execution.real_orders_submitted == []


def test_learning_engine_refuses_unsafe_live_risk_change():
    learning = LearningEngine()

    with pytest.raises(PermissionError):
        learning.validate_change(
            ProposedChange(
                name="disable live stop loss",
                target="risk.stop_loss_required",
                value=False,
                mode=Mode.LIVE,
            )
        )

