from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from arthabot.common import Mode


PROTECTED_LIVE_TARGETS = {
    "risk.stop_loss_required",
    "risk.trailing_stop_required",
    "risk.leverage_allowed",
    "risk.overnight_allowed",
    "execution.live_promotion",
}


@dataclass(frozen=True)
class ProposedChange:
    name: str
    target: str
    value: Any
    mode: Mode


class LearningEngine:
    def validate_change(self, change: ProposedChange) -> ProposedChange:
        if change.mode == Mode.LIVE and change.target in PROTECTED_LIVE_TARGETS:
            raise PermissionError("protected LIVE risk controls require explicit human approval")
        if change.target == "risk.leverage_allowed" and change.value is True:
            raise PermissionError("leverage is not allowed in the current version")
        return change

