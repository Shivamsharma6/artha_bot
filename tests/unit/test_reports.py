from decimal import Decimal

from arthabot.reporting import DailyReport, TradeRecord


def test_daily_report_includes_costs_rejections_and_net_result():
    report = DailyReport(
        date="2026-01-05",
        starting_capital=Decimal("5000"),
        trades=[
            TradeRecord(symbol="INFY", gross_pnl=Decimal("20"), total_costs=Decimal("5"), accepted=True),
            TradeRecord(symbol="TCS", gross_pnl=Decimal("0"), total_costs=Decimal("0"), accepted=False),
        ],
    )

    summary = report.summarize()

    assert summary["gross_pnl"] == Decimal("20")
    assert summary["total_costs"] == Decimal("5")
    assert summary["net_pnl"] == Decimal("15")
    assert summary["accepted_trades"] == 1
    assert summary["rejected_trades"] == 1
    assert summary["ending_capital"] == Decimal("5015")

