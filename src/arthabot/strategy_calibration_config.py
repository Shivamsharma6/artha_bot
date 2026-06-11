from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import yaml

from arthabot.backtest import BacktestExecutionEngine, HistoricalDataset
from arthabot.brokerage import BrokerageCalculator, BrokerageConfig
from arthabot.data_providers import HistoricalProviderRequest
from arthabot.historical_strategy_backtest import (
    HistoricalSignalEngine,
    build_calibration_inputs_from_historical_backtests,
)
from arthabot.strategy_calibration_factory import StrategyCalibrationInputs
from arthabot.strategy_engines import BreakoutSignalEngine, ReversalSignalEngine, VolumeMoverSignalEngine
from arthabot.strategies import MomentumSignalEngine


SUPPORTED_CALIBRATION_ENGINES = {"momentum", "breakout", "reversal", "volume_mover"}


class HistoricalProvider(Protocol):
    def fetch(self, request: HistoricalProviderRequest) -> HistoricalDataset:
        ...


@dataclass(frozen=True)
class StrategyCalibrationVersionConfig:
    version: str
    engine: str
    symbols: tuple[str, ...]
    resolution: str
    from_time: datetime
    to_time: datetime
    quantity: int
    walk_forward_windows: int
    out_of_sample_tested: bool
    survivorship_bias_checked: bool
    params: dict[str, Any]


@dataclass(frozen=True)
class StrategyCalibrationConfig:
    versions: tuple[StrategyCalibrationVersionConfig, ...]


def load_strategy_calibration_config(path: str | Path) -> StrategyCalibrationConfig:
    data = _read_yaml(Path(path))
    raw_versions = ((data.get("calibration") or {}).get("versions") or [])
    if not isinstance(raw_versions, list):
        raise ValueError("calibration.versions must be a list")
    versions = tuple(_parse_version_config(raw) for raw in raw_versions)
    if not versions:
        raise ValueError("at least one calibration version is required")
    return StrategyCalibrationConfig(versions=versions)


def build_historical_calibration_inputs_from_config(
    *,
    config: StrategyCalibrationConfig,
    historical_provider: HistoricalProvider,
    starting_capital: Decimal,
    brokerage_config: BrokerageConfig,
) -> StrategyCalibrationInputs:
    datasets_by_version: dict[str, list[HistoricalDataset]] = {}
    signal_engines_by_version: dict[str, HistoricalSignalEngine] = {}
    execution_engines_by_version: dict[str, BacktestExecutionEngine] = {}
    quantity_by_version: dict[str, int] = {}
    walk_forward_windows_by_version: dict[str, int] = {}
    out_of_sample_tested_by_version: dict[str, bool] = {}
    survivorship_bias_checked_by_version: dict[str, bool] = {}

    for version in config.versions:
        datasets_by_version[version.version] = [
            historical_provider.fetch(
                HistoricalProviderRequest(
                    symbol=symbol,
                    resolution=version.resolution,
                    from_time=version.from_time,
                    to_time=version.to_time,
                )
            )
            for symbol in version.symbols
        ]
        signal_engines_by_version[version.version] = _build_signal_engine(version)
        execution_engines_by_version[version.version] = BacktestExecutionEngine(
            starting_capital=starting_capital,
            brokerage=BrokerageCalculator(brokerage_config),
        )
        quantity_by_version[version.version] = version.quantity
        walk_forward_windows_by_version[version.version] = version.walk_forward_windows
        out_of_sample_tested_by_version[version.version] = version.out_of_sample_tested
        survivorship_bias_checked_by_version[version.version] = version.survivorship_bias_checked

    return build_calibration_inputs_from_historical_backtests(
        datasets_by_version=datasets_by_version,
        signal_engines_by_version=signal_engines_by_version,
        execution_engines_by_version=execution_engines_by_version,
        quantity_by_version=quantity_by_version,
        walk_forward_windows_by_version=walk_forward_windows_by_version,
        out_of_sample_tested_by_version=out_of_sample_tested_by_version,
        survivorship_bias_checked_by_version=survivorship_bias_checked_by_version,
    )


def _parse_version_config(raw: object) -> StrategyCalibrationVersionConfig:
    if not isinstance(raw, dict):
        raise ValueError("calibration version entries must be mappings")
    engine = str(raw.get("engine", ""))
    if engine not in SUPPORTED_CALIBRATION_ENGINES:
        raise ValueError(f"unsupported calibration engine: {engine}")
    if "from_time" not in raw or "to_time" not in raw:
        raise ValueError("from_time and to_time are required for calibration backtests")
    symbols = tuple(str(symbol) for symbol in raw.get("symbols", []))
    if not symbols:
        raise ValueError("at least one calibration symbol is required")
    quantity = int(raw.get("quantity", 0))
    if quantity <= 0:
        raise ValueError("calibration quantity must be positive")
    from_time = datetime.fromisoformat(str(raw["from_time"]))
    to_time = datetime.fromisoformat(str(raw["to_time"]))
    if to_time <= from_time:
        raise ValueError("calibration to_time must be after from_time")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("calibration params must be a mapping")
    return StrategyCalibrationVersionConfig(
        version=str(raw["version"]),
        engine=engine,
        symbols=symbols,
        resolution=str(raw["resolution"]),
        from_time=from_time,
        to_time=to_time,
        quantity=quantity,
        walk_forward_windows=int(raw["walk_forward_windows"]),
        out_of_sample_tested=bool(raw["out_of_sample_tested"]),
        survivorship_bias_checked=bool(raw["survivorship_bias_checked"]),
        params=dict(params),
    )


def _build_signal_engine(version: StrategyCalibrationVersionConfig) -> HistoricalSignalEngine:
    if version.engine == "momentum":
        return MomentumSignalEngine(min_move_pct=Decimal(str(version.params["min_move_pct"])))
    if version.engine == "breakout":
        return BreakoutSignalEngine(
            resistance_by_symbol={
                str(symbol): Decimal(str(value))
                for symbol, value in (version.params.get("resistance_by_symbol") or {}).items()
            },
            support_by_symbol={
                str(symbol): Decimal(str(value))
                for symbol, value in (version.params.get("support_by_symbol") or {}).items()
            },
            min_breakout_pct=Decimal(str(version.params["min_breakout_pct"])),
        )
    if version.engine == "reversal":
        return ReversalSignalEngine(min_reversal_pct=Decimal(str(version.params["min_reversal_pct"])))
    if version.engine == "volume_mover":
        return VolumeMoverSignalEngine(
            min_volume=int(version.params["min_volume"]),
            min_move_pct=Decimal(str(version.params["min_move_pct"])),
        )
    raise ValueError(f"unsupported calibration engine: {version.engine}")


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data
