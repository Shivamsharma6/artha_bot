import json

from arthabot.promotion_readiness_cli import main


def test_promotion_readiness_cli_writes_review_with_missing_calibration(tmp_path):
    output_path = tmp_path / "review.json"
    audit_path = tmp_path / "audit.jsonl"

    exit_code = main(
        [
            "--strategy-version",
            "momentum-v1",
            "--calibration-dir",
            str(tmp_path / "calibration"),
            "--audit-log",
            str(audit_path),
            "--output",
            str(output_path),
            "--paper-successful",
            "--human-approval",
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["approved"] is False
    assert payload["live_enabled"] is False
    assert payload["calibration"]["reason_codes"] == ["CALIBRATION_ARTIFACT_MISSING"]
    assert "no_live_safety_issues" in payload["missing"]
