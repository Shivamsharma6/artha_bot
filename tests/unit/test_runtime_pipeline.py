from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.brokerage import BrokerageCalculator, BrokerageConfig
from arthabot.common import Direction
from arthabot.execution import ExecutionEngine
from arthabot.live_feed import Tick
from arthabot.risk import RiskConfig, RiskEngine, TradeProposal
from arthabot.runtime_pipeline import HermesAdapter, PaperRuntimePipeline
from arthabot.strategies import TradeCandidate


def make_pipeline(tmp_path) -> PaperRuntimePipeline:
    return PaperRuntimePipeline(
        trading_date=date(2026, 1, 5),
        starting_capital=Decimal("5000"),
        execution=ExecutionEngine(),
        risk=RiskEngine(
            config=RiskConfig(
                starting_capital=Decimal("5000"),
                max_risk_per_trade_pct=Decimal("0.01"),
                max_daily_loss_pct=Decimal("0.03"),
                min_allocation_pct=Decimal("0.05"),
                max_trades_per_day=3,
                quote_max_age_seconds=3,
                square_off_time="15:15",
            ),
            brokerage=BrokerageCalculator(BrokerageConfig()),
        ),
        hermes=HermesAdapter(
            proposal_factory=lambda candidate, now: TradeProposal(
                symbol=candidate.symbol,
                direction=candidate.direction,
                entry_price=Decimal("100"),
                stop_loss=Decimal("98"),
                target_price=Decimal("104"),
                confidence=Decimal("0.75"),
                trailing_stop_step=Decimal("1"),
                timestamp=now,
                strategy_version="pipeline-test-v1",
            )
        ),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
        max_tick_age_seconds=3,
    )


def test_paper_runtime_pipeline_executes_fresh_strategy_candidate(tmp_path):
    pipeline = make_pipeline(tmp_path)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    pipeline.on_tick(Tick(symbol="INFY", price=Decimal("100"), volume=1000, timestamp=now))
    result = pipeline.process_candidate(
        TradeCandidate(
            symbol="INFY",
            direction=Direction.LONG,
            score=Decimal("0.02"),
            rationale="Momentum breakout.",
        ),
        now=now,
    )

    assert result is not None
    assert result.simulated
    assert pipeline.daily_report().summarize()["accepted_trades"] == 1
    assert [event.event_type for event in pipeline.audit.read_all()] == [
        "decision",
        "risk_approved",
        "paper_signal_executed",
    ]


def test_paper_runtime_pipeline_audits_risk_rejection_for_stale_quote(tmp_path):
    pipeline = make_pipeline(tmp_path)
    now = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)

    pipeline.on_tick(Tick(symbol="INFY", price=Decimal("100"), volume=1000, timestamp=now - timedelta(seconds=10)))
    result = pipeline.process_candidate(
        TradeCandidate(
            symbol="INFY",
            direction=Direction.LONG,
            score=Decimal("0.02"),
            rationale="Momentum breakout.",
        ),
        now=now,
    )

    assert result is None
    assert pipeline.daily_report().summarize()["rejected_trades"] == 1
    assert pipeline.audit.read_all()[-1].payload["reason_code"] == "STALE_TICK"

