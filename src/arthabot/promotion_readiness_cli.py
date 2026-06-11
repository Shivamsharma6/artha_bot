from __future__ import annotations

import argparse

from arthabot.audit_store import JsonlAuditStore
from arthabot.live_promotion import LivePromotionGate
from arthabot.promotion_readiness import (
    PaperTradingEvidence,
    PromotionReadinessAuditor,
    SafetyIssueEvidence,
)
from arthabot.strategy_calibration import StrategyCalibrationArtifactStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write an ArthaBot LIVE promotion readiness review.")
    parser.add_argument("--strategy-version", required=True)
    parser.add_argument("--calibration-dir", default="reports/calibration")
    parser.add_argument("--audit-log", default="logs/promotion_readiness.jsonl")
    parser.add_argument("--output", required=True)
    parser.add_argument("--paper-successful", action="store_true")
    parser.add_argument("--human-approval", action="store_true")
    parser.add_argument("--unresolved-execution-bugs", type=int, default=0)
    parser.add_argument("--unresolved-order-reconciliation-bugs", type=int, default=0)
    parser.add_argument("--unresolved-risk-rule-violations", type=int, default=0)
    parser.add_argument("--stale-data-issues", type=int, default=0)
    parser.add_argument("--live-safety-issues", type=int, default=0)
    args = parser.parse_args(argv)

    PromotionReadinessAuditor(
        calibration_store=StrategyCalibrationArtifactStore(args.calibration_dir),
        promotion_gate=LivePromotionGate(),
        audit=JsonlAuditStore(args.audit_log),
    ).review(
        strategy_version=args.strategy_version,
        paper=PaperTradingEvidence(successful=args.paper_successful),
        safety=SafetyIssueEvidence(
            unresolved_execution_bugs=args.unresolved_execution_bugs,
            unresolved_order_reconciliation_bugs=args.unresolved_order_reconciliation_bugs,
            unresolved_risk_rule_violations=args.unresolved_risk_rule_violations,
            stale_data_issues=args.stale_data_issues,
            live_safety_issues=args.live_safety_issues,
        ),
        human_approval=args.human_approval,
        output_path=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
