from dataclasses import dataclass
import hmac
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
from queue import Queue
import threading
from arthabot.runtime_state import RuntimeStateStore
from arthabot.zerodha_auth import SessionRenewalResult
from arthabot.audit_store import JsonlAuditStore

app = FastAPI()

# Allow CORS for the dashboard frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread-safe queue to receive updates from the bot loop
_state_queue = Queue()

# Store active connections
active_connections = set()
_runtime_health_lock = threading.Lock()
_runtime_health = {
    "status": "degraded",
    "mode": "PAPER",
    "trading_ready": False,
    "reason_code": "STARTING",
}
_runtime_state_store: RuntimeStateStore | None = None
_runtime_state: dict = {}


class RemoteRenewal(Protocol):
    @property
    def login_url(self) -> str: ...
    def exchange(self, redirect_url_or_token: str) -> SessionRenewalResult: ...


@dataclass(frozen=True)
class DashboardZerodhaAuth:
    renewal: RemoteRenewal
    audit: JsonlAuditStore | None = None


class ZerodhaExchangeRequest(BaseModel):
    redirect_url: str


_zerodha_auth: DashboardZerodhaAuth | None = None


def configure_zerodha_auth(config: DashboardZerodhaAuth | None) -> None:
    global _zerodha_auth
    _zerodha_auth = config


def _require_auth() -> DashboardZerodhaAuth:
    if _zerodha_auth is None:
        raise HTTPException(status_code=503, detail="Zerodha dashboard authentication is not configured")
    return _zerodha_auth


def configure_runtime_state(store: RuntimeStateStore) -> None:
    global _runtime_state_store, _runtime_state
    _runtime_state_store = store
    _runtime_state = store.load_or_default()


def set_runtime_health(*, trading_ready: bool, reason_code: str) -> None:
    with _runtime_health_lock:
        _runtime_health.update(
            status="ok" if trading_ready else "degraded",
            trading_ready=trading_ready,
            reason_code=reason_code,
        )


@app.get("/health")
async def health():
    with _runtime_health_lock:
        return dict(_runtime_health)


@app.get("/state")
async def state():
    return dict(_runtime_state)


@app.get("/auth/zerodha")
async def zerodha_login():
    auth = _require_auth()
    return {"login_url": auth.renewal.login_url}


@app.post("/auth/zerodha/exchange")
async def zerodha_exchange(request: ZerodhaExchangeRequest):
    auth = _require_auth()
    try:
        result = auth.renewal.exchange(request.redirect_url)
    except (ValueError, PermissionError) as exc:
        if auth.audit is not None:
            auth.audit.append(event_type="zerodha_dashboard_exchange_rejected", payload={"error_type": type(exc).__name__})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if auth.audit is not None:
            auth.audit.append(event_type="zerodha_dashboard_exchange_failed", payload={"error_type": type(exc).__name__})
        raise HTTPException(status_code=502, detail="Zerodha session exchange failed") from exc
    if auth.audit is not None:
        auth.audit.append(event_type="zerodha_dashboard_exchange_completed", payload={"user_id": result.user_id})
    
    async def _delayed_restart():
        await asyncio.sleep(1)
        import os
        os._exit(0)
    
    asyncio.create_task(_delayed_restart())
    return {"status": "validated", "user_id": result.user_id, "restart_required": True}

def broadcast_update(payload: dict):
    """Called by the bot to send data to the dashboard."""
    global _runtime_state
    _runtime_state = dict(payload)
    if _runtime_state_store is not None:
        _runtime_state_store.save(_runtime_state)
    _state_queue.put(payload)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    try:
        while True:
            # Wait for messages to keep the connection open and handle disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.discard(websocket)

async def _queue_broadcaster():
    """Background task to read from queue and broadcast."""
    import logging
    last_heartbeat = asyncio.get_event_loop().time()
    while True:
        if not _state_queue.empty():
            payload = _state_queue.get()
            for connection in list(active_connections):
                try:
                    await connection.send_json(payload)
                except Exception as e:
                    logging.error(f"WebSocket broadcast failed: {e}")
                    active_connections.discard(connection)
            last_heartbeat = asyncio.get_event_loop().time()
        else:
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat > 5.0:
                for connection in list(active_connections):
                    try:
                        await connection.send_json({"type": "HEARTBEAT"})
                    except Exception as e:
                        logging.error(f"WebSocket heartbeat failed: {e}")
                        active_connections.discard(connection)
                last_heartbeat = now
        await asyncio.sleep(0.01)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_queue_broadcaster())
