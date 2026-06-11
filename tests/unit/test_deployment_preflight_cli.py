import json

from arthabot.deployment_preflight_cli import main


def test_deployment_preflight_cli_writes_redacted_ready_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERODHA_API_KEY", "key-secret-value")
    monkeypatch.setenv("ZERODHA_API_SECRET", "api-secret-value")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "access-token-value")
    monkeypatch.setenv("NEWS_API_KEY", "news-secret-value")
    ssh_key = tmp_path / "deploy.pem"
    ssh_key.write_text("private-key-value", encoding="utf-8")
    ssh_key.chmod(0o600)
    sensitive = tmp_path / "secrets.txt"
    sensitive.write_text("credential-value", encoding="utf-8")
    sensitive.chmod(0o600)
    output = tmp_path / "preflight.json"

    exit_code = main(
        [
            "--config-dir",
            "config",
            "--audit-path",
            str(tmp_path / "audit.jsonl"),
            "--instrument-store-path",
            str(tmp_path / "data" / "instruments.json"),
            "--output",
            str(output),
            "--ssh-key",
            str(ssh_key),
            "--sensitive-file",
            str(sensitive),
            "--sensitive-files-ignored",
            "--live-feed-handler-configured",
            "--learning-rerun-handler-configured",
            "--strategy-calibration-handler-configured",
        ]
    )

    raw = output.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert exit_code == 0
    assert payload["ready"] is True
    assert "key-secret-value" not in raw
    assert "private-key-value" not in raw
    assert str(ssh_key) not in raw


def test_deployment_preflight_cli_returns_nonzero_for_missing_access_token(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERODHA_API_KEY", "set")
    monkeypatch.setenv("ZERODHA_API_SECRET", "set")
    monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("NEWS_API_KEY", "set")
    ssh_key = tmp_path / "deploy.pem"
    ssh_key.write_text("key", encoding="utf-8")
    ssh_key.chmod(0o600)
    sensitive = tmp_path / "secrets.txt"
    sensitive.write_text("secret", encoding="utf-8")
    sensitive.chmod(0o600)
    output = tmp_path / "preflight.json"

    exit_code = main(
        [
            "--config-dir",
            "config",
            "--audit-path",
            str(tmp_path / "audit.jsonl"),
            "--instrument-store-path",
            str(tmp_path / "instruments.json"),
            "--output",
            str(output),
            "--ssh-key",
            str(ssh_key),
            "--sensitive-file",
            str(sensitive),
            "--sensitive-files-ignored",
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["external_reason_codes"] == ["KITE_ACCESS_TOKEN_MISSING"]
    assert "LIVE_FEED_HANDLER_MISSING" in payload["reason_codes"]
    assert "LIVE_FEED_HANDLER_MISSING" in payload["local_reason_codes"]
