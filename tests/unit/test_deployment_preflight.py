from pathlib import Path

from arthabot.config import load_runtime_config
from arthabot.deployment_config import load_deployment_config
from arthabot.deployment_preflight import (
    DeploymentHandlerEvidence,
    DeploymentPreflight,
    DeploymentPreflightRequest,
    SensitiveFileEvidence,
)
from arthabot.secrets import SecretConfig


def _request(tmp_path: Path) -> DeploymentPreflightRequest:
    ssh_key = tmp_path / "deploy.pem"
    ssh_key.write_text("test-key", encoding="utf-8")
    ssh_key.chmod(0o600)
    sensitive = tmp_path / "secrets.txt"
    sensitive.write_text("redacted", encoding="utf-8")
    sensitive.chmod(0o600)
    return DeploymentPreflightRequest(
        deployment=load_deployment_config("config"),
        runtime=load_runtime_config("config"),
        secrets=SecretConfig(
            zerodha_api_key="set",
            zerodha_api_secret="set",
            zerodha_access_token="set",
            news_api_key="set",
        ),
        handlers=DeploymentHandlerEvidence(
            live_feed_supervision=True,
            learning_rerun=True,
            strategy_calibration=True,
            forced_square_off=True,
        ),
        audit_path=tmp_path / "logs" / "audit.jsonl",
        instrument_store_path=tmp_path / "data" / "instruments.json",
        sensitive_files=(SensitiveFileEvidence(path=sensitive, git_ignored=True),),
        ssh_key_path=ssh_key,
    )


def test_deployment_preflight_accepts_complete_paper_evidence(tmp_path):
    result = DeploymentPreflight().evaluate(_request(tmp_path))

    assert result.ready is True
    assert result.reason_codes == ()
    assert result.local_reason_codes == ()
    assert result.external_reason_codes == ()
    assert all(check.passed for check in result.checks)


def test_deployment_preflight_reports_missing_credentials_and_handlers(tmp_path):
    request = _request(tmp_path)
    request = DeploymentPreflightRequest(
        deployment=request.deployment,
        runtime=request.runtime,
        secrets=SecretConfig(zerodha_api_key="set"),
        handlers=DeploymentHandlerEvidence(
            live_feed_supervision=False,
            learning_rerun=False,
            strategy_calibration=False,
            forced_square_off=False,
        ),
        audit_path=request.audit_path,
        instrument_store_path=request.instrument_store_path,
        sensitive_files=request.sensitive_files,
        ssh_key_path=request.ssh_key_path,
    )

    result = DeploymentPreflight().evaluate(request)

    assert result.ready is False
    assert "ZERODHA_API_CREDENTIALS_MISSING" in result.reason_codes
    assert "KITE_ACCESS_TOKEN_MISSING" in result.reason_codes
    assert "NEWS_API_KEY_MISSING" in result.reason_codes
    assert "LIVE_FEED_HANDLER_MISSING" in result.reason_codes
    assert "LEARNING_RERUN_HANDLER_MISSING" in result.reason_codes
    assert "CALIBRATION_HANDLER_MISSING" in result.reason_codes
    assert "FORCED_SQUARE_OFF_HANDLER_MISSING" in result.reason_codes
    assert result.external_reason_codes == (
        "ZERODHA_API_CREDENTIALS_MISSING",
        "KITE_ACCESS_TOKEN_MISSING",
        "NEWS_API_KEY_MISSING",
    )
    assert "LIVE_FEED_HANDLER_MISSING" in result.local_reason_codes
    assert "LEARNING_RERUN_HANDLER_MISSING" in result.local_reason_codes
    assert "CALIBRATION_HANDLER_MISSING" in result.local_reason_codes
    assert "FORCED_SQUARE_OFF_HANDLER_MISSING" in result.local_reason_codes


def test_deployment_preflight_reports_access_token_as_external_blocker(tmp_path):
    request = _request(tmp_path)
    request = DeploymentPreflightRequest(
        deployment=request.deployment,
        runtime=request.runtime,
        secrets=SecretConfig(
            zerodha_api_key="set",
            zerodha_api_secret="set",
            news_api_key="set",
        ),
        handlers=request.handlers,
        audit_path=request.audit_path,
        instrument_store_path=request.instrument_store_path,
        sensitive_files=request.sensitive_files,
        ssh_key_path=request.ssh_key_path,
    )

    result = DeploymentPreflight().evaluate(request)

    assert result.external_reason_codes == ("KITE_ACCESS_TOKEN_MISSING",)
    assert result.local_reason_codes == ()


def test_deployment_preflight_rejects_unsafe_sensitive_and_ssh_permissions(tmp_path):
    request = _request(tmp_path)
    request.sensitive_files[0].path.chmod(0o644)
    request.ssh_key_path.chmod(0o644)
    unsafe_sensitive = SensitiveFileEvidence(
        path=request.sensitive_files[0].path,
        git_ignored=False,
    )
    request = DeploymentPreflightRequest(
        deployment=request.deployment,
        runtime=request.runtime,
        secrets=request.secrets,
        handlers=request.handlers,
        audit_path=request.audit_path,
        instrument_store_path=request.instrument_store_path,
        sensitive_files=(unsafe_sensitive,),
        ssh_key_path=request.ssh_key_path,
    )

    result = DeploymentPreflight().evaluate(request)

    assert "SENSITIVE_FILE_PERMISSIONS_UNSAFE" in result.reason_codes
    assert "SENSITIVE_FILE_NOT_IGNORED" in result.reason_codes
    assert "SSH_KEY_PERMISSIONS_UNSAFE" in result.reason_codes


def test_deployment_preflight_reports_unwritable_persistence_parent(tmp_path):
    request = _request(tmp_path)
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("x", encoding="utf-8")
    request = DeploymentPreflightRequest(
        deployment=request.deployment,
        runtime=request.runtime,
        secrets=request.secrets,
        handlers=request.handlers,
        audit_path=blocking_file / "audit.jsonl",
        instrument_store_path=request.instrument_store_path,
        sensitive_files=request.sensitive_files,
        ssh_key_path=request.ssh_key_path,
    )

    result = DeploymentPreflight().evaluate(request)

    assert "AUDIT_PATH_UNWRITABLE" in result.reason_codes
