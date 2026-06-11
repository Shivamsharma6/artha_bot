from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path

from arthabot.audit_store import JsonlAuditStore
from arthabot.live_promotion import LivePromotionDecision, LivePromotionGate
from arthabot.strategy_calibration import StrategyCalibrationArtifactStore
from arthabot.validation import ValidationEvidence, ValidationHarness


@dataclass(frozen=True)
class PaperTradingEvidence:
    successful: bool


@dataclass(frozen=True)
class SafetyIssueEvidence:
    unresolved_execution_bugs: int = 0
    unresolved_order_reconciliation_bugs: int = 0
    unresolved_risk_rule_violations: int = 0
    stale_data_issues: int = 0
    live_safety_issues: int = 0


@dataclass(frozen=True)
class PromotionReadinessReview:
    strategy_version: str
    decision: LivePromotionDecision
    missing: tuple[str, ...]
    calibration_reason_codes: tuple[str, ...]
    output_path: Path


class PromotionReadinessAuditor:
    def __init__(
        self,
        *,
        calibration_store: StrategyCalibrationArtifactStore,
        promotion_gate: LivePromotionGate,
        audit: JsonlAuditStore,
    ) -> None:
        self.calibration_store = calibration_store
        self.promotion_gate = promotion_gate
        self.audit = audit

    def review(
        self,
        *,
        strategy_version: str,
        paper: PaperTradingEvidence,
        safety: SafetyIssueEvidence,
        human_approval: bool,
        output_path: str | Path,
    ) -> PromotionReadinessReview:
        if not strategy_version.strip():
            raise ValueError("strategy_version is required")

        data_years = Decimal("0")
        cost_aware = False
        positive_expectancy = False
        drawdown_ok = False
        strategy_calibrated = False
        calibration_reasons = ("CALIBRATION_ARTIFACT_MISSING",)

        try:
            artifact = self.calibration_store.read(strategy_version)
        except FileNotFoundError:
            pass
        else:
            data_years = artifact.evidence.data_years
            cost_aware = artifact.evidence.brokerage_and_slippage_included
            positive_expectancy = artifact.evidence.expectancy > 0 and artifact.evidence.net_profit > 0
            drawdown_ok = "DRAWDOWN_TOO_HIGH" not in artifact.result.reason_codes
            strategy_calibrated = artifact.result.promotable
            calibration_reasons = artifact.result.reason_codes

        evidence = ValidationEvidence(
            backtested=strategy_calibrated,
            data_years=data_years,
            brokerage_and_slippage_included=cost_aware,
            positive_expectancy_after_costs=positive_expectancy,
            drawdown_within_limit=drawdown_ok,
            paper_traded_successfully=paper.successful,
            strategy_calibrated=strategy_calibrated,
            unresolved_execution_bugs=safety.unresolved_execution_bugs,
            unresolved_order_reconciliation_bugs=safety.unresolved_order_reconciliation_bugs,
            unresolved_risk_rule_violations=safety.unresolved_risk_rule_violations,
            stale_data_issues=safety.stale_data_issues,
            live_safety_issues=safety.live_safety_issues,
            human_approval=human_approval,
        )
        checklist = ValidationHarness().build_live_checklist(evidence)
        decision = self.promotion_gate.evaluate(checklist)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "strategy_version": strategy_version,
            "approved": decision.approved,
            "reason_code": decision.reason_code,
            "missing": list(decision.missing),
            "live_enabled": False,
            "calibration": {
                "promotable": strategy_calibrated,
                "reason_codes": list(calibration_reasons),
                "data_years": str(data_years),
            },
            "paper": {
                "successful": paper.successful,
            },
            "safety": {
                "unresolved_execution_bugs": safety.unresolved_execution_bugs,
                "unresolved_order_reconciliation_bugs": safety.unresolved_order_reconciliation_bugs,
                "unresolved_risk_rule_violations": safety.unresolved_risk_rule_violations,
                "stale_data_issues": safety.stale_data_issues,
                "live_safety_issues": safety.live_safety_issues,
            },
            "human_approval": human_approval,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self.audit.append(
            event_type="promotion_readiness_reviewed",
            payload={
                "strategy_version": strategy_version,
                "approved": decision.approved,
                "reason_code": decision.reason_code,
                "missing": list(decision.missing),
                "output_path": str(path),
            },
        )
        return PromotionReadinessReview(
            strategy_version=strategy_version,
            decision=decision,
            missing=decision.missing,
            calibration_reason_codes=calibration_reasons,
            output_path=path,
        )
