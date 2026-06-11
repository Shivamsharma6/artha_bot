from datetime import datetime
from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.backtest import Candle, HistoricalDataset
from arthabot.brokerage import BrokerageConfig
from arthabot.data_providers import HistoricalProviderRequest
from arthabot.strategy_calibration import CalibrationThresholds, StrategyCalibrationArtifactStore
from arthabot.strategy_calibration_config import load_strategy_calibration_config
from arthabot.strategy_calibration_operations import StrategyCalibrationRunService


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
                candle("2023-01-01", open_price="100", close="103"),
                candle("2026-01-02", open_price="103", close="106"),
            ],
        )


def write_config(path):
    path.write_text(
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
""",
        encoding="utf-8",
    )


def test_strategy_calibration_run_service_persists_artifacts_and_batch_audit(tmp_path):
    config_path = tmp_path / "strategy.yaml"
    write_config(config_path)
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")
    store = StrategyCalibrationArtifactStore(tmp_path / "calibration")
    provider = FakeHistoricalProvider()

    result = StrategyCalibrationRunService(
        config=load_strategy_calibration_config(config_path),
        historical_provider=provider,
        starting_capital=Decimal("5000"),
        brokerage_config=BrokerageConfig(slippage_rate=Decimal("0")),
        thresholds=CalibrationThresholds(
            min_data_years=Decimal("3"),
            min_walk_forward_windows=4,
            max_drawdown=Decimal("100"),
            min_expectancy=Decimal("0.01"),
        ),
        store=store,
        audit=audit,
    ).run()

    assert result.strategy_versions == ("momentum-v1",)
    assert not result.results["momentum-v1"].promotable
    assert "NO_REJECTED_TRADE_LOGGING_EVIDENCE" in result.results["momentum-v1"].reason_codes
    assert not store.read("momentum-v1").result.promotable
    assert [request.symbol for request in provider.requests] == ["INFY"]
    assert audit.read_all()[-1].event_type == "strategy_calibration_batch_completed"
    assert audit.read_all()[-1].payload["strategy_versions"] == ["momentum-v1"]


def test_strategy_calibration_run_service_allows_targeted_version_runs(tmp_path):
    config_path = tmp_path / "strategy.yaml"
    write_config(config_path)

    result = StrategyCalibrationRunService(
        config=load_strategy_calibration_config(config_path),
        historical_provider=FakeHistoricalProvider(),
        starting_capital=Decimal("5000"),
        brokerage_config=BrokerageConfig(slippage_rate=Decimal("0")),
        thresholds=CalibrationThresholds(
            min_data_years=Decimal("3"),
            min_walk_forward_windows=4,
            max_drawdown=Decimal("100"),
            min_expectancy=Decimal("0.01"),
        ),
        store=StrategyCalibrationArtifactStore(tmp_path / "calibration"),
        audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
    ).run(strategy_versions=("momentum-v1",))

    assert tuple(result.results) == ("momentum-v1",)
