from datetime import datetime, timezone
from decimal import Decimal

import pytest

from arthabot.data import MarketSnapshot
from arthabot.runtime_strategy_provider import (
    ConfiguredRuntimeStrategyProvider,
    load_runtime_strategy_config,
)


def snapshot(symbol: str, price: str, open_price: str, volume: int) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        last_price=Decimal(price),
        open_price=Decimal(open_price),
        volume=volume,
        timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
    )


def test_configured_runtime_strategy_provider_generates_ranked_candidates_without_orders(tmp_path):
    config_path = tmp_path / "strategy.yaml"
    config_path.write_text(
        """
runtime_strategies:
  versions:
    - version: momentum-v1
      engine: momentum
      enabled: true
      params:
        min_move_pct: "0.01"
    - version: volume-mover-v1
      engine: volume_mover
      enabled: true
      params:
        min_volume: 10000
        min_move_pct: "0.01"
""",
        encoding="utf-8",
    )

    candidates = ConfiguredRuntimeStrategyProvider(
        config=load_runtime_strategy_config(config_path)
    ).generate(
        [
            snapshot("INFY", "102", "100", 20_000),
            snapshot("LOWVOL", "102", "100", 100),
        ]
    )

    infy_versions = {
        candidate.strategy_version
        for candidate in candidates
        if candidate.symbol == "INFY"
    }
    lowvol_versions = {
        candidate.strategy_version
        for candidate in candidates
        if candidate.symbol == "LOWVOL"
    }
    assert infy_versions == {"momentum-v1", "volume-mover-v1"}
    assert lowvol_versions == {"momentum-v1"}
    assert all(candidate.strategy_version in {"momentum-v1", "volume-mover-v1"} for candidate in candidates)
    assert not hasattr(candidates[0], "order_id")


def test_runtime_strategy_config_rejects_unknown_engine(tmp_path):
    config_path = tmp_path / "strategy.yaml"
    config_path.write_text(
        """
runtime_strategies:
  versions:
    - version: unsafe-v1
      engine: live_order_placer
      enabled: true
      params: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported runtime strategy engine"):
        load_runtime_strategy_config(config_path)


def test_repository_strategy_config_declares_core_runtime_strategy_versions():
    config = load_runtime_strategy_config("config/strategy.yaml")

    assert tuple(version.version for version in config.enabled_versions) == (
        "momentum-v1",
        "breakout-v1",
        "reversal-v1",
        "volume-mover-v1",
    )
