from __future__ import annotations

import argparse
import json
from pathlib import Path

from arthabot.audit_store import JsonlAuditStore
from arthabot.config import load_runtime_config
from arthabot.deployment_config import load_deployment_config
from arthabot.deployment_preflight import (
    DeploymentHandlerEvidence,
    DeploymentPreflight,
    DeploymentPreflightRequest,
    SensitiveFileEvidence,
)
from arthabot.secrets import SecretConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check ArthaBot PAPER deployment readiness.")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--audit-path", default="logs/deployment_preflight.audit.jsonl")
    parser.add_argument("--instrument-store-path", default="data/instruments.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--ssh-key", required=True)
    parser.add_argument("--sensitive-file", action="append", default=[])
    parser.add_argument("--sensitive-files-ignored", action="store_true")
    parser.add_argument("--live-feed-handler-configured", action="store_true")
    parser.add_argument("--learning-rerun-handler-configured", action="store_true")
    parser.add_argument("--strategy-calibration-handler-configured", action="store_true")
    args = parser.parse_args(argv)

    audit = JsonlAuditStore(args.audit_path)
    result = DeploymentPreflight().evaluate(
        DeploymentPreflightRequest(
            deployment=load_deployment_config(args.config_dir),
            runtime=load_runtime_config(args.config_dir),
            secrets=SecretConfig.from_env(),
            handlers=DeploymentHandlerEvidence(
                live_feed_supervision=args.live_feed_handler_configured,
                learning_rerun=args.learning_rerun_handler_configured,
                strategy_calibration=args.strategy_calibration_handler_configured,
            ),
            audit_path=Path(args.audit_path),
            instrument_store_path=Path(args.instrument_store_path),
            sensitive_files=tuple(
                SensitiveFileEvidence(path=Path(path), git_ignored=args.sensitive_files_ignored)
                for path in args.sensitive_file
            ),
            ssh_key_path=Path(args.ssh_key),
        )
    )
    payload = {
        "ready": result.ready,
        "reason_codes": list(result.reason_codes),
        "checks": [
            {"name": check.name, "passed": check.passed, "reason_code": check.reason_code}
            for check in result.checks
        ],
        "mode": "PAPER",
        "live_enabled": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    audit.append(
        event_type="deployment_preflight_completed",
        payload={
            "ready": result.ready,
            "reason_codes": list(result.reason_codes),
            "mode": "PAPER",
            "live_enabled": False,
        },
    )
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())

