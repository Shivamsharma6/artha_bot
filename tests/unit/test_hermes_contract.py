from decimal import Decimal

import pytest
from pydantic import ValidationError

from arthabot.agents.hermes import HermesDecision
from arthabot.common import Direction


def test_hermes_decision_requires_cost_aware_break_even_and_trailing_stop():
    decision = HermesDecision(
        candidate_symbol="RELIANCE",
        direction=Direction.LONG,
        entry_rationale="Breakout with volume expansion and positive news context.",
        entry_price_zone=(Decimal("2500"), Decimal("2510")),
        stop_loss=Decimal("2475"),
        trailing_stop_loss_logic="Step trail every 0.5 percent after price confirms breakout.",
        target_or_exit_logic="Exit at 2R or force square-off before configured intraday deadline.",
        expected_reward_to_risk=Decimal("2.0"),
        cost_aware_break_even=Decimal("2504.50"),
        confidence_score=Decimal("0.72"),
        reasons_to_reject=[],
        data_used=["ohlcv", "volume", "news_sentiment"],
        timestamp="2026-01-05T10:00:00+05:30",
        strategy_model_version="hermes-test-v1",
    )

    assert decision.candidate_symbol == "RELIANCE"
    assert decision.cost_aware_break_even > decision.entry_price_zone[0]


def test_hermes_decision_rejects_missing_trailing_stop_logic():
    with pytest.raises(ValidationError):
        HermesDecision(
            candidate_symbol="RELIANCE",
            direction=Direction.SHORT,
            entry_rationale="Weak reversal.",
            entry_price_zone=(Decimal("2500"), Decimal("2510")),
            stop_loss=Decimal("2520"),
            trailing_stop_loss_logic="",
            target_or_exit_logic="Exit by square-off.",
            expected_reward_to_risk=Decimal("1.5"),
            cost_aware_break_even=Decimal("2496"),
            confidence_score=Decimal("0.70"),
            reasons_to_reject=[],
            data_used=["ohlcv"],
            timestamp="2026-01-05T10:00:00+05:30",
            strategy_model_version="hermes-test-v1",
        )

