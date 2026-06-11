from datetime import datetime
from decimal import Decimal

import pytest

from arthabot.backtest import Candle, HistoricalDataset
from arthabot.brokerage import BrokerageConfig
from arthabot.data_providers import HistoricalProviderRequest
from arthabot.strategy_calibration_config import (
    build_historical_calibration_inputs_from_config,
    load_strategy_calibration_config,
)


def candle(day: str, *, open_price: str, close: str, volume: int = 20_000) -> Candle:
    return Candle(
        timestamp=datetime.fromisoformat(f"{day}T09:15:00+00:00"),
        open=Decimal(open_price),
        high=max(Decimal(open_price), Decimal(close)),
        low=min(Decimal(open_price), Decimal(close)),
        close=Decimal(close),
        volume=volume,
    )


class FakeHistoricalProvider:
    def __init__(self) -> None:
        self.requests: list[HistoricalProviderRequest] = []

    def fetch(self, request: HistoricalProviderRequest) -> HistoricalDataset:
        self.requests.append(request)
        return HistoricalDataset(
            symbol=request.symbol,
            resolution=request.resolution,
            candles=[
                candle("2026-01-05", open_price="100", close="103"),
                candle("2026-01-06", open_price="103", close="106"),
            ],
        )


def test_build_historical_calibration_inputs_from_config_fetches_datasets_and_runs_core_engines(tmp_path):
    config_path = tmp_path / "strategy.yaml"
    config_path.write_text(
        """
calibration:
  versions:
    - version: momentum-v1
      engine: momentum
      symbols: [INFY]
      resolution: 1m
      from_time: "2023-01-01T09:15:00+00:00"
      to_time: "2026-01-02T15:30:00+00:00"
      quantity: 2
      walk_forward_windows: 4
      out_of_sample_tested: true
      survivorship_bias_checked: true
      params:
        min_move_pct: "0.02"
    - version: volume-mover-v1
      engine: volume_mover
      symbols: [TCS]
      resolution: 1m
      from_time: "2023-01-01T09:15:00+00:00"
      to_time: "2026-01-02T15:30:00+00:00"
      quantity: 1
      walk_forward_windows: 4
      out_of_sample_tested: true
      survivorship_bias_checked: true
      params:
        min_volume: 10000
        min_move_pct: "0.01"
""",
        encoding="utf-8",
    )
    provider = FakeHistoricalProvider()

    inputs = build_historical_calibration_inputs_from_config(
        config=load_strategy_calibration_config(config_path),
        historical_provider=provider,
        starting_capital=Decimal("5000"),
        brokerage_config=BrokerageConfig(slippage_rate=Decimal("0")),
    )

    assert [request.symbol for request in provider.requests] == ["INFY", "TCS"]
    assert provider.requests[0].from_time == datetime.fromisoformat("2023-01-01T09:15:00+00:00")
    assert inputs.reports_by_version["momentum-v1"].number_of_trades == 1
    assert inputs.reports_by_version["volume-mover-v1"].total_costs > 0
    assert inputs.walk_forward_windows_by_version["momentum-v1"] == 4


def test_load_strategy_calibration_config_fails_closed_without_date_windows(tmp_path):
    config_path = tmp_path / "strategy.yaml"
    config_path.write_text(
        """
calibration:
  versions:
    - version: momentum-v1
      engine: momentum
      symbols: [INFY]
      resolution: 1m
      quantity: 1
      walk_forward_windows: 4
      out_of_sample_tested: true
      survivorship_bias_checked: true
      params:
        min_move_pct: "0.02"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="from_time and to_time are required"):
        load_strategy_calibration_config(config_path)


def test_load_strategy_calibration_config_rejects_unknown_engine(tmp_path):
    config_path = tmp_path / "strategy.yaml"
    config_path.write_text(
        """
calibration:
  versions:
    - version: unsafe-v1
      engine: live_magic
      symbols: [INFY]
      resolution: 1m
      from_time: "2023-01-01T09:15:00+00:00"
      to_time: "2026-01-02T15:30:00+00:00"
      quantity: 1
      walk_forward_windows: 4
      out_of_sample_tested: true
      survivorship_bias_checked: true
      params: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported calibration engine"):
        load_strategy_calibration_config(config_path)


def test_repository_strategy_config_declares_all_core_calibration_versions():
    config = load_strategy_calibration_config("config/strategy.yaml")

    assert tuple(version.version for version in config.versions) == (
        "momentum-v1",
        "breakout-v1",
        "reversal-v1",
        "volume-mover-v1",
    )
    assert all(version.from_time < version.to_time for version in config.versions)
    assert all(version.quantity > 0 for version in config.versions)
