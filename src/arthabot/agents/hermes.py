from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from arthabot.common import Direction


class HermesDecision(BaseModel):
    candidate_symbol: str
    direction: Direction
    entry_rationale: str
    entry_price_zone: tuple[Decimal, Decimal]
    stop_loss: Decimal
    trailing_stop_loss_logic: str
    target_or_exit_logic: str
    expected_reward_to_risk: Decimal
    cost_aware_break_even: Decimal
    confidence_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    reasons_to_reject: list[str]
    data_used: list[str]
    timestamp: str
    strategy_model_version: str

    @field_validator(
        "candidate_symbol",
        "entry_rationale",
        "trailing_stop_loss_logic",
        "target_or_exit_logic",
        "timestamp",
        "strategy_model_version",
    )
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("entry_price_zone")
    @classmethod
    def require_ordered_zone(cls, value: tuple[Decimal, Decimal]) -> tuple[Decimal, Decimal]:
        low, high = value
        if low <= 0 or high <= 0 or low > high:
            raise ValueError("entry_price_zone must be positive and ordered")
        return value

    @field_validator("expected_reward_to_risk", "cost_aware_break_even")
    @classmethod
    def require_positive_decimal(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("field must be positive")
        return value

