from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arthabot.live_promotion import LivePromotionChecklist


@dataclass(frozen=True)
class ValidationEvidence:
    backtested: bool
    data_years: Decimal
    brokerage_and_slippage_included: bool
    positive_expectancy_after_costs: bool
    drawdown_within_limit: bool
    paper_traded_successfully: bool
    strategy_calibrated: bool
    unresolved_execution_bugs: int
    unresolved_order_reconciliation_bugs: int
    unresolved_risk_rule_violations: int
    stale_data_issues: int
    live_safety_issues: int
    human_approval: bool


class ValidationHarness:
    def build_live_checklist(self, evidence: ValidationEvidence) -> LivePromotionChecklist:
        return LivePromotionChecklist(
            backtested=evidence.backtested,
            three_years_where_available=evidence.data_years >= Decimal("3"),
            brokerage_and_slippage_included=evidence.brokerage_and_slippage_included,
            positive_expectancy_after_costs=evidence.positive_expectancy_after_costs,
            drawdown_within_limit=evidence.drawdown_within_limit,
            paper_traded_successfully=evidence.paper_traded_successfully,
            no_execution_bugs=evidence.unresolved_execution_bugs == 0,
            no_order_reconciliation_bugs=evidence.unresolved_order_reconciliation_bugs == 0,
            no_risk_rule_violations=evidence.unresolved_risk_rule_violations == 0,
            no_stale_data_issues=evidence.stale_data_issues == 0,
            no_live_safety_issues=evidence.live_safety_issues == 0 and evidence.strategy_calibrated,
            human_approval=evidence.human_approval,
        )
