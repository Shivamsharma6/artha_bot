from datetime import datetime, timedelta, timezone
from decimal import Decimal

from arthabot.common import Direction
from arthabot.trailing_stop import TrailingStopPolicy, TrailingStopState


def test_long_trailing_stop_moves_only_after_step_and_cooldown():
    policy = TrailingStopPolicy(step=Decimal("1.00"), cooldown_seconds=30, max_modifications_per_trade=3)
    base_time = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
    state = TrailingStopState(
        symbol="INFY",
        direction=Direction.LONG,
        current_stop=Decimal("98"),
        last_reference_price=Decimal("100"),
        last_modified_at=base_time,
        modifications=0,
    )

    too_soon = policy.propose_update(state, price=Decimal("101.50"), now=base_time + timedelta(seconds=10))
    allowed = policy.propose_update(state, price=Decimal("101.50"), now=base_time + timedelta(seconds=31))

    assert too_soon is None
    assert allowed is not None
    assert allowed.current_stop == Decimal("99.50")
    assert allowed.modifications == 1


def test_trailing_stop_never_widens_risk_for_short():
    policy = TrailingStopPolicy(step=Decimal("1.00"), cooldown_seconds=0, max_modifications_per_trade=3)
    state = TrailingStopState(
        symbol="TCS",
        direction=Direction.SHORT,
        current_stop=Decimal("102"),
        last_reference_price=Decimal("100"),
        last_modified_at=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        modifications=0,
    )

    update = policy.propose_update(state, price=Decimal("101"), now=datetime(2026, 1, 5, 10, 1, tzinfo=timezone.utc))

    assert update is None


def test_trailing_stop_stops_after_modification_limit():
    policy = TrailingStopPolicy(step=Decimal("1.00"), cooldown_seconds=0, max_modifications_per_trade=1)
    state = TrailingStopState(
        symbol="INFY",
        direction=Direction.LONG,
        current_stop=Decimal("98"),
        last_reference_price=Decimal("100"),
        last_modified_at=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        modifications=1,
    )

    update = policy.propose_update(state, price=Decimal("103"), now=datetime(2026, 1, 5, 10, 1, tzinfo=timezone.utc))

    assert update is None

