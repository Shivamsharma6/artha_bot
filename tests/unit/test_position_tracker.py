from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from arthabot.brokerage import BrokerageCalculator, BrokerageConfig
from arthabot.common import Direction
from arthabot.execution import ExecutionEngine
from arthabot.trailing_stop import TrailingStopPolicy
from arthabot.position_tracker import ExitEvent, PositionTracker, PositionSnapshot


def test_position_tracker_initializes_with_starting_capital():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    snapshot = tracker.snapshot()
    assert snapshot.available_capital == Decimal("5000")
    assert snapshot.daily_realized_pnl == Decimal("0")
    assert snapshot.trades_today == 0
    assert snapshot.open_symbols == frozenset()
    assert snapshot.open_positions == tuple()


def test_open_position_records_state():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY",
        direction=Direction.LONG,
        entry_price=Decimal("100"),
        quantity=10,
        stop_loss=Decimal("98"),
        trailing_stop_step=Decimal("1"),
        now=now,
    )
    snapshot = tracker.snapshot()
    assert len(snapshot.open_positions) == 1
    assert snapshot.trades_today == 1
    assert "INFY" in snapshot.open_symbols
    pos = snapshot.open_positions[0]
    assert pos.symbol == "INFY"
    assert pos.direction == Direction.LONG
    assert pos.entry_price == Decimal("100")
    assert pos.quantity == 10
    assert pos.stop_loss == Decimal("98")
    assert pos.trailing is not None
    assert pos.trailing.current_stop == Decimal("98")


def test_close_position_updates_capital():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("0"), now=now,
    )
    exit_event = tracker.close_position(
        symbol="INFY", exit_price=Decimal("105"),
        reason="target", now=now,
    )
    assert exit_event.gross_pnl == Decimal("50")
    assert exit_event.total_costs > Decimal("0")
    assert exit_event.net_pnl < Decimal("50")
    snapshot = tracker.snapshot()
    assert snapshot.available_capital > Decimal("5000")
    assert snapshot.daily_realized_pnl > Decimal("0")
    assert snapshot.open_positions == ()
    assert snapshot.open_symbols == frozenset()


def test_close_short_position():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="TCS", direction=Direction.SHORT,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("102"), trailing_stop_step=Decimal("0"), now=now,
    )
    exit_event = tracker.close_position(
        symbol="TCS", exit_price=Decimal("95"),
        reason="target", now=now,
    )
    assert exit_event.gross_pnl == Decimal("50")


def test_on_tick_exit_long_position():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
        trailing_policy=TrailingStopPolicy(
            step=Decimal("1"), cooldown_seconds=0, max_modifications_per_trade=5,
        ),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("1"), now=now,
    )
    # Price drops to stop level
    exit_event = tracker.on_tick(symbol="INFY", price=Decimal("98"), now=now)
    assert exit_event is not None
    assert exit_event.reason == "trailing_stop_hit"
    assert exit_event.exit_price == Decimal("98")
    assert tracker.snapshot().open_positions == ()


def test_on_tick_exit_short_position():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
        trailing_policy=TrailingStopPolicy(
            step=Decimal("1"), cooldown_seconds=0, max_modifications_per_trade=5,
        ),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="TCS", direction=Direction.SHORT,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("102"), trailing_stop_step=Decimal("1"), now=now,
    )
    # Price rises to stop level
    exit_event = tracker.on_tick(symbol="TCS", price=Decimal("102"), now=now)
    assert exit_event is not None
    assert exit_event.reason == "trailing_stop_hit"
    assert tracker.snapshot().open_positions == ()


def test_on_tick_noop_for_unknown_symbol():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    result = tracker.on_tick(symbol="UNKNOWN", price=Decimal("100"), now=now)
    assert result is None


def test_on_tick_trailing_stop_update():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
        trailing_policy=TrailingStopPolicy(
            step=Decimal("1"), cooldown_seconds=0, max_modifications_per_trade=5,
        ),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("1"), now=now,
    )
    # Price moves favorably — trailing stop should advance
    result = tracker.on_tick(symbol="INFY", price=Decimal("103"), now=now)
    assert result is None  # no exit
    pos = tracker.snapshot().open_positions[0]
    assert pos.trailing.current_stop > Decimal("98")


def test_close_all_positions():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("0"), now=now,
    )
    tracker.open_position(
        symbol="TCS", direction=Direction.SHORT,
        entry_price=Decimal("200"), quantity=5,
        stop_loss=Decimal("202"), trailing_stop_step=Decimal("0"), now=now,
    )
    events = tracker.close_all_positions(
        prices={"INFY": Decimal("105"), "TCS": Decimal("195")},
        reason="square_off", now=now,
    )
    assert len(events) == 2
    assert tracker.snapshot().open_positions == ()
    assert tracker.snapshot().open_symbols == frozenset()


def test_unrealized_pnl_long():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("0"), now=now,
    )
    pnl = tracker.unrealized_pnl(prices={"INFY": Decimal("105")})
    assert pnl == Decimal("50")


def test_unrealized_pnl_short():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="TCS", direction=Direction.SHORT,
        entry_price=Decimal("200"), quantity=5,
        stop_loss=Decimal("202"), trailing_stop_step=Decimal("0"), now=now,
    )
    pnl = tracker.unrealized_pnl(prices={"TCS": Decimal("195")})
    assert pnl == Decimal("25")


def test_snapshot_unrealized_pnl_with_prices():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("0"), now=now,
    )
    snapshot = tracker.snapshot(prices={"INFY": Decimal("105")})
    assert snapshot.unrealized_pnl == Decimal("50")


def test_config_loads_trailing_stop_settings():
    from arthabot.config import load_runtime_config
    from pathlib import Path
    config = load_runtime_config(Path("config"))
    assert config.risk.trailing_stop_enabled is True
    assert config.risk.trailing_stop_step == Decimal("0.5")
    assert config.risk.trailing_stop_cooldown_seconds == 30
    assert config.risk.trailing_stop_max_modifications == 5


def test_paper_session_record_exit():
    from datetime import date
    from arthabot.paper_session import PaperSession, PaperTradeIntent
    from arthabot.execution import ExecutionEngine

    session = PaperSession(
        trading_date=date(2026, 6, 12),
        starting_capital=Decimal("5000"),
        execution=ExecutionEngine(),
    )
    session.submit(PaperTradeIntent(
        symbol="INFY", direction=Direction.LONG,
        quantity=10, entry_price=Decimal("100"),
        exit_price=Decimal("105"), total_costs=Decimal("5"),
    ))
    exit_event = ExitEvent(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), exit_price=Decimal("105"),
        quantity=10, gross_pnl=Decimal("50"),
        total_costs=Decimal("5"), net_pnl=Decimal("45"),
        reason="trailing_stop_hit",
        timestamp=datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc),
    )
    session.record_exit(exit_event)
    report = session.daily_report().summarize()
    assert report["net_pnl"] == Decimal("45")


def test_pipeline_uses_position_tracker_for_capital():
    from arthabot.runtime_pipeline import PaperRuntimePipeline, HermesAdapter
    from arthabot.risk import RiskEngine, RiskConfig
    from arthabot.audit_store import JsonlAuditStore
    from arthabot.strategies import TradeCandidate
    import tempfile, os

    audit_path = os.path.join(tempfile.mkdtemp(), "test.audit.jsonl")
    broker_cfg = BrokerageConfig()
    broker_calc = BrokerageCalculator(broker_cfg)
    risk = RiskEngine(config=RiskConfig(), brokerage=broker_calc)
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=broker_calc,
    )

    def proposal_factory(candidate, now):
        from arthabot.risk import TradeProposal
        return TradeProposal(
            symbol=candidate.symbol, direction=candidate.direction,
            entry_price=Decimal("100"), stop_loss=Decimal("98"),
            target_price=Decimal("105"), confidence=Decimal("0.8"),
            trailing_stop_step=Decimal("1"),
            timestamp=now, strategy_version="test-v1",
        )

    pipeline = PaperRuntimePipeline(
        trading_date=datetime(2026, 6, 12, tzinfo=timezone.utc).date(),
        starting_capital=Decimal("5000"),
        execution=ExecutionEngine(),
        risk=risk,
        hermes=HermesAdapter(proposal_factory=proposal_factory),
        audit=JsonlAuditStore(audit_path),
        max_tick_age_seconds=15,
        position_tracker=tracker,
    )
    assert pipeline.tracker.snapshot().available_capital == Decimal("5000")
