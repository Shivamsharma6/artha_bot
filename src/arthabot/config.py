from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from arthabot.common import Mode


def parse_market_time(value: str | time) -> time:
    if isinstance(value, time):
        return value
    return datetime.strptime(value, "%H:%M").time()


@dataclass(frozen=True)
class RuntimeRiskConfig:
    starting_capital: Decimal
    max_risk_per_trade_pct: Decimal
    max_daily_loss_pct: Decimal
    min_allocation_pct: Decimal
    max_trades_per_day: int
    quote_max_age_seconds: int
    square_off_time: str
    leverage_allowed: bool


@dataclass(frozen=True)
class RuntimeModeConfig:
    default_mode: Mode
    live_enabled: bool
    requires_human_live_approval: bool


@dataclass(frozen=True)
class RuntimeConfig:
    risk: RuntimeRiskConfig
    mode: RuntimeModeConfig


def load_runtime_config(config_dir: str | Path) -> RuntimeConfig:
    root = Path(config_dir)
    risk = _read_yaml(root / "risk.yaml")
    mode = _read_yaml(root / "modes.yaml")
    runtime = RuntimeConfig(
        risk=RuntimeRiskConfig(
            starting_capital=Decimal(str(risk["starting_capital"])),
            max_risk_per_trade_pct=Decimal(str(risk["max_risk_per_trade_pct"])),
            max_daily_loss_pct=Decimal(str(risk["max_daily_loss_pct"])),
            min_allocation_pct=Decimal(str(risk["min_allocation_pct"])),
            max_trades_per_day=int(risk["max_trades_per_day"]),
            quote_max_age_seconds=int(risk["quote_max_age_seconds"]),
            square_off_time=str(risk["square_off_time"]),
            leverage_allowed=bool(risk["leverage_allowed"]),
        ),
        mode=RuntimeModeConfig(
            default_mode=Mode(str(mode["default_mode"])),
            live_enabled=bool(mode["live_enabled"]),
            requires_human_live_approval=bool(mode["requires_human_live_approval"]),
        ),
    )
    if runtime.mode.default_mode == Mode.LIVE:
        raise ValueError("default mode must not be LIVE")
    if runtime.risk.leverage_allowed:
        raise ValueError("leverage must remain disabled in the current version")
    return runtime


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data
