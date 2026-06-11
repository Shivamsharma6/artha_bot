from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class LivePromotionChecklist:
    backtested: bool
    three_years_where_available: bool
    brokerage_and_slippage_included: bool
    positive_expectancy_after_costs: bool
    drawdown_within_limit: bool
    paper_traded_successfully: bool
    no_execution_bugs: bool
    no_order_reconciliation_bugs: bool
    no_risk_rule_violations: bool
    no_stale_data_issues: bool
    no_live_safety_issues: bool
    human_approval: bool

    @classmethod
    def all_clear(cls) -> "LivePromotionChecklist":
        return cls(**{field.name: True for field in fields(cls)})


@dataclass(frozen=True)
class LivePromotionDecision:
    approved: bool
    reason_code: str
    missing: tuple[str, ...]


class LivePromotionGate:
    def evaluate(self, checklist: LivePromotionChecklist) -> LivePromotionDecision:
        missing = tuple(field.name for field in fields(checklist) if not getattr(checklist, field.name))
        if not missing:
            return LivePromotionDecision(True, "LIVE_PROMOTION_APPROVED", ())
        if "human_approval" in missing:
            return LivePromotionDecision(False, "HUMAN_APPROVAL_REQUIRED", missing)
        return LivePromotionDecision(False, "SAFETY_GATE_INCOMPLETE", missing)

