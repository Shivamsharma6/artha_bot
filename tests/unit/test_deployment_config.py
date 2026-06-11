from pathlib import Path

import pytest

from arthabot.common import Mode
from arthabot.deployment_config import load_deployment_config


def test_deployment_config_loads_paper_scheduler_jobs_from_yaml():
    config = load_deployment_config("config")

    assert config.environment == "paper-local"
    assert config.mode == Mode.PAPER
    assert [job.name for job in config.scheduler.jobs] == [
        "instrument-refresh-nse",
        "news-ingest-core-watchlist",
        "live-feed-supervision",
        "broker-state-reconciliation",
        "operational-learning-rerun",
        "strategy-calibration-rerun",
    ]
    assert config.scheduler.jobs[0].run_at == "08:30"
    assert config.scheduler.jobs[0].critical
    assert config.scheduler.jobs[1].enabled
    assert config.scheduler.jobs[1].symbols == ["INFY", "RELIANCE", "TCS"]
    assert config.scheduler.jobs[3].type == "broker_reconciliation"
    assert config.scheduler.jobs[3].critical
    assert config.scheduler.jobs[5].type == "strategy_calibration"
    assert not config.scheduler.jobs[5].critical


def test_deployment_config_rejects_live_mode_when_live_is_disabled(tmp_path):
    deployment_file = tmp_path / "deployment.yaml"
    deployment_file.write_text(
        """
environment: unsafe-live
mode: LIVE
live_enabled: false
scheduler:
  timezone: Asia/Kolkata
  jobs:
    - name: instrument-refresh-nse
      type: instrument_refresh
      enabled: true
      critical: true
      run_at: "08:30"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="LIVE deployment requires live_enabled"):
        load_deployment_config(tmp_path)


def test_deployment_config_rejects_duplicate_job_names(tmp_path):
    deployment_file = Path(tmp_path) / "deployment.yaml"
    deployment_file.write_text(
        """
environment: paper-local
mode: PAPER
live_enabled: false
scheduler:
  timezone: Asia/Kolkata
  jobs:
    - name: duplicate-job
      type: news_ingestion
      enabled: true
      critical: false
      run_at: "08:45"
    - name: duplicate-job
      type: news_ingestion
      enabled: true
      critical: false
      run_at: "09:15"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate scheduler job"):
        load_deployment_config(tmp_path)
