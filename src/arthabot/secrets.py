from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat


@dataclass(frozen=True, repr=False)
class SecretConfig:
    zerodha_api_key: str | None = None
    zerodha_api_secret: str | None = None
    zerodha_access_token: str | None = None
    news_api_key: str | None = None

    @classmethod
    def from_env(cls, *, require_zerodha: bool = False) -> "SecretConfig":
        config = cls(
            zerodha_api_key=os.getenv("ZERODHA_API_KEY"),
            zerodha_api_secret=os.getenv("ZERODHA_API_SECRET"),
            zerodha_access_token=os.getenv("ZERODHA_ACCESS_TOKEN"),
            news_api_key=os.getenv("NEWS_API_KEY"),
        )
        if require_zerodha and not config.has_zerodha_credentials:
            raise ValueError("ZERODHA credentials are required for live broker operations")
        return config

    @property
    def has_zerodha_credentials(self) -> bool:
        return self.has_zerodha_api_credentials and bool(self.zerodha_access_token)

    @property
    def has_zerodha_api_credentials(self) -> bool:
        return bool(self.zerodha_api_key and self.zerodha_api_secret)

    def __repr__(self) -> str:
        return (
            "SecretConfig("
            f"zerodha_api_key={self._mask(self.zerodha_api_key)}, "
            f"zerodha_api_secret={self._mask(self.zerodha_api_secret)}, "
            f"zerodha_access_token={self._mask(self.zerodha_access_token)}, "
            f"news_api_key={self._mask(self.news_api_key)}"
            ")"
        )

    @staticmethod
    def _mask(value: str | None) -> str:
        return "[SET]" if value else "[MISSING]"


def load_secret_config(*, require_zerodha: bool = False) -> SecretConfig:
    return SecretConfig.from_env(require_zerodha=require_zerodha)


def load_secret_export(path: str | Path) -> SecretConfig:
    source = Path(path)
    try:
        mode = stat.S_IMODE(source.stat().st_mode)
    except OSError as exc:
        raise ValueError("secret export is unavailable") from exc
    if not source.is_file() or mode & 0o077:
        raise PermissionError("secret export must be an owner-only regular file")

    labels = {
        "api key": "zerodha_api_key",
        "api secret": "zerodha_api_secret",
        "access token": "zerodha_access_token",
        "newsapi.org api": "news_api_key",
    }
    values: dict[str, str] = {}
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        if ":" not in raw_line:
            continue
        raw_label, raw_value = raw_line.split(":", 1)
        field = labels.get(raw_label.strip().lower())
        if field is None:
            continue
        if field in values:
            raise ValueError("duplicate secret field")
        value = raw_value.strip()
        if not value:
            raise ValueError("recognized secret field is empty")
        values[field] = value

    required = {"zerodha_api_key", "zerodha_api_secret", "news_api_key"}
    if not required.issubset(values):
        raise ValueError("required secret fields are missing")
    return SecretConfig(**values)
