# ArthaBot Live Trading Dashboard Design Spec

## Overview
This document specifies the design for a real-time, browser-based dashboard for ArthaBot. The dashboard's primary purpose is to serve as a "Live Trading Monitor", providing a clear, high-performance view of the bot's current state, open positions, and Hermes AI decision logic.

## Architecture

The system consists of two tightly integrated components:

### 1. The Python Backend (Embedded Server)
ArthaBot's existing trading loop will be augmented with an embedded WebSocket server.
*   **Framework:** `FastAPI` served via `uvicorn` (running asynchronously alongside the main trading loop).
*   **Data Flow:** The core `ExecutionEngine` and `HermesAgent` will push state updates (e.g., P&L changes, new quotes, executed orders) to an `asyncio.Queue`. 
*   **WebSocket Endpoint:** A `/ws` endpoint will read from this queue and broadcast JSON payloads to all connected dashboard clients instantly.

### 2. The Frontend Web App (Client)
A modern, standalone web application that consumes the WebSocket feed.
*   **Framework:** `Vite` utilizing vanilla JavaScript and HTML for maximum performance and simplicity, avoiding the overhead of heavy frameworks unless necessary.
*   **Styling:** Vanilla CSS following a strict dark-mode aesthetic. 
*   **Visual Design Requirements:** Must feel premium. The design will use curated HSL color palettes, backdrop-filters (glassmorphism), and micro-animations (e.g., green/red flashes on ticks) to create a dynamic, live feel.

## Layout: Focus Mode

The UI will follow a "Focus Mode" layout pattern to prioritize active risk over peripheral information.

### Header
*   **Global P&L:** A highly visible, color-coded aggregate of today's realized and unrealized profit/loss.
*   **Mode Indicator:** Clear pill badge showing if the bot is in `PAPER` or `LIVE` mode.
*   **Connection Status:** A pulsing indicator showing WebSocket health and Kite API connection status.

### Primary Content Area
*   **Active Positions:** A central table or card grid displaying current open positions.
    *   *Data per position:* Symbol, side (Long/Short), entry price, current price, dynamic stop-loss level, and unrealized P&L.
    *   *Visuals:* A mini progress bar showing how close the current price is to the stop-loss or target.

### Secondary Content Areas (Bottom/Side)
*   **Hermes Decision Feed:** A scrolling log of the most recent candidate evaluations from the Hermes AI.
    *   *Data:* Symbol, decision (Accepted/Rejected), confidence score, and a brief rationale string.
*   **System Health Log:** A lightweight terminal-style view showing major system events, error logs, and execution confirmations.

## Success Criteria
*   The dashboard updates in real-time (sub-second latency from Python to UI) without full-page reloads.
*   The UI remains responsive and visually stable even during high-frequency market ticks.
*   The codebase for the dashboard is kept separate from the core trading logic (`src/arthabot/`), residing in a new `dashboard/` or `frontend/` directory.

## Out of Scope
*   Historical analytics, backtest viewing, and multi-day charting (this is strictly a live monitor).
*   Configuring or modifying the strategy parameters from the UI (read-only for now).
*   Authentication / Login screens (assumes local network deployment for now).
