from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from arthabot.common import Direction, Mode
from arthabot.config import load_runtime_config
from arthabot.reconciliation import AccountSnapshot, BrokerPosition, InternalPosition, ReconciliationService


def test_runtime_config_defaults_to_non_live_mode_and_disables_live():
    config = load_runtime_config("config")

    assert config.mode.default_mode in {Mode.BACKTEST, Mode.PAPER}
    assert config.mode.live_enabled is False
    assert config.risk.leverage_allowed is False
    assert config.risk.starting_capital == Decimal("5000")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trailing_stop_step", "0"),
        ("trailing_stop_step", "-1"),
        ("trailing_stop_cooldown_seconds", -1),
        ("trailing_stop_max_modifications", 0),
    ],
)
def test_runtime_config_rejects_invalid_enabled_trailing_stop_settings(tmp_path, field, value):
    risk = yaml.safe_load(Path("config/risk.yaml").read_text(encoding="utf-8"))
    modes = yaml.safe_load(Path("config/modes.yaml").read_text(encoding="utf-8"))
    risk[field] = value
    (tmp_path / "risk.yaml").write_text(yaml.safe_dump(risk), encoding="utf-8")
    (tmp_path / "modes.yaml").write_text(yaml.safe_dump(modes), encoding="utf-8")
    with pytest.raises(ValueError, match="trailing stop"):
        load_runtime_config(tmp_path)


def test_reconciliation_passes_matching_cash_and_positions():
    service = ReconciliationService(cash_tolerance=Decimal("1.00"))

    result = service.reconcile(
        account=AccountSnapshot(available_cash=Decimal("4999.50")),
        internal_cash=Decimal("5000"),
        broker_positions=[
            BrokerPosition(symbol="INFY", quantity=2, direction=Direction.LONG),
        ],
        internal_positions=[
            InternalPosition(symbol="INFY", quantity=2, direction=Direction.LONG),
        ],
    )

    assert result.ok
    assert result.reason_code == "RECONCILED"


def test_reconciliation_fails_closed_on_position_mismatch():
    service = ReconciliationService()

    result = service.reconcile(
        account=AccountSnapshot(available_cash=Decimal("5000")),
        internal_cash=Decimal("5000"),
        broker_positions=[
            BrokerPosition(symbol="INFY", quantity=1, direction=Direction.LONG),
        ],
        internal_positions=[
            InternalPosition(symbol="INFY", quantity=2, direction=Direction.LONG),
        ],
    )

    assert not result.ok
    assert result.reason_code == "POSITION_MISMATCH"
    assert result.must_stop_trading


def test_reconciliation_requires_verified_account_balance():
    service = ReconciliationService()

    with pytest.raises(ValueError, match="account balance"):
        service.reconcile(
            account=None,
            internal_cash=Decimal("5000"),
            broker_positions=[],
            internal_positions=[],
        )
