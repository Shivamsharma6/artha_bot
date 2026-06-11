from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat

from arthabot.common import Mode
from arthabot.config import RuntimeConfig
from arthabot.deployment_config import DeploymentConfig
from arthabot.secrets import SecretConfig


@dataclass(frozen=True)
class DeploymentHandlerEvidence:
    live_feed_supervision: bool
    learning_rerun: bool
    strategy_calibration: bool
    forced_square_off: bool = False


@dataclass(frozen=True)
class SensitiveFileEvidence:
    path: Path
    git_ignored: bool


@dataclass(frozen=True)
class DeploymentPreflightRequest:
    deployment: DeploymentConfig
    runtime: RuntimeConfig
    secrets: SecretConfig
    handlers: DeploymentHandlerEvidence
    audit_path: Path
    instrument_store_path: Path
    sensitive_files: tuple[SensitiveFileEvidence, ...]
    ssh_key_path: Path


@dataclass(frozen=True)
class DeploymentPreflightCheck:
    name: str
    passed: bool
    reason_code: str


@dataclass(frozen=True)
class DeploymentPreflightResult:
    ready: bool
    reason_codes: tuple[str, ...]
    local_reason_codes: tuple[str, ...]
    external_reason_codes: tuple[str, ...]
    checks: tuple[DeploymentPreflightCheck, ...]


class DeploymentPreflight:
    def evaluate(self, request: DeploymentPreflightRequest) -> DeploymentPreflightResult:
        checks = [
            self._check("deployment_mode", request.deployment.mode == Mode.PAPER, "DEPLOYMENT_MODE_NOT_PAPER"),
            self._check("runtime_mode", request.runtime.mode.default_mode == Mode.PAPER, "RUNTIME_MODE_NOT_PAPER"),
            self._check(
                "live_disabled",
                not request.deployment.live_enabled and not request.runtime.mode.live_enabled,
                "LIVE_ENABLED",
            ),
            self._check(
                "human_approval_required",
                request.runtime.mode.requires_human_live_approval,
                "HUMAN_APPROVAL_GATE_DISABLED",
            ),
            self._check("leverage_disabled", not request.runtime.risk.leverage_allowed, "LEVERAGE_ENABLED"),
            self._check(
                "zerodha_api_credentials",
                request.secrets.has_zerodha_api_credentials,
                "ZERODHA_API_CREDENTIALS_MISSING",
            ),
            self._check(
                "kite_access_token",
                bool(request.secrets.zerodha_access_token),
                "KITE_ACCESS_TOKEN_MISSING",
            ),
            self._check("news_api_key", bool(request.secrets.news_api_key), "NEWS_API_KEY_MISSING"),
            self._check(
                "live_feed_handler",
                request.handlers.live_feed_supervision,
                "LIVE_FEED_HANDLER_MISSING",
            ),
            self._check(
                "learning_rerun_handler",
                request.handlers.learning_rerun,
                "LEARNING_RERUN_HANDLER_MISSING",
            ),
            self._check(
                "calibration_handler",
                request.handlers.strategy_calibration,
                "CALIBRATION_HANDLER_MISSING",
            ),
            self._check(
                "forced_square_off_handler",
                request.handlers.forced_square_off,
                "FORCED_SQUARE_OFF_HANDLER_MISSING",
            ),
            self._check_path("audit_path", request.audit_path, "AUDIT_PATH_UNWRITABLE"),
            self._check_path(
                "instrument_store_path",
                request.instrument_store_path,
                "INSTRUMENT_STORE_PATH_UNWRITABLE",
            ),
        ]
        for evidence in request.sensitive_files:
            checks.append(
                self._check(
                    "sensitive_file_permissions",
                    self._is_owner_only(evidence.path),
                    "SENSITIVE_FILE_PERMISSIONS_UNSAFE",
                )
            )
            checks.append(
                self._check(
                    "sensitive_file_ignored",
                    evidence.git_ignored,
                    "SENSITIVE_FILE_NOT_IGNORED",
                )
            )
        checks.extend(
            [
                self._check("ssh_key_exists", request.ssh_key_path.is_file(), "SSH_KEY_MISSING"),
                self._check(
                    "ssh_key_permissions",
                    self._is_owner_only(request.ssh_key_path),
                    "SSH_KEY_PERMISSIONS_UNSAFE",
                ),
            ]
        )
        reason_codes = tuple(check.reason_code for check in checks if not check.passed)
        external_codes = {
            "ZERODHA_API_CREDENTIALS_MISSING",
            "KITE_ACCESS_TOKEN_MISSING",
            "NEWS_API_KEY_MISSING",
        }
        return DeploymentPreflightResult(
            ready=not reason_codes,
            reason_codes=reason_codes,
            local_reason_codes=tuple(code for code in reason_codes if code not in external_codes),
            external_reason_codes=tuple(code for code in reason_codes if code in external_codes),
            checks=tuple(checks),
        )

    @staticmethod
    def _check(name: str, passed: bool, reason_code: str) -> DeploymentPreflightCheck:
        return DeploymentPreflightCheck(name=name, passed=passed, reason_code=reason_code)

    def _check_path(self, name: str, path: Path, reason_code: str) -> DeploymentPreflightCheck:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            probe = path.parent / ".arthabot-write-probe"
            probe.touch(exist_ok=False)
            probe.unlink()
        except OSError:
            return self._check(name, False, reason_code)
        return self._check(name, True, reason_code)

    @staticmethod
    def _is_owner_only(path: Path) -> bool:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            return False
        return path.is_file() and mode & 0o077 == 0
