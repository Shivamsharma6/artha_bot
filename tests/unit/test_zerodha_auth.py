from pathlib import Path

import pytest

from arthabot.zerodha_auth import LoginCallback, RemoteZerodhaSessionRenewal, ZerodhaSessionRenewal


class FakeKite:
    def __init__(self):
        self.access_token = None

    def login_url(self):
        return "https://kite.example/login"

    def generate_session(self, request_token, api_secret):
        assert request_token == "request-123"
        assert api_secret == "secret"
        return {"access_token": "access-456"}

    def set_access_token(self, token):
        self.access_token = token

    def profile(self):
        assert self.access_token == "access-456"
        return {"user_id": "AB1234"}


def test_session_renewal_validates_then_stores_token(tmp_path):
    env_path = tmp_path / ".env"
    renewal = ZerodhaSessionRenewal(
        api_secret="secret",
        env_path=env_path,
        kite=FakeKite(),
        callback_receiver=lambda: LoginCallback(request_token="request-123", status="success"),
        browser_opener=lambda url: True,
    )

    result = renewal.run()

    assert result.user_id == "AB1234"
    assert env_path.read_text(encoding="utf-8") == "ZERODHA_ACCESS_TOKEN=access-456\n"


def test_session_renewal_rejects_failed_callback_without_writing_token(tmp_path):
    env_path = tmp_path / ".env"
    renewal = ZerodhaSessionRenewal(
        api_secret="secret",
        env_path=env_path,
        kite=FakeKite(),
        callback_receiver=lambda: LoginCallback(request_token=None, status="cancelled"),
        browser_opener=lambda url: True,
    )

    with pytest.raises(PermissionError, match="cancelled"):
        renewal.run()

    assert not env_path.exists()


def test_session_renewal_accepts_kite_action_login_callback(tmp_path):
    env_path = tmp_path / ".env"
    result = ZerodhaSessionRenewal(
        api_secret="secret",
        env_path=env_path,
        kite=FakeKite(),
        callback_receiver=lambda: LoginCallback(request_token="request-123", status="login"),
        browser_opener=lambda url: True,
    ).run()

    assert result.user_id == "AB1234"


def test_remote_session_renewal_accepts_pasted_redirect_url(tmp_path):
    env_path = tmp_path / ".env"
    renewal = RemoteZerodhaSessionRenewal(api_secret="secret", env_path=env_path, kite=FakeKite())

    result = renewal.exchange(
        "https://example.test/callback?request_token=request-123&action=login"
    )

    assert result.user_id == "AB1234"
    assert not hasattr(result, "access_token")
    assert env_path.read_text(encoding="utf-8") == "ZERODHA_ACCESS_TOKEN=access-456\n"


def test_remote_session_renewal_rejects_input_without_request_token(tmp_path):
    renewal = RemoteZerodhaSessionRenewal(
        api_secret="secret", env_path=tmp_path / ".env", kite=FakeKite()
    )

    with pytest.raises(ValueError, match="request_token"):
        renewal.exchange("https://example.test/callback?action=login")
