from datetime import date, datetime, time, timezone

import pytest

from arthabot.market_eligibility import (
    MarketEligibilityConfig,
    MarketEligibilityGuard,
    load_market_eligibility_config,
)


def _config() -> MarketEligibilityConfig:
    return MarketEligibilityConfig(
        timezone="Asia/Kolkata",
        session_open=time(9, 15),
        session_close=time(15, 30),
        holidays=frozenset({date(2026, 1, 26)}),
        corporate_action_fail_closed=True,
    )


def test_market_eligibility_accepts_open_nse_session_after_timezone_conversion():
    guard = MarketEligibilityGuard(
        config=_config(),
        corporate_action_provider=lambda symbol, trading_date: False,
    )

    decision = guard.evaluate_market(now=datetime(2026, 1, 5, 4, 0, tzinfo=timezone.utc))

    assert decision.allowed is True
    assert decision.reason_code == "MARKET_ELIGIBLE"


@pytest.mark.parametrize(
    ("now", "reason_code"),
    [
        (datetime(2026, 1, 4, 10, 0, tzinfo=timezone.utc), "MARKET_WEEKEND"),
        (datetime(2026, 1, 26, 4, 0, tzinfo=timezone.utc), "MARKET_HOLIDAY"),
        (datetime(2026, 1, 5, 3, 0, tzinfo=timezone.utc), "MARKET_SESSION_CLOSED"),
        (datetime(2026, 1, 5, 11, 0, tzinfo=timezone.utc), "MARKET_SESSION_CLOSED"),
    ],
)
def test_market_eligibility_rejects_closed_market_context(now, reason_code):
    decision = MarketEligibilityGuard(
        config=_config(),
        corporate_action_provider=lambda symbol, trading_date: False,
    ).evaluate_market(now=now)

    assert decision.allowed is False
    assert decision.reason_code == reason_code


def test_market_eligibility_rejects_active_corporate_action():
    guard = MarketEligibilityGuard(
        config=_config(),
        corporate_action_provider=lambda symbol, trading_date: symbol == "INFY",
    )

    decision = guard.evaluate_symbol(
        symbol="INFY",
        now=datetime(2026, 1, 5, 4, 0, tzinfo=timezone.utc),
    )

    assert decision.allowed is False
    assert decision.reason_code == "CORPORATE_ACTION_ACTIVE"
    assert decision.symbol == "INFY"


def test_market_eligibility_fails_closed_when_corporate_action_state_is_unknown():
    def failing_provider(symbol, trading_date):
        raise RuntimeError("provider unavailable")

    decision = MarketEligibilityGuard(
        config=_config(),
        corporate_action_provider=failing_provider,
    ).evaluate_symbol(
        symbol="TCS",
        now=datetime(2026, 1, 5, 4, 0, tzinfo=timezone.utc),
    )

    assert decision.allowed is False
    assert decision.reason_code == "CORPORATE_ACTION_STATE_UNKNOWN"


def test_market_eligibility_config_loads_repository_policy():
    config = load_market_eligibility_config("config/market.yaml")

    assert config.timezone == "Asia/Kolkata"
    assert config.session_open == time(9, 15)
    assert config.session_close == time(15, 30)
    assert config.corporate_action_fail_closed is True


def test_market_eligibility_config_rejects_invalid_session(tmp_path):
    path = tmp_path / "market.yaml"
    path.write_text(
        """
timezone: Asia/Kolkata
session_open: "15:30"
session_close: "09:15"
holidays: []
corporate_action_fail_closed: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="session_close must be after session_open"):
        load_market_eligibility_config(path)
