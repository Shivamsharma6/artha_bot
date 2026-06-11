from datetime import datetime, timezone
from decimal import Decimal

from arthabot.common import Direction
from arthabot.data import MarketSnapshot
from arthabot.strategy_engines import BreakoutSignalEngine, ReversalSignalEngine, VolumeMoverSignalEngine


def snapshot(symbol: str, price: str, open_price: str, volume: int) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        last_price=Decimal(price),
        open_price=Decimal(open_price),
        volume=volume,
        timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
    )


def test_breakout_engine_generates_long_candidate_above_resistance():
    engine = BreakoutSignalEngine(resistance_by_symbol={"INFY": Decimal("101")}, min_breakout_pct=Decimal("0.005"))

    candidates = engine.generate([snapshot("INFY", "102", "100", 1000)])

    assert candidates[0].symbol == "INFY"
    assert candidates[0].direction == Direction.LONG
    assert not hasattr(candidates[0], "order_id")


def test_breakout_engine_generates_short_candidate_below_support():
    engine = BreakoutSignalEngine(support_by_symbol={"TCS": Decimal("99")}, min_breakout_pct=Decimal("0.005"))

    candidates = engine.generate([snapshot("TCS", "98", "100", 1000)])

    assert candidates[0].direction == Direction.SHORT


def test_reversal_engine_generates_long_candidate_after_deep_intraday_drop():
    engine = ReversalSignalEngine(min_reversal_pct=Decimal("0.02"))

    candidates = engine.generate([snapshot("SBIN", "97", "100", 5000)])

    assert candidates[0].direction == Direction.LONG
    assert "reversal" in candidates[0].rationale.lower()


def test_reversal_engine_generates_short_candidate_after_intraday_spike():
    engine = ReversalSignalEngine(min_reversal_pct=Decimal("0.02"))

    candidates = engine.generate([snapshot("SBIN", "103", "100", 5000)])

    assert candidates[0].direction == Direction.SHORT


def test_volume_mover_engine_prioritizes_high_volume_top_movers():
    engine = VolumeMoverSignalEngine(min_volume=10_000, min_move_pct=Decimal("0.01"))

    candidates = engine.generate([
        snapshot("LOWVOL", "105", "100", 100),
        snapshot("HIVOL", "102", "100", 20_000),
    ])

    assert [candidate.symbol for candidate in candidates] == ["HIVOL"]
    assert candidates[0].direction == Direction.LONG

