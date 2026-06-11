from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path

from arthabot.audit_store import JsonlAuditStore
from arthabot.backtest import BacktestReport
from arthabot.common import Mode
from arthabot.learning import ProposedChange


@dataclass(frozen=True)
class BacktestRerunRequest:
    strategy_version: str


@dataclass(frozen=True)
class BacktestRerunResult:
    strategy_version: str
    report: BacktestReport
    artifact_path: Path


class LearningRerunWorkflow:
    def __init__(
        self,
        *,
        audit: JsonlAuditStore,
        artifact_dir: str | Path,
        runner: Callable[[BacktestRerunRequest], BacktestReport],
    ) -> None:
        self.audit = audit
        self.artifact_dir = Path(artifact_dir)
        self.runner = runner

    def run(self, change: ProposedChange) -> BacktestRerunResult:
        if change.mode == Mode.LIVE:
            raise PermissionError("learning reruns must not run in LIVE mode")
        prefix = "backtest.rerun."
        if not change.target.startswith(prefix):
            raise ValueError("learning rerun target must start with backtest.rerun")
        strategy_version = change.target.removeprefix(prefix)
        if not strategy_version:
            raise ValueError("strategy version is required")
        request = BacktestRerunRequest(strategy_version=strategy_version)
        report = self.runner(request)
        artifact_path = self._write_artifact(strategy_version, report)
        self.audit.append(
            event_type="learning_backtest_rerun",
            payload={
                "strategy_version": strategy_version,
                "artifact_path": str(artifact_path),
                "net_profit": str(report.net_profit),
            },
        )
        return BacktestRerunResult(strategy_version=strategy_version, report=report, artifact_path=artifact_path)

    def _write_artifact(self, strategy_version: str, report: BacktestReport) -> Path:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self.artifact_dir / f"{strategy_version}-backtest-rerun.json"
        payload = {
            "strategy_version": strategy_version,
            "net_profit": str(report.net_profit),
            "gross_profit": str(report.gross_profit),
            "total_costs": str(report.total_costs),
            "win_rate": str(report.win_rate),
            "number_of_trades": report.number_of_trades,
            "number_of_rejected_trades": report.number_of_rejected_trades,
            "number_of_missed_trades": report.number_of_missed_trades,
            "max_drawdown": str(report.max_drawdown),
        }
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return path

