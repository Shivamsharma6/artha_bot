import json

from arthabot.strategy_calibration_cli import main


class FakeService:
    def __init__(self) -> None:
        self.seen_versions = None

    def run(self, *, strategy_versions=None):
        self.seen_versions = strategy_versions
        return {"ok": True}


def test_strategy_calibration_cli_runs_service_for_selected_versions():
    service = FakeService()

    exit_code = main(
        ["--strategy-version", "momentum-v1", "--strategy-version", "breakout-v1"],
        service_factory=lambda args: service,
    )

    assert exit_code == 0
    assert service.seen_versions == ("momentum-v1", "breakout-v1")


def test_strategy_calibration_cli_requires_explicit_provider_wiring_without_factory():
    exit_code = main(["--config-path", "config/strategy.yaml"])

    assert exit_code == 2


def test_strategy_calibration_cli_runs_with_explicit_historical_json(tmp_path):
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
      quantity: 1
      walk_forward_windows: 4
      out_of_sample_tested: true
      survivorship_bias_checked: true
      params:
        min_move_pct: "0.02"
""",
        encoding="utf-8",
    )
    history_path = tmp_path / "history.json"
    history_path.write_text(
        json.dumps(
            {
                "INFY": [
                    {
                        "timestamp": "2023-01-01T09:15:00+00:00",
                        "open": "100",
                        "high": "103",
                        "low": "100",
                        "close": "103",
                        "volume": 20000,
                    },
                    {
                        "timestamp": "2026-01-02T09:15:00+00:00",
                        "open": "103",
                        "high": "106",
                        "low": "103",
                        "close": "106",
                        "volume": 20000,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--config-path",
            str(config_path),
            "--historical-json-path",
            str(history_path),
            "--audit-path",
            str(tmp_path / "audit.jsonl"),
            "--artifact-dir",
            str(tmp_path / "calibration"),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "calibration" / "momentum-v1-calibration.json").exists()
