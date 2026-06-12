import pytest
from fastapi.testclient import TestClient
from arthabot.dashboard_api import app, broadcast_update, set_runtime_health

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
