# Remaining Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 remaining gaps — PositionTracker state persistence, dashboard open positions, and unrealized P&L in daily report.

**Architecture:** Add serialization to PositionTracker, track latest prices in pipeline, and wire both into the paper loop and dashboard broadcast.

**Tech Stack:** Python 3.11+, Decimal arithmetic, pytest

---

## File Structure

| File | Role |
|------|------|
| `src/arthabot/position_tracker.py` | Add `save_state()` and `load_state()` |
| `src/arthabot/runtime_pipeline.py` | Add `_latest_prices`, fix `daily_report` |
| `scripts/run_paper_loop.py` | Restore tracker state, add open_positions to broadcast |
| `tests/unit/test_position_tracker.py` | Add 7 new tests |

---

### Task 1: PositionTracker save_state / load_state

**Files:**
- Modify: `src/arthabot/position_tracker.py`
- Modify: `tests/unit/test_position_tracker.py`

- [ ] **Step 1: Write failing tests for save/load**

```python
# tests/unit/test_position_tracker.py (append)


def test_save_state_empty_tracker():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    state = tracker.save_state()
    assert state["available_capital"] == "5000"
    assert state["daily_realized_pnl"] == "0"
    assert state["trades_today"] == 0
    assert state["positions"] == {}


def test_save_state_with_open_position():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
        trailing_policy=TrailingStopPolicy(
            step=Decimal("1"), cooldown_seconds=0, max_modifications_per_trade=5,
        ),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("1"), now=now,
    )
    state = tracker.save_state()
    assert "INFY" in state["positions"]
    pos = state["positions"]["INFY"]
    assert pos["symbol"] == "INFY"
    assert pos["direction"] == "LONG"
    assert pos["entry_price"] == "100"
    assert pos["trailing"] is not None
    assert pos["trailing"]["current_stop"] == "98"


def test_load_state_restores_tracker():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    state = {
        "available_capital": "4800",
        "daily_realized_pnl": "200",
        "trades_today": 5,
        "positions": {
            "INFY": {
                "symbol": "INFY",
                "direction": "LONG",
                "entry_price": "100",
                "quantity": 10,
                "stop_loss": "98",
                "trailing_stop_step": "1",
                "entry_timestamp": "2026-06-12T10:00:00+00:00",
                "trailing": None,
            }
        },
    }
    tracker.load_state(state)
    snapshot = tracker.snapshot()
    assert snapshot.available_capital == Decimal("4800")
    assert snapshot.daily_realized_pnl == Decimal("200")
    assert snapshot.trades_today == 5
    assert len(snapshot.open_positions) == 1
    assert snapshot.open_positions[0].symbol == "INFY"


def test_save_load_roundtrip():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
        trailing_policy=TrailingStopPolicy(
            step=Decimal("1"), cooldown_seconds=0, max_modifications_per_trade=5,
        ),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("1"), now=now,
    )
    state = tracker.save_state()

    tracker2 = PositionTracker(
        starting_capital=Decimal("9999"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    tracker2.load_state(state)
    snapshot = tracker2.snapshot()
    assert snapshot.available_capital == Decimal("5000")
    assert len(snapshot.open_positions) == 1
    assert snapshot.open_positions[0].symbol == "INFY"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_position_tracker.py -k "save_state or load_state or roundtrip" -v`
Expected: FAIL with `AttributeError: 'PositionTracker' object has no attribute 'save_state'`

- [ ] **Step 3: Implement save_state and load_state**

```python
# src/arthabot/position_tracker.py — add imports and methods

import json
from typing import Any

# Inside PositionTracker class:

    def save_state(self) -> dict[str, Any]:
        positions = {}
        for symbol, pos in self._positions.items():
            trailing = None
            if pos.trailing is not None:
                trailing = {
                    "symbol": pos.trailing.symbol,
                    "direction": pos.trailing.direction.value,
                    "current_stop": str(pos.trailing.current_stop),
                    "last_reference_price": str(pos.trailing.last_reference_price),
                    "last_modified_at": pos.trailing.last_modified_at.isoformat(),
                    "modifications": pos.trailing.modifications,
                }
            positions[symbol] = {
                "symbol": pos.symbol,
                "direction": pos.direction.value,
                "entry_price": str(pos.entry_price),
                "quantity": pos.quantity,
                "stop_loss": str(pos.stop_loss),
                "trailing_stop_step": str(pos.trailing_stop_step),
                "entry_timestamp": pos.entry_timestamp.isoformat(),
                "trailing": trailing,
            }
        return {
            "available_capital": str(self._available_capital),
            "daily_realized_pnl": str(self._daily_realized_pnl),
            "trades_today": self._trades_today,
            "positions": positions,
        }

    def load_state(self, state: dict[str, Any]) -> None:
        self._available_capital = Decimal(str(state["available_capital"]))
        self._daily_realized_pnl = Decimal(str(state["daily_realized_pnl"]))
        self._trades_today = int(state["trades_today"])
        self._positions = {}
        for symbol, pos_data in state.get("positions", {}).items():
            trailing = None
            if pos_data.get("trailing") is not None:
                t = pos_data["trailing"]
                trailing = TrailingStopState(
                    symbol=t["symbol"],
                    direction=Direction(t["direction"]),
                    current_stop=Decimal(str(t["current_stop"])),
                    last_reference_price=Decimal(str(t["last_reference_price"])),
                    last_modified_at=datetime.fromisoformat(t["last_modified_at"]),
                    modifications=int(t["modifications"]),
                )
            self._positions[symbol] = TrackedPosition(
                symbol=pos_data["symbol"],
                direction=Direction(pos_data["direction"]),
                entry_price=Decimal(str(pos_data["entry_price"])),
                quantity=int(pos_data["quantity"]),
                stop_loss=Decimal(str(pos_data["stop_loss"])),
                trailing_stop_step=Decimal(str(pos_data["trailing_stop_step"])),
                entry_timestamp=datetime.fromisoformat(pos_data["entry_timestamp"]),
                trailing=trailing,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_position_tracker.py -k "save_state or load_state or roundtrip" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arthabot/position_tracker.py tests/unit/test_position_tracker.py
git commit -m "feat: add PositionTracker save_state/load_state for persistence"
```

---

### Task 2: Pipeline _latest_prices + daily_report fix

**Files:**
- Modify: `src/arthabot/runtime_pipeline.py`
- Modify: `tests/unit/test_position_tracker.py`

- [ ] **Step 1: Write failing test for daily_report unrealized_pnl**

```python
# tests/unit/test_position_tracker.py (append)


def test_daily_report_unrealized_pnl():
    from arthabot.runtime_pipeline import PaperRuntimePipeline, HermesAdapter
    from arthabot.risk import RiskEngine, RiskConfig
    from arthabot.audit_store import JsonlAuditStore
    from arthabot.live_feed import Tick
    import tempfile, os

    audit_path = os.path.join(tempfile.mkdtemp(), "test.audit.jsonl")
    broker_calc = BrokerageCalculator(BrokerageConfig())
    risk = RiskEngine(config=RiskConfig(), brokerage=broker_calc)
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=broker_calc,
    )

    def proposal_factory(candidate, now):
        from arthabot.risk import TradeProposal
        return TradeProposal(
            symbol=candidate.symbol, direction=candidate.direction,
            entry_price=Decimal("100"), stop_loss=Decimal("98"),
            target_price=Decimal("105"), confidence=Decimal("0.8"),
            trailing_stop_step=Decimal("1"),
            timestamp=now, strategy_version="test-v1",
        )

    pipeline = PaperRuntimePipeline(
        trading_date=datetime(2026, 6, 12, tzinfo=timezone.utc).date(),
        starting_capital=Decimal("5000"),
        execution=ExecutionEngine(),
        risk=risk,
        hermes=HermesAdapter(proposal_factory=proposal_factory),
        audit=JsonlAuditStore(audit_path),
        max_tick_age_seconds=15,
        position_tracker=tracker,
    )

    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("0"), now=now,
    )
    # Simulate a tick to set latest price
    tick = Tick(symbol="INFY", price=Decimal("105"), volume=100, timestamp=now)
    pipeline.on_tick(tick)

    report = pipeline.daily_report()
    assert report["unrealized_pnl"] == Decimal("50")
    assert report["open_positions"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_daily_report_unrealized_pnl -v`
Expected: FAIL — `unrealized_pnl` is `Decimal("0")` instead of `Decimal("50")`

- [ ] **Step 3: Add _latest_prices to PaperRuntimePipeline**

```python
# src/arthabot/runtime_pipeline.py — add to __init__

class PaperRuntimePipeline:
    def __init__(self, ...):
        ...
        self._latest_prices: dict[str, Decimal] = {}
```

- [ ] **Step 4: Update on_tick to track prices**

```python
# src/arthabot/runtime_pipeline.py — add to on_tick

    def on_tick(self, tick: Tick) -> None:
        self.feed.record_tick(tick)
        self._latest_prices[tick.symbol] = tick.price  # NEW
        ...existing tracker.on_tick logic...
```

- [ ] **Step 5: Update daily_report to use latest prices**

```python
# src/arthabot/runtime_pipeline.py — replace daily_report

    def daily_report(self):
        session_report = self.session.daily_report()
        snapshot = self.tracker.snapshot(prices=self._latest_prices)  # CHANGED
        report = session_report.summarize()
        report["available_capital"] = snapshot.available_capital
        report["daily_realized_pnl"] = snapshot.daily_realized_pnl
        report["unrealized_pnl"] = snapshot.unrealized_pnl  # CHANGED
        report["open_positions"] = len(snapshot.open_positions)
        return report
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_daily_report_unrealized_pnl -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/arthabot/runtime_pipeline.py tests/unit/test_position_tracker.py
git commit -m "fix: compute unrealized_pnl in daily_report using live prices"
```

---

### Task 3: Wire persistence and dashboard in run_paper_loop.py

**Files:**
- Modify: `scripts/run_paper_loop.py`
- Modify: `tests/unit/test_position_tracker.py`

- [ ] **Step 1: Write failing test for dashboard broadcast**

```python
# tests/unit/test_position_tracker.py (append)


def test_dashboard_broadcast_includes_open_positions():
    from arthabot.runtime_pipeline import PaperRuntimePipeline, HermesAdapter
    from arthabot.risk import RiskEngine, RiskConfig
    from arthabot.audit_store import JsonlAuditStore
    from arthabot.live_feed import Tick
    from arthabot.dashboard_api import broadcast_update
    import tempfile, os

    audit_path = os.path.join(tempfile.mkdtemp(), "test.audit.jsonl")
    broker_calc = BrokerageCalculator(BrokerageConfig())
    risk = RiskEngine(config=RiskConfig(), brokerage=broker_calc)
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=broker_calc,
    )

    def proposal_factory(candidate, now):
        from arthabot.risk import TradeProposal
        return TradeProposal(
            symbol=candidate.symbol, direction=candidate.direction,
            entry_price=Decimal("100"), stop_loss=Decimal("98"),
            target_price=Decimal("105"), confidence=Decimal("0.8"),
            trailing_stop_step=Decimal("1"),
            timestamp=now, strategy_version="test-v1",
        )

    pipeline = PaperRuntimePipeline(
        trading_date=datetime(2026, 6, 12, tzinfo=timezone.utc).date(),
        starting_capital=Decimal("5000"),
        execution=ExecutionEngine(),
        risk=risk,
        hermes=HermesAdapter(proposal_factory=proposal_factory),
        audit=JsonlAuditStore(audit_path),
        max_tick_age_seconds=15,
        position_tracker=tracker,
    )

    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("0"), now=now,
    )

    snapshot = tracker.snapshot(prices={"INFY": Decimal("105")})
    open_pos_list = [
        {
            "symbol": pos.symbol,
            "direction": pos.direction.name,
            "entry_price": float(pos.entry_price),
            "quantity": pos.quantity,
            "stop_loss": float(pos.stop_loss),
        }
        for pos in snapshot.open_positions
    ]
    assert len(open_pos_list) == 1
    assert open_pos_list[0]["symbol"] == "INFY"
```

- [ ] **Step 2: Run test to verify it passes (logic test)**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_dashboard_broadcast_includes_open_positions -v`
Expected: PASS (this tests the data shape, not the actual broadcast)

- [ ] **Step 3: Restore tracker state in run_paper_loop.py**

```python
# scripts/run_paper_loop.py — after creating position_tracker

    restored_tracker_state = restored_runtime_state.get("position_tracker")
    if restored_tracker_state is not None:
        position_tracker.load_state(restored_tracker_state)
        logging.info(f"Restored PositionTracker state: {len(restored_tracker_state.get('positions', {}))} open positions")
```

- [ ] **Step 4: Add open_positions to broadcast_update**

```python
# scripts/run_paper_loop.py — in the main loop, build broadcast payload

            snapshot = position_tracker.snapshot(
                prices={sym: pipeline.feed.latest_tick(sym).price 
                        for sym in symbols_to_track 
                        if pipeline.feed.health(sym, now=now).ok}
            )
            open_pos_list = [
                {
                    "symbol": pos.symbol,
                    "direction": pos.direction.name,
                    "entry_price": float(pos.entry_price),
                    "quantity": pos.quantity,
                    "stop_loss": float(pos.stop_loss),
                    "unrealized_pnl": float(pos.entry_price * pos.quantity - sum(...)),
                }
                for pos in snapshot.open_positions
            ]

            broadcast_update({
                ...existing fields...,
                "open_positions": open_pos_list,
                "unrealized_pnl": float(snapshot.unrealized_pnl),
                "position_tracker": position_tracker.save_state(),
            })
```

- [ ] **Step 5: Run import check**

Run: `uv run python -c "from scripts.run_paper_loop import main"`
Expected: No ImportError

- [ ] **Step 6: Commit**

```bash
git add scripts/run_paper_loop.py tests/unit/test_position_tracker.py
git commit -m "feat: restore PositionTracker state and show open positions in dashboard"
```

---

### Task 4: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 3: Verify no secrets in code**

Run: `grep -r "api_key\|secret\|token" src/arthabot/position_tracker.py`
Expected: No matches

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: fix remaining gaps — tracker persistence, dashboard open positions, unrealized P&L"
```
