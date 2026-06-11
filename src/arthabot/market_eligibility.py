from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


CorporateActionProvider = Callable[[str, date], bool]


@dataclass(frozen=True)
class MarketEligibilityConfig:
    timezone: str
    session_open: time
    session_close: time
    holidays: frozenset[date]
    corporate_action_fail_closed: bool

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {self.timezone}") from exc
        if self.session_close <= self.session_open:
            raise ValueError("session_close must be after session_open")


@dataclass(frozen=True)
class MarketEligibilityDecision:
    allowed: bool
    reason_code: str
    symbol: str | None = None


class MarketEligibilityError(RuntimeError):
    def __init__(self, decision: MarketEligibilityDecision) -> None:
        super().__init__(decision.reason_code)
        self.decision = decision


class MarketEligibilityGuard:
    def __init__(
        self,
        *,
        config: MarketEligibilityConfig,
        corporate_action_provider: CorporateActionProvider,
    ) -> None:
        self.config = config
        self.corporate_action_provider = corporate_action_provider
        self._timezone = ZoneInfo(config.timezone)

    def evaluate_market(self, *, now: datetime) -> MarketEligibilityDecision:
        local_now = self._localize(now)
        if local_now.weekday() >= 5:
            return MarketEligibilityDecision(False, "MARKET_WEEKEND")
        if local_now.date() in self.config.holidays:
            return MarketEligibilityDecision(False, "MARKET_HOLIDAY")
        if not self.config.session_open <= local_now.time().replace(tzinfo=None) <= self.config.session_close:
            return MarketEligibilityDecision(False, "MARKET_SESSION_CLOSED")
        return MarketEligibilityDecision(True, "MARKET_ELIGIBLE")

    def evaluate_symbol(self, *, symbol: str, now: datetime) -> MarketEligibilityDecision:
        local_now = self._localize(now)
        try:
            active = self.corporate_action_provider(symbol, local_now.date())
        except Exception:
            if self.config.corporate_action_fail_closed:
                return MarketEligibilityDecision(False, "CORPORATE_ACTION_STATE_UNKNOWN", symbol)
            return MarketEligibilityDecision(True, "SYMBOL_ELIGIBLE", symbol)
        if active:
            return MarketEligibilityDecision(False, "CORPORATE_ACTION_ACTIVE", symbol)
        return MarketEligibilityDecision(True, "SYMBOL_ELIGIBLE", symbol)

    def _localize(self, now: datetime) -> datetime:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return now.astimezone(self._timezone)


def load_market_eligibility_config(path: str | Path) -> MarketEligibilityConfig:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("market config must contain a mapping")
    holidays = frozenset(date.fromisoformat(str(value)) for value in raw.get("holidays", []))
    return MarketEligibilityConfig(
        timezone=str(raw["timezone"]),
        session_open=time.fromisoformat(str(raw["session_open"])),
        session_close=time.fromisoformat(str(raw["session_close"])),
        holidays=holidays,
        corporate_action_fail_closed=bool(raw.get("corporate_action_fail_closed", True)),
    )

