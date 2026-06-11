from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from arthabot.audit_store import JsonlAuditStore
from arthabot.config import load_runtime_config
from arthabot.live_approval_interface import ApprovalInterface


@dataclass(frozen=True)
class LiveApprovalPackageResult:
    output_dir: Path
    manifest_path: Path
    template_path: Path


class LiveApprovalPackageBuilder:
    def __init__(self, *, config_dir: str | Path, audit: JsonlAuditStore) -> None:
        self.config_dir = Path(config_dir)
        self.audit = audit

    def build(self, *, strategy_version: str, output_dir: str | Path) -> LiveApprovalPackageResult:
        if not strategy_version.strip():
            raise ValueError("strategy_version is required")
        runtime = load_runtime_config(self.config_dir)
        if runtime.mode.live_enabled:
            raise PermissionError("live_enabled must remain disabled while packaging approval")
        if not runtime.mode.requires_human_live_approval:
            raise PermissionError("human live approval must be required")

        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        template_path = root / "approval_request.yaml"
        manifest_path = root / "manifest.json"
        template_path.write_text(
            ApprovalInterface(self.audit).render_request(strategy_version=strategy_version),
            encoding="utf-8",
        )
        manifest = {
            "strategy_version": strategy_version,
            "default_mode": runtime.mode.default_mode.value,
            "live_enabled": runtime.mode.live_enabled,
            "requires_human_live_approval": runtime.mode.requires_human_live_approval,
            "approval_template": template_path.name,
            "audit_event": "human_live_approval",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        self.audit.append(
            event_type="live_approval_package_created",
            payload={
                "strategy_version": strategy_version,
                "output_dir": str(root),
                "manifest_path": str(manifest_path),
            },
        )
        return LiveApprovalPackageResult(
            output_dir=root,
            manifest_path=manifest_path,
            template_path=template_path,
        )
