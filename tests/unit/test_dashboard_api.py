import pytest
from fastapi.testclient import TestClient
from arthabot.dashboard_api import app, broadcast_update, _state_queue

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
