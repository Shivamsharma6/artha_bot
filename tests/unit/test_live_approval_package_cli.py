import json

from arthabot.live_approval_package_cli import main


def test_live_approval_package_cli_creates_package(tmp_path):
    output_dir = tmp_path / "approval-package"

    exit_code = main(
        [
            "--config-dir",
            "config",
            "--audit-log",
            str(tmp_path / "audit.jsonl"),
            "--strategy-version",
            "momentum-v1",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "approval_request.yaml").exists()
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["strategy_version"] == "momentum-v1"
