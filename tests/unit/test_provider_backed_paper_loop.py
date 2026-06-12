from datetime import date, datetime, time, timezone
from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.brokerage import BrokerageCalculator, BrokerageConfig
from arthabot.common import Direction
from arthabot.data import MarketSnapshot
from arthabot.execution import ExecutionEngine
from arthabot.live_feed import Tick
from arthabot.position_tracker import PositionTracker
from arthabot.provider_paper_loop import ProviderBackedPaperLoop
from arthabot.risk import RiskConfig, RiskEngine, TradeProposal
from arthabot.runtime_market_provider import RuntimeMarketSnapshotProvider, RuntimeStrategyCandidateComposer
from arthabot.runtime_strategy_provider import ConfiguredRuntimeStrategyProvider, load_runtime_strategy_config
from arthabot.runtime_pipeline import HermesAdapter, PaperRuntimePipeline
from arthabot.scheduler import ScheduledJob, SchedulerRunner, TimeOfDaySchedule
from arthabot.strategies import TradeCandidate


def make_pipeline(tmp_path, *, calls: list[str] | None = None) -> PaperRuntimePipeline:
    def proposal_factory(candidate: TradeCandidate, now: datetime) -> TradeProposal:
        if calls is not None:
            calls.append(candidate.symbol)
        return TradeProposal(
            symbol=candidate.symbol,
            direction=candidate.direction,
            entry_price=Decimal("100"),
            stop_loss=Decimal("98"),
            target_price=Decimal("104"),
            confidence=Decimal("0.75"),
            trailing_stop_step=Decimal("1"),
            timestamp=now,
            strategy_version=(
                candidate.strategy_version
                if candidate.strategy_version != "unknown"
                else "provider-loop-test-v1"
            ),
        )

    broker_calc = BrokerageCalculator(BrokerageConfig())
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
            brokerage=broker_calc,
        ),
        hermes=HermesAdapter(proposal_factory=proposal_factory),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
        max_tick_age_seconds=3,
        position_tracker=PositionTracker(
            starting_capital=Decimal("5000"),
            brokerage=broker_calc,
        ),
    )


def test_provider_backed_paper_loop_stops_before_signals_when_critical_provider_job_fails(tmp_path):
    audit = JsonlAuditStore(tmp_path / "loop-audit.jsonl")
    hermes_calls: list[str] = []
    pipeline = make_pipeline(tmp_path, calls=hermes_calls)
    now = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)

    failing_job = ScheduledJob(
        name="instrument-refresh",
        schedule=TimeOfDaySchedule(run_at=time(8, 30)),
        action=lambda _: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
        critical=True,
    )

    result = ProviderBackedPaperLoop(
        scheduler=SchedulerRunner(audit=audit),
        pipeline=pipeline,
        audit=audit,
    ).run(
        jobs=[failing_job],
        candidates=[
            TradeCandidate(
                symbol="INFY",
                direction=Direction.LONG,
                score=Decimal("0.02"),
                rationale="Momentum breakout.",
            )
        ],
        now=now,
    )

    assert result.must_stop_trading
    assert result.reason_code == "SCHEDULED_JOB_FAILED"
    assert len(result.job_results) == 1
    assert result.signal_results == []
    assert hermes_calls == []
    assert audit.read_all()[-1].event_type == "provider_paper_loop_stopped"


def test_provider_backed_paper_loop_processes_signals_after_provider_jobs_pass(tmp_path):
    audit = JsonlAuditStore(tmp_path / "loop-audit.jsonl")
    pipeline = make_pipeline(tmp_path)
    now = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)
    pipeline.on_tick(Tick(symbol="INFY", price=Decimal("100"), volume=1000, timestamp=now))

    passing_job = ScheduledJob(
        name="news-ingest",
        schedule=TimeOfDaySchedule(run_at=time(8, 45)),
        action=lambda _: {"article_count": 1},
        critical=False,
    )

    result = ProviderBackedPaperLoop(
        scheduler=SchedulerRunner(audit=audit),
        pipeline=pipeline,
        audit=audit,
    ).run(
        jobs=[passing_job],
        candidates=[
            TradeCandidate(
                symbol="INFY",
                direction=Direction.LONG,
                score=Decimal("0.02"),
                rationale="Momentum breakout.",
            )
        ],
        now=now,
    )

    assert not result.must_stop_trading
    assert result.reason_code == "PROVIDER_JOBS_PASSED"
    assert len(result.job_results) == 1
    assert len(result.signal_results) == 1
    assert result.signal_results[0] is not None
    assert pipeline.daily_report()["accepted_trades"] == 1


def test_provider_backed_paper_loop_accepts_configured_runtime_strategy_candidates(tmp_path):
    audit = JsonlAuditStore(tmp_path / "loop-audit.jsonl")
    pipeline = make_pipeline(tmp_path)
    now = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)
    pipeline.on_tick(Tick(symbol="INFY", price=Decimal("100"), volume=1000, timestamp=now))
    strategy_provider = ConfiguredRuntimeStrategyProvider(
        config=load_runtime_strategy_config("config/strategy.yaml")
    )
    candidates = [
        candidate
        for candidate in strategy_provider.generate(
            [
                MarketSnapshot(
                    symbol="INFY",
                    last_price=Decimal("102"),
                    open_price=Decimal("100"),
                    volume=20_000,
                    timestamp=now,
                )
            ]
        )
        if candidate.strategy_version == "momentum-v1"
    ]

    result = ProviderBackedPaperLoop(
        scheduler=SchedulerRunner(audit=audit),
        pipeline=pipeline,
        audit=audit,
    ).run(
        jobs=[
            ScheduledJob(
                name="provider-ok",
                schedule=TimeOfDaySchedule(run_at=time(8, 45)),
                action=lambda _: {"ok": True},
                critical=False,
            )
        ],
        candidates=candidates,
        now=now,
    )

    assert not result.must_stop_trading
    assert result.signal_results[0] is not None
    assert pipeline.audit.read_all()[0].payload["strategy_version"] == "momentum-v1"


def test_provider_backed_paper_loop_uses_top_mover_composer_candidates(tmp_path):
    audit = JsonlAuditStore(tmp_path / "loop-audit.jsonl")
    pipeline = make_pipeline(tmp_path)
    now = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)
    pipeline.on_tick(Tick(symbol="INFY", price=Decimal("100"), volume=1000, timestamp=now))
    composer = RuntimeStrategyCandidateComposer(
        market_provider=RuntimeMarketSnapshotProvider(
            top_movers_client=lambda *, limit: [
                {
                    "symbol": "INFY",
                    "last_price": "102",
                    "open_price": "100",
                    "volume": "20000",
                    "timestamp": now.isoformat(),
                }
            ],
            max_age_seconds=3,
        ),
        strategy_config=load_runtime_strategy_config("config/strategy.yaml"),
    )

    result = ProviderBackedPaperLoop(
        scheduler=SchedulerRunner(audit=audit),
        pipeline=pipeline,
        audit=audit,
    ).run(
        jobs=[],
        candidates=[
            candidate
            for candidate in composer.generate_from_top_movers(limit=10, now=now)
            if candidate.strategy_version == "momentum-v1"
        ],
        now=now,
    )

    assert not result.must_stop_trading
    assert result.signal_results[0] is not None
    assert pipeline.daily_report()["accepted_trades"] == 1
