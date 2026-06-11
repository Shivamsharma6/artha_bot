from decimal import Decimal

from arthabot.backtest import BacktestReport
from arthabot.common import Mode
from arthabot.learning_comparison import LearningComparisonReport
from arthabot.strategy_comparison import StrategyComparisonHarness, StrategyResult


def make_report(net: str, drawdown: str, win_rate: str = "0.50") -> BacktestReport:
    return BacktestReport(
        net_profit=Decimal(net),
        gross_profit=Decimal(net),
        total_costs=Decimal("0"),
        win_rate=Decimal(win_rate),
        number_of_trades=10,
        number_of_rejected_trades=1,
        max_drawdown=Decimal(drawdown),
    )


def test_strategy_comparison_ranks_by_net_profit_then_drawdown():
    harness = StrategyComparisonHarness(max_drawdown_limit=Decimal("100"))
    results = [
        StrategyResult(strategy_version="v1", report=make_report("50", "20")),
        StrategyResult(strategy_version="v2", report=make_report("50", "10")),
        StrategyResult(strategy_version="v3", report=make_report("40", "5")),
    ]

    comparison = harness.compare(results)

    assert comparison.best.strategy_version == "v2"
    assert comparison.rankings[0].strategy_version == "v2"
    assert comparison.rankings[1].strategy_version == "v1"


def test_strategy_comparison_marks_drawdown_breach_as_not_promotable():
    harness = StrategyComparisonHarness(max_drawdown_limit=Decimal("25"))
    comparison = harness.compare([
        StrategyResult(strategy_version="risky", report=make_report("100", "50")),
    ])

    assert comparison.rankings[0].promotable is False
    assert comparison.rankings[0].reason_code == "DRAWDOWN_LIMIT_BREACHED"


def test_learning_comparison_report_proposes_paper_backtest_rerun_for_degraded_strategy():
    comparison = StrategyComparisonHarness(max_drawdown_limit=Decimal("100")).compare(
        [
            StrategyResult(strategy_version="v1", report=make_report("10", "20")),
            StrategyResult(strategy_version="v2", report=make_report("50", "10")),
        ]
    )

    summary = LearningComparisonReport(comparison=comparison).summarize()

    assert summary.best_strategy_version == "v2"
    assert summary.proposed_change.mode == Mode.PAPER
    assert summary.proposed_change.target == "backtest.rerun.v1"

