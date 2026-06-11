import json

import pytest

from arthabot.audit_store import JsonlAuditStore
from arthabot.live_approval_package import LiveApprovalPackageBuilder


def test_live_approval_package_builder_writes_manifest_and_template(tmp_path):
    package_dir = tmp_path / "approval-package"
    audit = JsonlAuditStore(tmp_path / "audit.jsonl")

    result = LiveApprovalPackageBuilder(
        config_dir="config",
        audit=audit,
    ).build(strategy_version="momentum-v1", output_dir=package_dir)

    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    template = (package_dir / "approval_request.yaml").read_text(encoding="utf-8")

    assert result.manifest_path == package_dir / "manifest.json"
    assert manifest["strategy_version"] == "momentum-v1"
    assert manifest["default_mode"] == "PAPER"
    assert manifest["live_enabled"] is False
    assert manifest["requires_human_live_approval"] is True
    assert manifest["approval_template"] == "approval_request.yaml"
    assert "human_approval" in template
    assert audit.read_all()[-1].event_type == "live_approval_package_created"


def test_live_approval_package_builder_refuses_live_enabled_config(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "risk.yaml").write_text(
        """
starting_capital: "5000"
max_risk_per_trade_pct: "0.01"
max_daily_loss_pct: "0.03"
min_allocation_pct: "0.05"
max_trades_per_day: 3
quote_max_age_seconds: 3
square_off_time: "15:15"
leverage_allowed: false
""",
        encoding="utf-8",
    )
    (config_dir / "modes.yaml").write_text(
        """
default_mode: "PAPER"
live_enabled: true
requires_human_live_approval: true
""",
        encoding="utf-8",
    )

    with pytest.raises(PermissionError, match="must remain disabled"):
        LiveApprovalPackageBuilder(
            config_dir=config_dir,
            audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
        ).build(strategy_version="momentum-v1", output_dir=tmp_path / "package")


def test_live_approval_package_builder_requires_human_approval_gate(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "risk.yaml").write_text(
        """
starting_capital: "5000"
max_risk_per_trade_pct: "0.01"
max_daily_loss_pct: "0.03"
min_allocation_pct: "0.05"
max_trades_per_day: 3
quote_max_age_seconds: 3
square_off_time: "15:15"
leverage_allowed: false
""",
        encoding="utf-8",
    )
    (config_dir / "modes.yaml").write_text(
        """
default_mode: "PAPER"
live_enabled: false
requires_human_live_approval: false
""",
        encoding="utf-8",
    )

    with pytest.raises(PermissionError, match="human live approval"):
        LiveApprovalPackageBuilder(
            config_dir=config_dir,
            audit=JsonlAuditStore(tmp_path / "audit.jsonl"),
        ).build(strategy_version="momentum-v1", output_dir=tmp_path / "package")
