# Paper Runtime Safety Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the PAPER runtime enforce no-leverage capital reservation, process trailing stops from broker ticks, restore durable position state, correctly identify trade exits, and square off safely.

**Architecture:** PositionTracker remains the source of truth for open positions and capital. Each position and accepted ledger row receives a stable trade ID. Runtime state serializes tracker snapshots and ledger rows together; broker feed callbacks route through PaperRuntimePipeline.on_tick. Square-off requires fresh tracked prices and fails closed if any position cannot be priced.

**Tech Stack:** Python 3.11+, dataclasses, Decimal, FastAPI dashboard runtime, pytest.

---

### Task 1: Stable trade identity and entry accounting

**Files:**
- Modify: `src/arthabot/reporting.py`
- Modify: `src/arthabot/paper_session.py`
- Modify: `src/arthabot/runtime_state.py`
- Test: `tests/unit/test_position_tracker.py`

- [ ] Add failing tests proving entry rows have zero P&L and exits update only their matching trade ID.
- [ ] Run focused tests and confirm expected failures.
- [ ] Add trade IDs to ledger records and paper intents; finalize rows by ID.
- [ ] Extend trade serialization compatibly and run focused tests.

### Task 2: Capital reservation and tracker persistence

**Files:**
- Modify: `src/arthabot/position_tracker.py`
- Modify: `src/arthabot/runtime_state.py`
- Test: `tests/unit/test_position_tracker.py`

- [ ] Add failing tests for notional reservation, release on close, duplicate trade IDs, and state round-trip.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement reserved capital accounting and tracker export/restore.
- [ ] Run focused tests.

### Task 3: Broker tick routing and exact exits

**Files:**
- Modify: `src/arthabot/live_feed.py`
- Modify: `src/arthabot/runtime_pipeline.py`
- Modify: `scripts/run_paper_loop.py`
- Test: `tests/unit/test_broker_modify_cancel_and_ws.py`
- Test: `tests/unit/test_runtime_pipeline.py`

- [ ] Add failing tests that WebSocket ticks invoke the pipeline callback and stop exits finalize the correct trade.
- [ ] Run focused tests and confirm expected failures.
- [ ] Add an injected tick handler and wire it to `pipeline.on_tick`.
- [ ] Generate stable trade IDs at approval and pass them through tracker/session.
- [ ] Run focused tests.

### Task 4: Safe square-off and dashboard state

**Files:**
- Modify: `src/arthabot/runtime_pipeline.py`
- Modify: `scripts/run_paper_loop.py`
- Test: `tests/unit/test_runtime_pipeline.py`
- Test: `tests/unit/test_dashboard_assets.py`

- [ ] Add failing tests for square-off with fresh prices and fail-closed behavior when prices are missing/stale.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement pipeline square-off and invoke it once at/after cutoff.
- [ ] Build persisted/dashboard payloads from tracker and finalized ledger state.
- [ ] Run focused tests.

### Task 5: Restart restoration and verification

**Files:**
- Modify: `scripts/run_paper_loop.py`
- Test: `tests/unit/test_dashboard_assets.py`
- Test: `tests/unit/test_runtime_state.py`

- [ ] Add failing tests for restoring tracker state and removal of dead `pipeline.trades_today` assignment.
- [ ] Implement startup restoration and atomic payload fields.
- [ ] Run full pytest, compileall, and diff checks.
- [ ] Deploy backend/dashboard and verify container stability, health, WebSocket payload, and persisted state.
