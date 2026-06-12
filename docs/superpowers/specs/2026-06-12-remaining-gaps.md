# Remaining Gaps — PositionTracker Persistence, Dashboard, Unrealized P&L

**Date:** 2026-06-12
**Scope:** 3 remaining gaps from the critical runtime wiring audit
**Out of scope:** Hermes-as-LLM, new strategies, new data sources

---

## Problem

After implementing PositionTracker, trailing stops, and backtest stop simulation, 3 gaps remain:

1. **PositionTracker state not restored across restarts** — `PositionTracker` starts fresh each run. Open positions, available capital, and daily P&L are lost on restart.
2. **Dashboard doesn't show open positions** — `broadcast_update` in `run_paper_loop.py` builds `positions_list` from closed trades only. Open positions from `position_tracker.snapshot()` never appear.
3. **`unrealized_pnl` in daily report is 0** — `daily_report()` in `runtime_pipeline.py` hardcodes `Decimal("0")` because it doesn't pass live prices to the tracker.

---

## Gap 1: PositionTracker State Persistence

### Approach

Add `save_state()` and `load_state()` methods to `PositionTracker`. Wire into `run_paper_loop.py` to restore state on restart using the existing `RuntimeStateStore`.

**Why not extend RuntimeStateStore directly?**
- PositionTracker owns its own internal state (`_positions`, `_available_capital`, `_daily_realized_pnl`, `_trades_today`)
- Serialization logic should live close to the data it serializes
- RuntimeStateStore stays a generic JSON file store

### Interface

```python
class PositionTracker:
    def save_state(self) -> dict[str, Any]:
        """Serialize tracker state to JSON-compatible dict."""

    def load_state(self, state: dict[str, Any]) -> None:
        """Restore tracker state from dict. Overwrites current state."""
```

### Serialization Format

```json
{
  "available_capital": "5000.00",
  "daily_realized_pnl": "125.50",
  "trades_today": 3,
  "positions": {
    "INFY": {
      "symbol": "INFY",
      "direction": "LONG",
      "entry_price": "100.00",
      "quantity": 10,
      "stop_loss": "98.00",
      "trailing_stop_step": "1.00",
      "entry_timestamp": "2026-06-12T10:00:00+00:00",
      "trailing": {
        "symbol": "INFY",
        "direction": "LONG",
        "current_stop": "101.00",
        "last_reference_price": "103.00",
        "last_modified_at": "2026-06-12T10:05:00+00:00",
        "modifications": 2
      }
    }
  }
}
```

### Wire in run_paper_loop.py

```python
# After creating PositionTracker:
restored_tracker_state = restored_runtime_state.get("position_tracker")
if restored_tracker_state is not None:
    position_tracker.load_state(restored_tracker_state)

# In the main loop, save tracker state alongside trades:
broadcast_update({
    ...existing fields...,
    "position_tracker": position_tracker.save_state(),
})
```

---

## Gap 2: Dashboard Open Positions

### Approach

Add `position_tracker.snapshot()` data to the `broadcast_update` payload in `run_paper_loop.py`. Include open positions with entry info, current stop, and unrealized P&L.

### Broadcast Payload Additions

```python
broadcast_update({
    ...existing fields...,
    "open_positions": [
        {
            "symbol": "INFY",
            "direction": "LONG",
            "entry_price": 100.0,
            "quantity": 10,
            "stop_loss": 101.0,
            "unrealized_pnl": 30.0,
        }
        for pos in snapshot.open_positions
    ],
    "unrealized_pnl": float(snapshot.unrealized_pnl),
})
```

### Price Source

Use `pipeline.feed.latest_tick(symbol).price` for each open position to compute unrealized P&L. If tick is unavailable, fall back to entry_price (conservative).

---

## Gap 3: Unrealized P&L in Daily Report

### Approach

Store latest tick prices in `PaperRuntimePipeline._latest_prices` (updated on each `on_tick`). Pass to `tracker.snapshot(prices=...)` in `daily_report()`.

### Pipeline Changes

```python
class PaperRuntimePipeline:
    def __init__(self, ...):
        ...
        self._latest_prices: dict[str, Decimal] = {}

    def on_tick(self, tick: Tick) -> None:
        self.feed.record_tick(tick)
        self._latest_prices[tick.symbol] = tick.price  # NEW
        ...existing tracker.on_tick logic...

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

---

## Testing Plan

### New Tests

**`tests/unit/test_position_tracker.py`** (append):

1. `test_save_state_empty_tracker` — empty tracker serializes correctly
2. `test_save_state_with_open_position` — position with trailing state serializes
3. `test_load_state_restores_tracker` — load_state restores all fields
4. `test_load_state_overwrites_existing` — load_state replaces current state
5. `test_save_load_roundtrip` — save → load produces identical state
6. `test_daily_report_unrealized_pnl` — pipeline.daily_report uses live prices
7. `test_dashboard_broadcast_includes_open_positions` — broadcast payload has open_positions

### Modified Tests

- `test_pipeline_uses_position_tracker_for_capital` — verify `_latest_prices` tracking

---

## Files Changed

| File | Change |
|------|--------|
| `src/arthabot/position_tracker.py` | Add `save_state()` and `load_state()` |
| `src/arthabot/runtime_pipeline.py` | Add `_latest_prices`, pass to `daily_report` |
| `scripts/run_paper_loop.py` | Restore tracker state, add open_positions to broadcast |
| `tests/unit/test_position_tracker.py` | Add 7 new tests |

---

## Implementation Order

1. PositionTracker `save_state()` / `load_state()` + tests
2. Pipeline `_latest_prices` + `daily_report` fix + tests
3. `run_paper_loop.py` — restore tracker state + dashboard open positions
4. Run full test suite
