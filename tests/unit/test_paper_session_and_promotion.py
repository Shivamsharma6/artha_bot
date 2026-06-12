from datetime import date
from decimal import Decimal

from arthabot.common import Direction
from arthabot.execution import ExecutionEngine
from arthabot.live_promotion import LivePromotionChecklist, LivePromotionGate
from arthabot.paper_session import PaperSession, PaperTradeIntent
from arthabot.reporting import TradeRecord


def test_paper_session_records_simulated_fills_and_daily_report():
    execution = ExecutionEngine()
    session = PaperSession(
        trading_date=date(2026, 1, 5),
        starting_capital=Decimal("5000"),
        execution=execution,
    )

    result = session.submit(
        PaperTradeIntent(
            symbol="INFY",
            direction=Direction.LONG,
            quantity=2,
            entry_price=Decimal("100"),
            exit_price=Decimal("102"),
            total_costs=Decimal("1.50"),
        )
    )
    report = session.daily_report().summarize()

    assert result.simulated
    assert execution.real_orders_submitted == []
    assert report["accepted_trades"] == 1
    assert report["net_pnl"] == Decimal("0")


def test_paper_session_records_rejected_trade_without_execution():
    execution = ExecutionEngine()
    session = PaperSession(
        trading_date=date(2026, 1, 5),
        starting_capital=Decimal("5000"),
        execution=execution,
    )

    result = session.reject(symbol="INFY", reason="STALE_MARKET_DATA")
    report = session.daily_report().summarize()

    assert result is None
    assert execution.real_orders_submitted == []
    assert report["rejected_trades"] == 1


def test_paper_session_restores_persisted_trade_ledger():
    session = PaperSession(
        trading_date=date(2026, 6, 12),
        starting_capital=Decimal("5000"),
        execution=ExecutionEngine(),
    )

    session.restore_trades(
        [TradeRecord(symbol="INFY", gross_pnl=Decimal("25"), total_costs=Decimal("5"), accepted=True)]
    )

    assert session.daily_report().summarize()["ending_capital"] == Decimal("5020")


def test_live_promotion_gate_requires_all_safety_conditions_and_human_approval():
    checklist = LivePromotionChecklist(
        backtested=True,
        three_years_where_available=True,
        brokerage_and_slippage_included=True,
        positive_expectancy_after_costs=True,
        drawdown_within_limit=True,
        paper_traded_successfully=True,
        no_execution_bugs=True,
        no_order_reconciliation_bugs=True,
        no_risk_rule_violations=True,
        no_stale_data_issues=True,
        no_live_safety_issues=True,
        human_approval=False,
    )

    decision = LivePromotionGate().evaluate(checklist)

    assert not decision.approved
    assert decision.reason_code == "HUMAN_APPROVAL_REQUIRED"


def test_live_promotion_gate_approves_only_complete_checklist():
    checklist = LivePromotionChecklist.all_clear()

    decision = LivePromotionGate().evaluate(checklist)

    assert decision.approved
    assert decision.reason_code == "LIVE_PROMOTION_APPROVED"
