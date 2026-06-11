from decimal import Decimal

from arthabot.brokerage import BrokerageCalculator, BrokerageConfig, TradeSide


def test_intraday_equity_costs_are_config_based_and_include_break_even():
    config = BrokerageConfig(
        brokerage_rate=Decimal("0.0003"),
        brokerage_cap=Decimal("20"),
        stt_sell_rate=Decimal("0.00025"),
        exchange_txn_rate=Decimal("0.0000322"),
        sebi_turnover_rate=Decimal("0.000001"),
        stamp_buy_rate=Decimal("0.00003"),
        gst_rate=Decimal("0.18"),
        slippage_rate=Decimal("0.0005"),
    )
    calculator = BrokerageCalculator(config)

    estimate = calculator.estimate_intraday_equity(
        side=TradeSide.LONG,
        entry_price=Decimal("100"),
        exit_price=Decimal("101"),
        quantity=10,
    )

    assert estimate.gross_pnl == Decimal("10.00")
    assert estimate.total_charges > Decimal("0")
    assert estimate.net_pnl == estimate.gross_pnl - estimate.total_charges
    assert estimate.break_even_points > Decimal("0")
    assert estimate.slippage > Decimal("0")


def test_cost_model_rejects_non_positive_quantity():
    calculator = BrokerageCalculator(BrokerageConfig())

    try:
        calculator.estimate_intraday_equity(
            side=TradeSide.SHORT,
            entry_price=Decimal("100"),
            exit_price=Decimal("99"),
            quantity=0,
        )
    except ValueError as exc:
        assert "quantity" in str(exc)
    else:
        raise AssertionError("Expected invalid quantity to be rejected")

