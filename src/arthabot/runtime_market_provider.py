from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from arthabot.audit_store import JsonlAuditStore
from arthabot.data import FreshnessPolicy, MarketSnapshot
from arthabot.market_eligibility import (
    CorporateActionProvider,
    MarketEligibilityDecision,
    MarketEligibilityError,
    MarketEligibilityGuard,
    load_market_eligibility_config,
)
from arthabot.runtime_strategy_provider import (
    ConfiguredRuntimeStrategyProvider,
    RuntimeStrategyConfig,
    load_runtime_strategy_config,
)
from arthabot.strategies import TradeCandidate


TopMoversClient = Callable[..., list[dict[str, Any]]]


class RuntimeMarketSnapshotProvider:
    def __init__(
        self,
        *,
        top_movers_client: TopMoversClient,
        max_age_seconds: int,
        eligibility_guard: MarketEligibilityGuard | None = None,
        audit: JsonlAuditStore | None = None,
    ) -> None:
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        self.top_movers_client = top_movers_client
        self.freshness = FreshnessPolicy(max_age_seconds=max_age_seconds)
        self.eligibility_guard = eligibility_guard
        self.audit = audit

    def fetch_top_movers(self, *, limit: int, now: datetime) -> list[MarketSnapshot]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if self.eligibility_guard is not None:
            self._require_eligible(self.eligibility_guard.evaluate_market(now=now), now=now)
        rows = self.top_movers_client(limit=limit)
        snapshots = [self._snapshot_from_row(row) for row in rows]
        stale = [
            snapshot.symbol
            for snapshot in snapshots
            if not self.freshness.is_fresh(snapshot, now=now)
        ]
        if stale:
            raise ValueError(f"stale top-mover snapshot: {stale[0]}")
        if self.eligibility_guard is not None:
            for snapshot in snapshots:
                self._require_eligible(
                    self.eligibility_guard.evaluate_symbol(symbol=snapshot.symbol, now=now),
                    now=now,
                )
        return snapshots

    def _require_eligible(self, decision: MarketEligibilityDecision, *, now: datetime) -> None:
        if decision.allowed:
            return
        if self.audit is not None:
            self.audit.append(
                event_type="market_eligibility_rejected",
                payload={
                    "reason_code": decision.reason_code,
                    "symbol": decision.symbol,
                    "evaluated_at": now.isoformat(),
                },
            )
        raise MarketEligibilityError(decision)

    @staticmethod
    def _snapshot_from_row(row: dict[str, Any]) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=str(row["symbol"]),
            last_price=Decimal(str(row["last_price"])),
            open_price=Decimal(str(row["open_price"])) if row.get("open_price") is not None else None,
            volume=int(row["volume"]),
            timestamp=datetime.fromisoformat(str(row["timestamp"])),
        )


class RuntimeStrategyCandidateComposer:
    def __init__(
        self,
        *,
        market_provider: RuntimeMarketSnapshotProvider,
        strategy_config: RuntimeStrategyConfig,
    ) -> None:
        self.market_provider = market_provider
        self.strategy_provider = ConfiguredRuntimeStrategyProvider(config=strategy_config)

    def generate_from_top_movers(self, *, limit: int, now: datetime) -> list[TradeCandidate]:
        snapshots = self.market_provider.fetch_top_movers(limit=limit, now=now)
        return self.strategy_provider.generate(snapshots)


def build_guarded_runtime_candidate_composer(
    *,
    top_movers_client: TopMoversClient,
    corporate_action_provider: CorporateActionProvider,
    max_age_seconds: int,
    market_config_path: str | Path,
    strategy_config_path: str | Path,
    audit: JsonlAuditStore,
) -> RuntimeStrategyCandidateComposer:
    guard = MarketEligibilityGuard(
        config=load_market_eligibility_config(market_config_path),
        corporate_action_provider=corporate_action_provider,
    )
    market_provider = RuntimeMarketSnapshotProvider(
        top_movers_client=top_movers_client,
        max_age_seconds=max_age_seconds,
        eligibility_guard=guard,
        audit=audit,
    )
    return RuntimeStrategyCandidateComposer(
        market_provider=market_provider,
        strategy_config=load_runtime_strategy_config(strategy_config_path),
    )
