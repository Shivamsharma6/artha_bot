import stat
import pytest

from arthabot import secrets


def test_update_env_access_token_replaces_token_and_secures_file(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "ZERODHA_API_KEY=key\nZERODHA_ACCESS_TOKEN=old-token\nNEWS_API_KEY=news\n",
        encoding="utf-8",
    )
    env_path.chmod(0o644)

    secrets.update_env_access_token(env_path, "new-token")

    assert env_path.read_text(encoding="utf-8") == (
        "ZERODHA_API_KEY=key\nZERODHA_ACCESS_TOKEN=new-token\nNEWS_API_KEY=news\n"
    )
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_update_env_access_token_appends_missing_token(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("ZERODHA_API_KEY=key\n", encoding="utf-8")

    secrets.update_env_access_token(env_path, "new-token")

    assert env_path.read_text(encoding="utf-8") == (
        "ZERODHA_API_KEY=key\nZERODHA_ACCESS_TOKEN=new-token\n"
    )


def test_load_access_token_file_requires_owner_only_file(tmp_path):
    env_path = tmp_path / "zerodha.env"
    env_path.write_text("ZERODHA_ACCESS_TOKEN=new-token\n", encoding="utf-8")
    env_path.chmod(0o600)

    assert secrets.load_access_token_file(env_path) == "new-token"

    env_path.chmod(0o644)
    with pytest.raises(PermissionError, match="owner-only"):
        secrets.load_access_token_file(env_path)
