from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import yaml

from arthabot.data import MarketSnapshot
from arthabot.strategy_engines import BreakoutSignalEngine, ReversalSignalEngine, VolumeMoverSignalEngine
from arthabot.strategies import MomentumSignalEngine, TradeCandidate


SUPPORTED_RUNTIME_ENGINES = {"momentum", "breakout", "reversal", "volume_mover"}


class RuntimeSignalEngine(Protocol):
    def generate(self, snapshots: list[MarketSnapshot]) -> list[TradeCandidate]:
        ...


@dataclass(frozen=True)
class RuntimeStrategyVersionConfig:
    version: str
    engine: str
    enabled: bool
    params: dict[str, Any]


@dataclass(frozen=True)
class RuntimeStrategyConfig:
    versions: tuple[RuntimeStrategyVersionConfig, ...]

    @property
    def enabled_versions(self) -> tuple[RuntimeStrategyVersionConfig, ...]:
        return tuple(version for version in self.versions if version.enabled)


class ConfiguredRuntimeStrategyProvider:
    def __init__(self, *, config: RuntimeStrategyConfig) -> None:
        self.config = config

    def generate(self, snapshots: list[MarketSnapshot]) -> list[TradeCandidate]:
        candidates: list[TradeCandidate] = []
        for version in self.config.enabled_versions:
            engine = _build_engine(version)
            for candidate in engine.generate(snapshots):
                candidates.append(
                    TradeCandidate(
                        symbol=candidate.symbol,
                        direction=candidate.direction,
                        score=candidate.score,
                        rationale=candidate.rationale,
                        strategy_version=version.version,
                    )
                )
        return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)


def load_runtime_strategy_config(path: str | Path) -> RuntimeStrategyConfig:
    data = _read_yaml(Path(path))
    raw_versions = ((data.get("runtime_strategies") or {}).get("versions") or [])
    if not isinstance(raw_versions, list):
        raise ValueError("runtime_strategies.versions must be a list")
    versions = tuple(_parse_version(raw) for raw in raw_versions)
    if not versions:
        raise ValueError("at least one runtime strategy version is required")
    return RuntimeStrategyConfig(versions=versions)


def _parse_version(raw: object) -> RuntimeStrategyVersionConfig:
    if not isinstance(raw, dict):
        raise ValueError("runtime strategy entries must be mappings")
    engine = str(raw.get("engine", ""))
    if engine not in SUPPORTED_RUNTIME_ENGINES:
        raise ValueError(f"unsupported runtime strategy engine: {engine}")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("runtime strategy params must be a mapping")
    return RuntimeStrategyVersionConfig(
        version=str(raw["version"]),
        engine=engine,
        enabled=bool(raw.get("enabled", True)),
        params=dict(params),
    )


def _build_engine(version: RuntimeStrategyVersionConfig) -> RuntimeSignalEngine:
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
    raise ValueError(f"unsupported runtime strategy engine: {version.engine}")


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data
