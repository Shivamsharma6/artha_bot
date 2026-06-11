from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from pathlib import Path


@dataclass(frozen=True)
class StrategyCalibrationEvidence:
    strategy_version: str
    data_start: date
    data_end: date
    data_resolution: str
    symbols: tuple[str, ...]
    brokerage_and_slippage_included: bool
    walk_forward_windows: int
    out_of_sample_tested: bool
    survivorship_bias_checked: bool
    net_profit: Decimal
    expectancy: Decimal
    max_drawdown: Decimal
    rejected_trades: int

    def __post_init__(self) -> None:
        if self.data_end <= self.data_start:
            raise ValueError("data_end must be after data_start")

    @property
    def data_years(self) -> Decimal:
        days = (self.data_end - self.data_start).days
        return Decimal(days) / Decimal("365")


@dataclass(frozen=True)
class CalibrationThresholds:
    min_data_years: Decimal
    min_walk_forward_windows: int
    max_drawdown: Decimal
    min_expectancy: Decimal


@dataclass(frozen=True)
class StrategyCalibrationResult:
    strategy_version: str
    promotable: bool
    reason_codes: tuple[str, ...]


class StrategyCalibrationGate:
    def __init__(self, *, thresholds: CalibrationThresholds) -> None:
        self.thresholds = thresholds

    def evaluate(self, evidence: StrategyCalibrationEvidence) -> StrategyCalibrationResult:
        reasons: list[str] = []
        if evidence.data_years < self.thresholds.min_data_years:
            reasons.append("INSUFFICIENT_DATA_DEPTH")
        if evidence.data_resolution == "unknown":
            reasons.append("UNKNOWN_DATA_RESOLUTION")
        if not evidence.brokerage_and_slippage_included:
            reasons.append("COSTS_NOT_INCLUDED")
        if evidence.walk_forward_windows < self.thresholds.min_walk_forward_windows:
            reasons.append("INSUFFICIENT_WALK_FORWARD_WINDOWS")
        if not evidence.out_of_sample_tested:
            reasons.append("OUT_OF_SAMPLE_MISSING")
        if not evidence.survivorship_bias_checked:
            reasons.append("SURVIVORSHIP_CHECK_MISSING")
        if evidence.net_profit <= 0:
            reasons.append("NON_POSITIVE_NET_PROFIT")
        if evidence.expectancy < self.thresholds.min_expectancy:
            reasons.append("EXPECTANCY_TOO_LOW")
        if evidence.max_drawdown > self.thresholds.max_drawdown:
            reasons.append("DRAWDOWN_TOO_HIGH")
        if evidence.rejected_trades <= 0:
            reasons.append("NO_REJECTED_TRADE_LOGGING_EVIDENCE")

        if reasons:
            return StrategyCalibrationResult(
                strategy_version=evidence.strategy_version,
                promotable=False,
                reason_codes=tuple(reasons),
            )
        return StrategyCalibrationResult(
            strategy_version=evidence.strategy_version,
            promotable=True,
            reason_codes=("CALIBRATION_PASSED",),
        )


@dataclass(frozen=True)
class StrategyCalibrationArtifact:
    evidence: StrategyCalibrationEvidence
    result: StrategyCalibrationResult


class StrategyCalibrationArtifactStore:
    def __init__(self, artifact_dir: str | Path) -> None:
        self.artifact_dir = Path(artifact_dir)

    def write(self, *, evidence: StrategyCalibrationEvidence, result: StrategyCalibrationResult) -> Path:
        if evidence.strategy_version != result.strategy_version:
            raise ValueError("calibration result strategy_version must match evidence")
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(evidence.strategy_version)
        payload = {
            "evidence": {
                "strategy_version": evidence.strategy_version,
                "data_start": evidence.data_start.isoformat(),
                "data_end": evidence.data_end.isoformat(),
                "data_resolution": evidence.data_resolution,
                "symbols": list(evidence.symbols),
                "brokerage_and_slippage_included": evidence.brokerage_and_slippage_included,
                "walk_forward_windows": evidence.walk_forward_windows,
                "out_of_sample_tested": evidence.out_of_sample_tested,
                "survivorship_bias_checked": evidence.survivorship_bias_checked,
                "net_profit": str(evidence.net_profit),
                "expectancy": str(evidence.expectancy),
                "max_drawdown": str(evidence.max_drawdown),
                "rejected_trades": evidence.rejected_trades,
                "data_years": str(evidence.data_years),
            },
            "result": {
                "strategy_version": result.strategy_version,
                "promotable": result.promotable,
                "reason_codes": list(result.reason_codes),
            },
        }
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return path

    def read(self, strategy_version: str) -> StrategyCalibrationArtifact:
        data = json.loads(self._path_for(strategy_version).read_text(encoding="utf-8"))
        raw_evidence = data["evidence"]
        raw_result = data["result"]
        return StrategyCalibrationArtifact(
            evidence=StrategyCalibrationEvidence(
                strategy_version=str(raw_evidence["strategy_version"]),
                data_start=date.fromisoformat(str(raw_evidence["data_start"])),
                data_end=date.fromisoformat(str(raw_evidence["data_end"])),
                data_resolution=str(raw_evidence["data_resolution"]),
                symbols=tuple(str(symbol) for symbol in raw_evidence["symbols"]),
                brokerage_and_slippage_included=bool(raw_evidence["brokerage_and_slippage_included"]),
                walk_forward_windows=int(raw_evidence["walk_forward_windows"]),
                out_of_sample_tested=bool(raw_evidence["out_of_sample_tested"]),
                survivorship_bias_checked=bool(raw_evidence["survivorship_bias_checked"]),
                net_profit=Decimal(str(raw_evidence["net_profit"])),
                expectancy=Decimal(str(raw_evidence["expectancy"])),
                max_drawdown=Decimal(str(raw_evidence["max_drawdown"])),
                rejected_trades=int(raw_evidence["rejected_trades"]),
            ),
            result=StrategyCalibrationResult(
                strategy_version=str(raw_result["strategy_version"]),
                promotable=bool(raw_result["promotable"]),
                reason_codes=tuple(str(reason) for reason in raw_result["reason_codes"]),
            ),
        )

    def _path_for(self, strategy_version: str) -> Path:
        safe_name = strategy_version.replace("/", "_")
        return self.artifact_dir / f"{safe_name}-calibration.json"
