from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from arthabot.common import Mode


@dataclass(frozen=True)
class DeploymentJobConfig:
    name: str
    type: str
    enabled: bool
    critical: bool
    run_at: str
    symbols: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DeploymentSchedulerConfig:
    timezone: str
    jobs: list[DeploymentJobConfig]


@dataclass(frozen=True)
class DeploymentConfig:
    environment: str
    mode: Mode
    live_enabled: bool
    scheduler: DeploymentSchedulerConfig


def load_deployment_config(config_dir: str | Path) -> DeploymentConfig:
    root = Path(config_dir)
    data = _read_yaml(root / "deployment.yaml")
    scheduler = _read_mapping(data, "scheduler")
    jobs = [_parse_job(job) for job in _read_list(scheduler, "jobs")]
    _validate_unique_job_names(jobs)
    config = DeploymentConfig(
        environment=str(data["environment"]),
        mode=Mode(str(data["mode"])),
        live_enabled=bool(data.get("live_enabled", False)),
        scheduler=DeploymentSchedulerConfig(
            timezone=str(scheduler["timezone"]),
            jobs=jobs,
        ),
    )
    if config.mode == Mode.LIVE and not config.live_enabled:
        raise ValueError("LIVE deployment requires live_enabled")
    return config


def _parse_job(data: Any) -> DeploymentJobConfig:
    if not isinstance(data, dict):
        raise ValueError("scheduler jobs must be mappings")
    return DeploymentJobConfig(
        name=str(data["name"]),
        type=str(data["type"]),
        enabled=bool(data.get("enabled", True)),
        critical=bool(data.get("critical", False)),
        run_at=str(data["run_at"]),
        symbols=[str(symbol) for symbol in data.get("symbols", [])],
    )


def _validate_unique_job_names(jobs: list[DeploymentJobConfig]) -> None:
    seen: set[str] = set()
    for job in jobs:
        if job.name in seen:
            raise ValueError(f"duplicate scheduler job: {job.name}")
        seen.add(job.name)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


def _read_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must contain a mapping")
    return value


def _read_list(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must contain a list")
    return value
