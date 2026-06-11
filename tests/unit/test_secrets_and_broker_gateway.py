from decimal import Decimal

import pytest

from arthabot.broker_gateway import BrokerOrderRequest, BrokerOrderResponse, ZerodhaGateway
from arthabot.common import Direction
from arthabot.secrets import SecretConfig, load_secret_config, load_secret_export


def test_secret_config_loads_from_environment_without_values_in_repr(monkeypatch):
    monkeypatch.setenv("ZERODHA_API_KEY", "key-123")
    monkeypatch.setenv("ZERODHA_API_SECRET", "secret-456")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "token-789")
    monkeypatch.setenv("NEWS_API_KEY", "news-000")

    config = load_secret_config()

    assert config.has_zerodha_credentials
    assert "key-123" not in repr(config)
    assert "secret-456" not in repr(config)
    assert "token-789" not in repr(config)


def test_secret_config_rejects_missing_required_live_credentials(monkeypatch):
    monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
    monkeypatch.delenv("ZERODHA_API_SECRET", raising=False)
    monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)

    with pytest.raises(ValueError, match="ZERODHA"):
        SecretConfig.from_env(require_zerodha=True)


def test_zerodha_gateway_requires_credentials_before_order_submission():
    gateway = ZerodhaGateway(secret_config=SecretConfig())
    request = BrokerOrderRequest(symbol="INFY", direction=Direction.LONG, quantity=1, price=Decimal("100"))

    with pytest.raises(PermissionError, match="credentials"):
        gateway.place_intraday_order(request)


def test_zerodha_gateway_adapter_returns_normalized_response_without_real_network_call():
    seen: list[BrokerOrderRequest] = []

    def fake_submit(request: BrokerOrderRequest) -> BrokerOrderResponse:
        seen.append(request)
        return BrokerOrderResponse(order_id="kite-1", status="OPEN", raw={"token": "not-logged"})

    gateway = ZerodhaGateway(
        secret_config=SecretConfig(
            zerodha_api_key="key",
            zerodha_api_secret="secret",
            zerodha_access_token="token",
        ),
        submit_order=fake_submit,
    )
    request = BrokerOrderRequest(symbol="INFY", direction=Direction.SHORT, quantity=2, price=Decimal("100"))

    response = gateway.place_intraday_order(request)

    assert response.order_id == "kite-1"
    assert response.status == "OPEN"
    assert seen == [request]


def test_secret_export_imports_kite_and_news_values_in_memory(tmp_path):
    path = tmp_path / "secrets.txt"
    path.write_text(
        "API KEY: kite-key\nAPI secret: kite-secret\nNewsapi.org API: news-key\n",
        encoding="utf-8",
    )
    path.chmod(0o600)

    config = load_secret_export(path)

    assert config.zerodha_api_key == "kite-key"
    assert config.zerodha_api_secret == "kite-secret"
    assert config.zerodha_access_token is None
    assert config.news_api_key == "news-key"
    assert config.has_zerodha_credentials is False
    assert "kite-key" not in repr(config)
    assert "news-key" not in repr(config)


def test_secret_export_imports_optional_access_token(tmp_path):
    path = tmp_path / "secrets.txt"
    path.write_text(
        "API KEY: key\nAPI secret: secret\nAccess token: token\nNewsapi.org API: news\n",
        encoding="utf-8",
    )
    path.chmod(0o600)

    assert load_secret_export(path).has_zerodha_credentials is True


def test_secret_export_rejects_unsafe_permissions_without_exposing_values(tmp_path):
    path = tmp_path / "secrets.txt"
    path.write_text("API KEY: private-value\n", encoding="utf-8")
    path.chmod(0o644)

    with pytest.raises(PermissionError) as error:
        load_secret_export(path)

    assert "private-value" not in str(error.value)


def test_secret_export_rejects_duplicate_recognized_label(tmp_path):
    path = tmp_path / "secrets.txt"
    path.write_text(
        "API KEY: first\nAPI KEY: second\nAPI secret: secret\nNewsapi.org API: news\n",
        encoding="utf-8",
    )
    path.chmod(0o600)

    with pytest.raises(ValueError, match="duplicate secret field"):
        load_secret_export(path)
