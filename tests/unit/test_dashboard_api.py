import pytest
from fastapi.testclient import TestClient
from arthabot.dashboard_api import (
    DashboardZerodhaAuth,
    app,
    broadcast_update,
    configure_runtime_state,
    configure_zerodha_auth,
    set_runtime_health,
)
from arthabot.runtime_state import RuntimeStateStore

client = TestClient(app)

def test_websocket_broadcast():
    # We must use the context manager to trigger startup events
    with TestClient(app) as client:
        # Push an update to the queue
        broadcast_update({"type": "P_AND_L_UPDATE", "value": 1500})
        
        with client.websocket_connect("/ws") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "P_AND_L_UPDATE"
            assert data["value"] == 1500


def test_websocket_accepts_client_heartbeat_without_disconnect():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            assert websocket.receive_json()["type"] == "P_AND_L_UPDATE"
            websocket.send_text("ping")
            broadcast_update({"type": "HEARTBEAT_TEST"})
            assert websocket.receive_json()["type"] == "HEARTBEAT_TEST"


def test_health_reports_trading_readiness_separately_from_liveness():
    set_runtime_health(trading_ready=False, reason_code="KITE_AUTHENTICATION_FAILED")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "mode": "PAPER",
        "trading_ready": False,
        "reason_code": "KITE_AUTHENTICATION_FAILED",
    }

    set_runtime_health(trading_ready=True, reason_code="READY")
    assert client.get("/health").json()["status"] == "ok"


def test_dashboard_restores_last_persisted_runtime_state(tmp_path):
    store = RuntimeStateStore(tmp_path / "runtime.json")
    store.save({"mode": "PAPER", "capital": 5012.5, "total_trades": 3})
    configure_runtime_state(store)

    response = client.get("/state")

    assert response.status_code == 200
    assert response.json()["capital"] == 5012.5
    assert response.json()["total_trades"] == 3


def test_websocket_sends_last_persisted_state_immediately(tmp_path):
    store = RuntimeStateStore(tmp_path / "runtime.json")
    store.save({"type": "MARKET_TICK", "capital": 5253.7, "total_trades": 3})
    configure_runtime_state(store)

    with TestClient(app) as websocket_client:
        with websocket_client.websocket_connect("/ws") as websocket:
            assert websocket.receive_json() == {
                "type": "MARKET_TICK",
                "capital": 5253.7,
                "total_trades": 3,
            }


class FakeRemoteRenewal:
    login_url = "https://kite.example/login"

    def exchange(self, redirect_url):
        assert "request_token=request-123" in redirect_url
        return type("Result", (), {"user_id": "AB1234"})()


def test_dashboard_exposes_login_url_and_exchanges_redirect_without_access_token():
    configure_zerodha_auth(
        DashboardZerodhaAuth(renewal=FakeRemoteRenewal())
    )

    login = client.get("/auth/zerodha")
    exchange = client.post(
        "/auth/zerodha/exchange",
        json={"redirect_url": "https://example.test/?request_token=request-123&action=login"},
    )

    assert login.json() == {"login_url": "https://kite.example/login"}
    assert exchange.status_code == 200
    assert exchange.json() == {
        "status": "validated",
        "user_id": "AB1234",
        "restart_required": True,
    }
    assert "access_token" not in exchange.text
