from datetime import datetime, timezone

import pytest

from arthabot.deployment_command import build_paper_deployment_service
from arthabot.http_clients import HttpRequest


def test_build_paper_deployment_service_wires_real_provider_clients_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERODHA_API_KEY", "kite-key")
    monkeypatch.setenv("ZERODHA_API_SECRET", "kite-secret")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "kite-token")
    monkeypatch.setenv("NEWS_API_KEY", "news-key")
    seen_requests: list[HttpRequest] = []
    operational_calls: list[str] = []

    def zerodha_transport(request: HttpRequest):
        seen_requests.append(request)
        assert request.headers["Authorization"] == "token kite-key:kite-token"
        return (
            "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,"
            "tick_size,lot_size,instrument_type,segment,exchange\n"
            "408065,1594,INFY,INFOSYS,0,,,0.05,1,EQ,NSE,NSE\n"
        )

    def news_transport(request: HttpRequest):
        seen_requests.append(request)
        assert request.headers["X-Api-Key"] == "news-key"
        assert request.query["domains"] == "moneycontrol.com,economictimes.indiatimes.com,business-standard.com,livemint.com"
        return {
            "status": "ok",
            "articles": [{"title": "Infosys wins deal", "source": {"name": "Example"}}],
        }

    service = build_paper_deployment_service(
        config_dir="config",
        audit_path=tmp_path / "audit.jsonl",
        instrument_store_path=tmp_path / "instruments.json",
        zerodha_transport=zerodha_transport,
        news_transport=news_transport,
        live_feed_supervision=lambda now: operational_calls.append("feed"),
        learning_rerun=lambda now: operational_calls.append("learning"),
        strategy_calibration=lambda now: operational_calls.append("calibration"),
        interval_seconds=60,
        clock=lambda: datetime(2026, 1, 5, 16, 30, tzinfo=timezone.utc),
        sleep=lambda seconds: None,
    )

    result = service.run(max_ticks=1)

    assert not result.must_stop_trading
    assert [request.path for request in seen_requests] == [
        "/instruments/NSE",
        "/v2/everything",
        "/v2/everything",
        "/v2/everything",
    ]
    assert operational_calls == ["feed", "learning", "calibration"]


def test_build_paper_deployment_service_rejects_live_deployment_config(tmp_path, monkeypatch):
    monkeypatch.setenv("ZERODHA_API_KEY", "kite-key")
    monkeypatch.setenv("ZERODHA_API_SECRET", "kite-secret")
    monkeypatch.setenv("ZERODHA_ACCESS_TOKEN", "kite-token")
    monkeypatch.setenv("NEWS_API_KEY", "news-key")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "deployment.yaml").write_text(
        """
environment: live
mode: LIVE
live_enabled: true
scheduler:
  timezone: Asia/Kolkata
  jobs: []
""",
        encoding="utf-8",
    )

    with pytest.raises(PermissionError, match="PAPER deployment"):
        build_paper_deployment_service(
            config_dir=config_dir,
            audit_path=tmp_path / "audit.jsonl",
            instrument_store_path=tmp_path / "instruments.json",
            zerodha_transport=lambda request: {},
            news_transport=lambda request: {},
            live_feed_supervision=lambda now: {},
            learning_rerun=lambda now: {},
            strategy_calibration=lambda now: {},
        )
