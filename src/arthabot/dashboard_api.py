from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from queue import Queue
import threading

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


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "PAPER"}

def broadcast_update(payload: dict):
    """Called by the bot to send data to the dashboard."""
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
    while True:
        if not _state_queue.empty():
            payload = _state_queue.get()
            # We must iterate over a copy of the set because it might change during iteration
            for connection in list(active_connections):
                try:
                    await connection.send_json(payload)
                except Exception:
                    active_connections.discard(connection)
        await asyncio.sleep(0.01)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_queue_broadcaster())
