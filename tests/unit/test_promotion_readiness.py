from datetime import date
from decimal import Decimal
import json

from arthabot.audit_store import JsonlAuditStore
from arthabot.live_promotion import LivePromotionGate
from arthabot.promotion_readiness import (
    PaperTradingEvidence,
    PromotionReadinessAuditor,
    SafetyIssueEvidence,
)
from arthabot.strategy_calibration import (
    StrategyCalibrationArtifactStore,
    StrategyCalibrationEvidence,
    StrategyCalibrationGate,
)


def _write_calibration_artifact(tmp_path, *, promotable=True):
    evidence = StrategyCalibrationEvidence(
        strategy_version="momentum-v1",
        data_start=date(2023, 1, 1),
        data_end=date(2026, 1, 2),
        data_resolution="minute",
        symbols=("RELIANCE",),
        brokerage_and_slippage_included=True,
        walk_forward_windows=4,
        out_of_sample_tested=True,
        survivorship_bias_checked=True,
        net_profit=Decimal("120.50") if promotable else Decimal("-1"),
        expectancy=Decimal("0.4") if promotable else Decimal("-0.1"),
        max_drawdown=Decimal("0.05"),
        rejected_trades=3,
    )
    thresholds = type(
        "Thresholds",
        (),
        {
            "min_data_years": Decimal("3"),
            "min_walk_forward_windows": 3,
            "max_drawdown": Decimal("0.10"),
            "min_expectancy": Decimal("0.01"),
        },
    )()
    result = StrategyCalibrationGate(thresholds=thresholds).evaluate(evidence)
    store = StrategyCalibrationArtifactStore(tmp_path / "calibration")
    store.write(evidence=evidence, result=result)
    return store


def test_promotion_readiness_auditor_writes_blocking_review_without_human_approval(tmp_path):
    store = _write_calibration_artifact(tmp_path)
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")

    review = PromotionReadinessAuditor(
        calibration_store=store,
        promotion_gate=LivePromotionGate(),
        audit=audit,
    ).review(
        strategy_version="momentum-v1",
        paper=PaperTradingEvidence(successful=True),
        safety=SafetyIssueEvidence(),
        human_approval=False,
        output_path=tmp_path / "review.json",
    )

    payload = json.loads((tmp_path / "review.json").read_text(encoding="utf-8"))
    assert review.decision.approved is False
    assert review.decision.reason_code == "HUMAN_APPROVAL_REQUIRED"
    assert review.missing == ("human_approval",)
    assert payload["strategy_version"] == "momentum-v1"
    assert payload["approved"] is False
    assert payload["live_enabled"] is False
    assert payload["missing"] == ["human_approval"]
    assert payload["calibration"]["promotable"] is True
    assert audit.read_all()[-1].event_type == "promotion_readiness_reviewed"


def test_promotion_readiness_auditor_reports_missing_calibration_as_live_safety_blocker(tmp_path):
    review = PromotionReadinessAuditor(
        calibration_store=StrategyCalibrationArtifactStore(tmp_path / "missing"),
        promotion_gate=LivePromotionGate(),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    ).review(
        strategy_version="unknown-v1",
        paper=PaperTradingEvidence(successful=True),
        safety=SafetyIssueEvidence(),
        human_approval=True,
        output_path=tmp_path / "review.json",
    )

    assert review.decision.approved is False
    assert "no_live_safety_issues" in review.missing
    assert review.calibration_reason_codes == ("CALIBRATION_ARTIFACT_MISSING",)


def test_promotion_readiness_auditor_requires_paper_success_and_clean_safety_counts(tmp_path):
    store = _write_calibration_artifact(tmp_path)

    review = PromotionReadinessAuditor(
        calibration_store=store,
        promotion_gate=LivePromotionGate(),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    ).review(
        strategy_version="momentum-v1",
        paper=PaperTradingEvidence(successful=False),
        safety=SafetyIssueEvidence(
            unresolved_execution_bugs=1,
            unresolved_order_reconciliation_bugs=2,
            unresolved_risk_rule_violations=1,
            stale_data_issues=1,
            live_safety_issues=1,
        ),
        human_approval=True,
        output_path=tmp_path / "review.json",
    )

    assert review.decision.approved is False
    assert review.missing == (
        "paper_traded_successfully",
        "no_execution_bugs",
        "no_order_reconciliation_bugs",
        "no_risk_rule_violations",
        "no_stale_data_issues",
        "no_live_safety_issues",
    )
