# Critical Runtime Wiring — Design Spec

**Date:** 2026-06-12
**Scope:** 4 wiring fixes to make the paper trading pipeline function correctly end-to-end
**Out of scope:** Hermes-as-LLM (deferred), new strategies, new data sources

---

## Problem

The audit found 5 critical gaps. This spec addresses 4 of them — all wiring issues where components exist but aren't connected:

1. **P&L tracking not wired** — `available_capital` never updates after trades. Compounding broken. Risk engine daily loss check disabled.
2. **Trailing stop not in paper loop** — `TrailingStopPolicy` and `BrokerTrailingStopWorkflow` exist but aren't called from `PaperRuntimePipeline`.
3. **Backtest doesn't simulate stops** — `BacktestExecutionEngine` uses fixed entry/exit prices. No stop-loss triggers, no trailing stops.
4. **Unrealized P&L not computed** — No code computes open position unrealized P&L.

---

## Approach: PositionTracker Extraction

Extract position management into a new `PositionTracker` class. The pipeline stays a thin orchestrator.

**Why not extend PaperRuntimePipeline directly?**
- Pipeline mixes orchestration with position bookkeeping
- Hard to test position logic in isolation
- Backtest engine can't reuse pipeline internals

**Why PositionTracker?**
- Clean separation: pipeline orchestrates, tracker manages positions
- Independently testable with pure logic
- Backtest engine can reuse trailing stop simulation logic
- Pipeline stays focused on feed → Hermes → risk → execution

---

## Component 1: PositionTracker

**New file:** `src/arthabot/position_tracker.py`

### Data Types

```python
@dataclass
class TrackedPosition:
    symbol: str
    direction: Direction
    entry_price: Decimal
    quantity: int
    stop_loss: Decimal
    trailing_stop_step: Decimal
    trailing: TrailingStopState | None
    entry_timestamp: datetime

@dataclass
class PositionSnapshot:
    open_positions: list[TrackedPosition]
    available_capital: Decimal
    daily_realized_pnl: Decimal
    unrealized_pnl: Decimal
    trades_today: int
    open_symbols: set[str]

@dataclass
class ExitEvent:
    symbol: str
    direction: Direction
    entry_price: Decimal
    exit_price: Decimal
    quantity: int
    gross_pnl: Decimal
    total_costs: Decimal
    net_pnl: Decimal
    reason: str  # "trailing_stop_hit" | "square_off" | "manual"
    timestamp: datetime
```

### PositionTracker Interface

```python
class PositionTracker:
    def __init__(
        self,
        *,
        starting_capital: Decimal,
        brokerage: BrokerageCalculator,
        trailing_policy: TrailingStopPolicy | None = None,
    ) -> None: ...

    def open_position(
        self,
        *,
        symbol: str,
        direction: Direction,
        entry_price: Decimal,
        quantity: int,
        stop_loss: Decimal,
        trailing_stop_step: Decimal,
        now: datetime,
    ) -> None:
        """Record a new open position. Initializes trailing stop state
        if trailing_stop_step > 0. Increments trades_today."""

    def on_tick(
        self, *, symbol: str, price: Decimal, now: datetime
    ) -> ExitEvent | None:
        """Process a tick for an open position.
        1. If trailing state exists, call TrailingStopPolicy.propose_update
        2. Check if current price crosses the stop (exit condition)
        3. If exit triggered, call close_position and return ExitEvent
        4. Otherwise return None"""
        ...

    def close_position(
        self,
        *,
        symbol: str,
        exit_price: Decimal,
        reason: str,
        now: datetime,
    ) -> ExitEvent:
        """Close position, compute net P&L via BrokerageCalculator,
        update available_capital and daily_realized_pnl."""
        ...

    def close_all_positions(
        self, *, prices: dict[str, Decimal], reason: str, now: datetime
    ) -> list[ExitEvent]:
        """Close all open positions (used by square-off)."""

    def snapshot(self) -> PositionSnapshot:
        """Return read-only view of current state."""

    def unrealized_pnl(
        self, *, prices: dict[str, Decimal]
    ) -> Decimal:
        """Sum of (current_price - entry_price) * qty * direction
        for all open positions. Returns 0 if no prices provided."""
```

### Exit Detection Logic

In `on_tick`:
```python
position = self._positions.get(symbol)
if position is None:
    return None

# Update trailing stop
if position.trailing is not None and self._trailing_policy:
    updated = self._trailing_policy.propose_update(
        position.trailing, price=price, now=now
    )
    if updated is not None:
        position = replace(position, trailing=updated)
        self._positions[symbol] = position
        # Audit: trailing_stop_updated

# Check exit condition
current_stop = (
    position.trailing.current_stop
    if position.trailing
    else position.stop_loss
)
if position.direction == Direction.LONG and price <= current_stop:
    return self.close_position(
        symbol=symbol, exit_price=current_stop,
        reason="trailing_stop_hit", now=now
    )
if position.direction == Direction.SHORT and price >= current_stop:
    return self.close_position(
        symbol=symbol, exit_price=current_stop,
        reason="trailing_stop_hit", now=now
    )
return None
```

### P&L Computation

In `close_position`:
```python
position = self._positions.pop(symbol)
gross_pnl = (
    (exit_price - position.entry_price) * position.quantity
    if position.direction == Direction.LONG
    else (position.entry_price - exit_price) * position.quantity
)
side = TradeSide.LONG if position.direction == Direction.LONG else TradeSide.SHORT
costs = self._brokerage.estimate_intraday_equity(
    side=side, entry_price=position.entry_price,
    exit_price=exit_price, quantity=position.quantity,
)
net_pnl = gross_pnl - costs.total_charges
self._available_capital += net_pnl
self._daily_realized_pnl += net_pnl
self._open_symbols.discard(symbol)
return ExitEvent(
    symbol=symbol, direction=position.direction,
    entry_price=position.entry_price, exit_price=exit_price,
    quantity=position.quantity, gross_pnl=gross_pnl,
    total_costs=costs.total_charges, net_pnl=net_pnl,
    reason=reason, timestamp=now,
)
```

---

## Component 2: Pipeline Integration

**Modified file:** `src/arthabot/runtime_pipeline.py`

### Constructor Changes

```python
class PaperRuntimePipeline:
    def __init__(
        self,
        *,
        trading_date: date,
        starting_capital: Decimal,
        execution: ExecutionEngine,
        risk: RiskEngine,
        hermes: HermesAdapter,
        audit: JsonlAuditStore,
        max_tick_age_seconds: int,
        position_tracker: PositionTracker,  # NEW
    ) -> None:
        self.feed = LiveFeedMonitor(max_tick_age_seconds=max_tick_age_seconds)
        self.session = PaperSession(
            trading_date=trading_date,
            starting_capital=starting_capital,
            execution=execution,
        )
        self.risk = risk
        self.hermes = hermes
        self.audit = audit
        self.tracker = position_tracker  # NEW
```

### on_tick Changes

```python
def on_tick(self, tick: Tick) -> None:
    self.feed.record_tick(tick)
    # NEW: update trailing stops, detect exits
    exit_event = self.tracker.on_tick(
        symbol=tick.symbol, price=tick.last_price, now=tick.timestamp
    )
    if exit_event is not None:
        self.session.record_exit(exit_event)
        self.audit.append(
            event_type="position_closed",
            payload={
                "symbol": exit_event.symbol,
                "direction": exit_event.direction.value,
                "entry_price": str(exit_event.entry_price),
                "exit_price": str(exit_event.exit_price),
                "quantity": exit_event.quantity,
                "net_pnl": str(exit_event.net_pnl),
                "total_costs": str(exit_event.total_costs),
                "reason": exit_event.reason,
            },
        )
```

### process_candidate Changes

```python
def process_candidate(self, candidate, *, now):
    # ... existing health check, hermes, risk logic ...
    snapshot = self.tracker.snapshot()
    decision = self.risk.evaluate(
        proposal=proposal, quote=tick, mode=Mode.PAPER,
        available_capital=snapshot.available_capital,
        daily_realized_pnl=snapshot.daily_realized_pnl,
        trades_today=snapshot.trades_today,
        open_symbols=snapshot.open_symbols, now=now,
    )
    # After risk approval, open position in tracker
    self.tracker.open_position(
        symbol=candidate.symbol, direction=candidate.direction,
        entry_price=proposal.entry_price, quantity=decision.quantity,
        stop_loss=proposal.stop_loss, trailing_stop_step=proposal.trailing_stop_step,
        now=now,
    )
    result = self.session.submit(PaperTradeIntent(...))
    return result
```

### Local Attributes Removed

The following move from pipeline local attributes to PositionTracker:
- `self.available_capital` → `self.tracker.snapshot().available_capital`
- `self.trades_today` → `self.tracker.snapshot().trades_today`
- `self.open_symbols` → `self.tracker.snapshot().open_symbols`
- `self.daily_realized_pnl` → `self.tracker.snapshot().daily_realized_pnl`

---

## Component 3: Backtest Stop Simulation

**Modified file:** `src/arthabot/backtest.py`

### BacktestSignal Changes

```python
@dataclass(frozen=True)
class BacktestSignal:
    symbol: str
    direction: Direction
    entry_date: date
    entry_price: Decimal
    exit_price: Decimal  # target price
    quantity: int
    stop_loss: Decimal = Decimal("0")
    trailing_stop_step: Decimal = Decimal("0")
    candles: tuple[Candle, ...] = ()
```

### BacktestExecutionEngine Changes

Constructor accepts `TrailingStopPolicy`:

```python
class BacktestExecutionEngine:
    def __init__(self, *, starting_capital: Decimal, brokerage: BrokerageCalculator,
                 trailing_policy: TrailingStopPolicy | None = None) -> None:
        self.starting_capital = starting_capital
        self.brokerage = brokerage
        self.trailing_policy = trailing_policy
```

Stop simulation method:

```python
def _simulate_stops(self, signal: BacktestSignal) -> tuple[Decimal, str]:
    if not signal.candles or signal.stop_loss <= 0:
        return signal.exit_price, "target"

    current_stop = signal.stop_loss
    trailing_state = None

    for candle in signal.candles:
        if signal.direction == Direction.LONG and candle.low <= current_stop:
            return current_stop, "stop_loss"
        if signal.direction == Direction.SHORT and candle.high >= current_stop:
            return current_stop, "stop_loss"

        if signal.trailing_stop_step > 0 and self.trailing_policy is not None:
            if trailing_state is None:
                trailing_state = TrailingStopState(
                    symbol=signal.symbol, direction=signal.direction,
                    current_stop=current_stop, last_reference_price=candle.close,
                    last_modified_at=candle.timestamp, modifications=0,
                )
            else:
                updated = self.trailing_policy.propose_update(
                    trailing_state, price=candle.close, now=candle.timestamp
                )
                if updated is not None:
                    trailing_state = updated
                    current_stop = updated.current_stop

    return signal.exit_price, "target"
```

---

## Component 4: PaperSession Updates

**Modified file:** `src/arthabot/paper_session.py`

Add `record_exit` method:

```python
def record_exit(self, exit_event: ExitEvent) -> None:
    """Record an exit driven by PositionTracker."""
    for trade in self._trades:
        if trade.symbol == exit_event.symbol and trade.exit_date is None:
            trade.exit_date = exit_event.timestamp.date()
            trade.exit_price = exit_event.exit_price
            trade.net_pnl = exit_event.net_pnl
            trade.total_costs = exit_event.total_costs
            break
```

---

## Component 5: Audit Events

| Event Type | When | Payload |
|------------|------|---------|
| `position_opened` | After risk approval + tracker.open_position | symbol, direction, entry_price, quantity, stop_loss, trailing_stop_step |
| `position_closed` | After tracker.close_position | symbol, direction, entry_price, exit_price, quantity, net_pnl, total_costs, reason |
| `trailing_stop_updated` | After TrailingStopPolicy.propose_update | symbol, old_stop, new_stop, modifications |
| `trailing_stop_exit` | When on_tick detects stop hit | symbol, stop_price, exit_price |

---

## Component 6: Config Changes

Add to `config/risk.yaml`:

```yaml
trailing_stop:
  enabled: true
  step: 0.5
  cooldown_seconds: 30
  max_modifications_per_trade: 5
```

Add to `config.py` RuntimeRiskConfig:

```python
trailing_stop_enabled: bool
trailing_stop_step: Decimal
trailing_stop_cooldown_seconds: int
trailing_stop_max_modifications: int
```

---

## Testing Plan

### New Tests

**`tests/unit/test_position_tracker.py`** (12 tests):
1. open_position records state
2. close_position updates capital
3. close_position deducts brokerage
4. on_tick trailing stop update
5. on_tick exit long position
6. on_tick exit short position
7. on_tick no-op for unknown symbol
8. unrealized_pnl long
9. unrealized_pnl short
10. close_all_positions
11. snapshot correctness
12. daily loss limit with compounding

**`tests/unit/test_backtest_stops.py`** (5 tests):
1. fixed stop hit
2. trailing stop updates
3. trailing stop exit
4. no stop (target reached)
5. short position stop

### Modified Tests

- `test_risk_engine.py` — use PositionTracker for capital
- `test_pipeline_modules.py` — inject PositionTracker
- `test_backtest_accounting.py` — add stop simulation cases

---

## Files Changed

| File | Change |
|------|--------|
| `src/arthabot/position_tracker.py` | **NEW** |
| `src/arthabot/runtime_pipeline.py` | Wire tracker, remove local state |
| `src/arthabot/backtest.py` | Add stop simulation |
| `src/arthabot/paper_session.py` | Add record_exit |
| `src/arthabot/config.py` | Add trailing stop config |
| `config/risk.yaml` | Add trailing_stop section |
| `scripts/run_paper_loop.py` | Create and inject tracker |
| `tests/unit/test_position_tracker.py` | **NEW** |
| `tests/unit/test_backtest_stops.py` | **NEW** |

---

## Implementation Order

1. `position_tracker.py` + tests
2. `config.py` + `risk.yaml` — trailing stop config
3. `runtime_pipeline.py` — wire tracker
4. `paper_session.py` — add record_exit
5. `backtest.py` — stop simulation
6. `run_paper_loop.py` — inject tracker
7. Update existing tests
8. Run full test suite