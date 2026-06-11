import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from arthabot.common import Mode
from arthabot.operational_handlers import (
    FileBackedLearningRerunHandler,
    HistoricalBacktestRerunRunner,
    StrategyCalibrationSchedulerHandler,
)
from arthabot.learning_operations import BacktestRerunRequest


class RecordingWorker:
    def __init__(self, result):
        self.result = result
        self.changes = []

    def run(self, changes):
        self.changes.append(changes)
        return self.result


def worker_result(*, completed=1, failed=0, must_stop=False):
    return SimpleNamespace(
        completed=completed,
        failed=failed,
        must_stop_trading=must_stop,
        reason_code="LEARNING_RERUN_FAILED" if must_stop else "LEARNING_RERUNS_COMPLETED",
    )


def test_file_backed_learning_handler_runs_paper_queue_and_clears_it(tmp_path):
    queue_path = tmp_path / "learning-reruns.json"
    queue_path.write_text(
        json.dumps(
            [
                {
                    "name": "rerun momentum-v2",
                    "target": "backtest.rerun.momentum-v2",
                    "value": "1",
                    "mode": "PAPER",
                }
            ]
        ),
        encoding="utf-8",
    )
    worker = RecordingWorker(worker_result())
    now = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)

    payload = FileBackedLearningRerunHandler(queue_path=queue_path, worker=worker)(now)

    assert worker.changes[0][0].mode == Mode.PAPER
    assert worker.changes[0][0].target == "backtest.rerun.momentum-v2"
    assert payload == {
        "reason_code": "LEARNING_RERUNS_COMPLETED",
        "completed": 1,
        "failed": 0,
        "must_stop_trading": False,
        "timestamp": "2026-06-11T10:00:00+00:00",
    }
    assert json.loads(queue_path.read_text(encoding="utf-8")) == []


def test_file_backed_learning_handler_keeps_queue_after_worker_failure(tmp_path):
    queue_path = tmp_path / "learning-reruns.json"
    original = [{"name": "rerun v1", "target": "backtest.rerun.v1", "value": 1, "mode": "PAPER"}]
    queue_path.write_text(json.dumps(original), encoding="utf-8")

    payload = FileBackedLearningRerunHandler(
        queue_path=queue_path,
        worker=RecordingWorker(worker_result(completed=0, failed=1, must_stop=True)),
    )()

    assert payload["must_stop_trading"] is True
    assert json.loads(queue_path.read_text(encoding="utf-8")) == original


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "unsafe", "target": "backtest.rerun.v1", "value": 1, "mode": "LIVE"},
        {"name": "unsafe", "target": "risk.stop_loss_required", "value": False, "mode": "PAPER"},
    ],
)
def test_file_backed_learning_handler_rejects_unsafe_entries_without_consuming_queue(tmp_path, entry):
    queue_path = tmp_path / "learning-reruns.json"
    queue_path.write_text(json.dumps([entry]), encoding="utf-8")
    worker = RecordingWorker(worker_result())

    with pytest.raises((PermissionError, ValueError)):
        FileBackedLearningRerunHandler(queue_path=queue_path, worker=worker)()

    assert worker.changes == []
    assert json.loads(queue_path.read_text(encoding="utf-8")) == [entry]


def test_file_backed_learning_handler_treats_missing_queue_as_no_work(tmp_path):
    worker = RecordingWorker(worker_result(completed=0))

    payload = FileBackedLearningRerunHandler(
        queue_path=tmp_path / "missing.json",
        worker=worker,
    )()

    assert payload["completed"] == 0
    assert payload["must_stop_trading"] is False
    assert worker.changes == [[]]


def test_strategy_calibration_scheduler_handler_returns_version_summary():
    service = SimpleNamespace(
        run=lambda: SimpleNamespace(
            results={
                "momentum-v1": SimpleNamespace(promotable=True),
                "reversal-v1": SimpleNamespace(promotable=False),
            }
        )
    )
    now = datetime(2026, 6, 11, 11, 0, tzinfo=timezone.utc)

    payload = StrategyCalibrationSchedulerHandler(service=service)(now)

    assert payload == {
        "reason_code": "STRATEGY_CALIBRATION_COMPLETED",
        "strategy_versions": ["momentum-v1", "reversal-v1"],
        "promotable_versions": ["momentum-v1"],
        "rejected_versions": ["reversal-v1"],
        "must_stop_trading": False,
        "timestamp": "2026-06-11T11:00:00+00:00",
    }


def test_historical_backtest_rerun_runner_returns_requested_configured_report(monkeypatch):
    expected = SimpleNamespace(net_profit=12)
    config = SimpleNamespace(versions=(SimpleNamespace(version="momentum-v1"),))

    monkeypatch.setattr(
        "arthabot.operational_handlers.build_historical_calibration_inputs_from_config",
        lambda **kwargs: SimpleNamespace(reports_by_version={"momentum-v1": expected}),
    )
    runner = HistoricalBacktestRerunRunner(
        config=config,
        historical_provider=object(),
        starting_capital=5000,
        brokerage_config=object(),
    )

    assert runner(BacktestRerunRequest(strategy_version="momentum-v1")) is expected


def test_historical_backtest_rerun_runner_rejects_unknown_version():
    runner = HistoricalBacktestRerunRunner(
        config=SimpleNamespace(versions=(SimpleNamespace(version="momentum-v1"),)),
        historical_provider=object(),
        starting_capital=5000,
        brokerage_config=object(),
    )

    with pytest.raises(KeyError, match="unknown configured rerun version"):
        runner(BacktestRerunRequest(strategy_version="missing-v1"))
