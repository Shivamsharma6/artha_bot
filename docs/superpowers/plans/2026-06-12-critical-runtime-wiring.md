# Critical Runtime Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire PositionTracker into the paper trading pipeline to fix P&L tracking, trailing stops, backtest stop simulation, and unrealized P&L computation.

**Architecture:** Extract position management into a new `PositionTracker` class. The pipeline delegates to it for position state, trailing stop updates, exit detection, and capital tracking. Backtest engine gains candle-by-candle stop simulation using the same `TrailingStopPolicy`.

**Tech Stack:** Python 3.11+, Pydantic (existing), Decimal arithmetic, pytest

---

## File Structure

| File | Role |
|------|------|
| `src/arthabot/position_tracker.py` | **NEW** — PositionTracker, TrackedPosition, PositionSnapshot, ExitEvent |
| `src/arthabot/runtime_pipeline.py` | Wire PositionTracker, remove local capital/trades/symbols |
| `src/arthabot/backtest.py` | Add stop simulation to BacktestExecutionEngine, add fields to BacktestSignal |
| `src/arthabot/paper_session.py` | Add record_exit method |
| `src/arthabot/config.py` | Add trailing stop config fields to RuntimeRiskConfig |
| `config/risk.yaml` | Add trailing_stop section |
| `scripts/run_paper_loop.py` | Create PositionTracker, inject into pipeline |
| `tests/unit/test_position_tracker.py` | **NEW** — 12 unit tests |
| `tests/unit/test_backtest_stops.py` | **NEW** — 5 unit tests |

---

### Task 1: PositionTracker Data Types + Constructor

**Files:**
- Create: `src/arthabot/position_tracker.py`
- Create: `tests/unit/test_position_tracker.py`

- [ ] **Step 1: Write the failing test for PositionTracker construction**

```python
# tests/unit/test_position_tracker.py
from decimal import Decimal
from arthabot.position_tracker import PositionTracker, PositionSnapshot
from arthabot.brokerage import BrokerageCalculator, BrokerageConfig


def test_position_tracker_initializes_with_starting_capital():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    snapshot = tracker.snapshot()
    assert snapshot.available_capital == Decimal("5000")
    assert snapshot.daily_realized_pnl == Decimal("0")
    assert snapshot.trades_today == 0
    assert snapshot.open_symbols == set()
    assert snapshot.open_positions == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_position_tracker_initializes_with_starting_capital -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arthabot.position_tracker'`

- [ ] **Step 3: Write PositionTracker data types and constructor**

```python
# src/arthabot/position_tracker.py
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from arthabot.brokerage import BrokerageCalculator, TradeSide
from arthabot.common import Direction
from arthabot.trailing_stop import TrailingStopPolicy, TrailingStopState


@dataclass(frozen=True)
class TrackedPosition:
    symbol: str
    direction: Direction
    entry_price: Decimal
    quantity: int
    stop_loss: Decimal
    trailing_stop_step: Decimal
    trailing: TrailingStopState | None
    entry_timestamp: datetime


@dataclass(frozen=True)
class PositionSnapshot:
    open_positions: list[TrackedPosition]
    available_capital: Decimal
    daily_realized_pnl: Decimal
    unrealized_pnl: Decimal
    trades_today: int
    open_symbols: set[str]


@dataclass(frozen=True)
class ExitEvent:
    symbol: str
    direction: Direction
    entry_price: Decimal
    exit_price: Decimal
    quantity: int
    gross_pnl: Decimal
    total_costs: Decimal
    net_pnl: Decimal
    reason: str
    timestamp: datetime


class PositionTracker:
    def __init__(
        self,
        *,
        starting_capital: Decimal,
        brokerage: BrokerageCalculator,
        trailing_policy: TrailingStopPolicy | None = None,
    ) -> None:
        self._available_capital = starting_capital
        self._daily_realized_pnl = Decimal("0")
        self._positions: dict[str, TrackedPosition] = {}
        self._trades_today = 0
        self._brokerage = brokerage
        self._trailing_policy = trailing_policy

    def snapshot(self) -> PositionSnapshot:
        return PositionSnapshot(
            open_positions=list(self._positions.values()),
            available_capital=self._available_capital,
            daily_realized_pnl=self._daily_realized_pnl,
            unrealized_pnl=Decimal("0"),
            trades_today=self._trades_today,
            open_symbols=set(self._positions.keys()),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_position_tracker_initializes_with_starting_capital -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arthabot/position_tracker.py tests/unit/test_position_tracker.py
git commit -m "feat: add PositionTracker data types and constructor"
```

---

### Task 2: PositionTracker.open_position

**Files:**
- Modify: `src/arthabot/position_tracker.py`
- Modify: `tests/unit/test_position_tracker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_position_tracker.py (append)
from datetime import datetime, timezone


def test_open_position_records_state():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY",
        direction=Direction.LONG,
        entry_price=Decimal("100"),
        quantity=10,
        stop_loss=Decimal("98"),
        trailing_stop_step=Decimal("1"),
        now=now,
    )
    snapshot = tracker.snapshot()
    assert len(snapshot.open_positions) == 1
    assert snapshot.trades_today == 1
    assert "INFY" in snapshot.open_symbols
    pos = snapshot.open_positions[0]
    assert pos.symbol == "INFY"
    assert pos.direction == Direction.LONG
    assert pos.entry_price == Decimal("100")
    assert pos.quantity == 10
    assert pos.stop_loss == Decimal("98")
    assert pos.trailing is not None
    assert pos.trailing.current_stop == Decimal("98")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_open_position_records_state -v`
Expected: FAIL with `AttributeError: 'PositionTracker' object has no attribute 'open_position'`

- [ ] **Step 3: Implement open_position**

```python
# src/arthabot/position_tracker.py (append to PositionTracker class)

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
        trailing = None
        if trailing_stop_step > 0:
            trailing = TrailingStopState(
                symbol=symbol,
                direction=direction,
                current_stop=stop_loss,
                last_reference_price=entry_price,
                last_modified_at=now,
                modifications=0,
            )
        self._positions[symbol] = TrackedPosition(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            trailing_stop_step=trailing_stop_step,
            trailing=trailing,
            entry_timestamp=now,
        )
        self._trades_today += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_open_position_records_state -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arthabot/position_tracker.py tests/unit/test_position_tracker.py
git commit -m "feat: add PositionTracker.open_position"
```

---

### Task 3: PositionTracker.close_position

**Files:**
- Modify: `src/arthabot/position_tracker.py`
- Modify: `tests/unit/test_position_tracker.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_position_tracker.py (append)


def test_close_position_updates_capital():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("0"), now=now,
    )
    exit_event = tracker.close_position(
        symbol="INFY", exit_price=Decimal("105"),
        reason="target", now=now,
    )
    assert exit_event.gross_pnl == Decimal("50")
    assert exit_event.total_costs > Decimal("0")
    assert exit_event.net_pnl < Decimal("50")
    snapshot = tracker.snapshot()
    assert snapshot.available_capital > Decimal("5000")
    assert snapshot.daily_realized_pnl > Decimal("0")
    assert snapshot.open_positions == []
    assert snapshot.open_symbols == set()


def test_close_short_position():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="TCS", direction=Direction.SHORT,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("102"), trailing_stop_step=Decimal("0"), now=now,
    )
    exit_event = tracker.close_position(
        symbol="TCS", exit_price=Decimal("95"),
        reason="target", now=now,
    )
    assert exit_event.gross_pnl == Decimal("50")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_close_position_updates_capital tests/unit/test_position_tracker.py::test_close_short_position -v`
Expected: FAIL with `AttributeError: 'PositionTracker' object has no attribute 'close_position'`

- [ ] **Step 3: Implement close_position**

```python
# src/arthabot/position_tracker.py (append to PositionTracker class)

    def close_position(
        self,
        *,
        symbol: str,
        exit_price: Decimal,
        reason: str,
        now: datetime,
    ) -> ExitEvent:
        position = self._positions.pop(symbol)
        if position.direction == Direction.LONG:
            gross_pnl = (exit_price - position.entry_price) * position.quantity
        else:
            gross_pnl = (position.entry_price - exit_price) * position.quantity
        side = TradeSide.LONG if position.direction == Direction.LONG else TradeSide.SHORT
        costs = self._brokerage.estimate_intraday_equity(
            side=side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
        )
        net_pnl = gross_pnl - costs.total_charges
        self._available_capital += net_pnl
        self._daily_realized_pnl += net_pnl
        return ExitEvent(
            symbol=symbol,
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            gross_pnl=gross_pnl,
            total_costs=costs.total_charges,
            net_pnl=net_pnl,
            reason=reason,
            timestamp=now,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_close_position_updates_capital tests/unit/test_position_tracker.py::test_close_short_position -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arthabot/position_tracker.py tests/unit/test_position_tracker.py
git commit -m "feat: add PositionTracker.close_position with brokerage-aware P&L"
```

---

### Task 4: PositionTracker.on_tick (trailing stop + exit detection)

**Files:**
- Modify: `src/arthabot/position_tracker.py`
- Modify: `tests/unit/test_position_tracker.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_position_tracker.py (append)


def test_on_tick_exit_long_position():
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
    # Price drops to stop level
    exit_event = tracker.on_tick(symbol="INFY", price=Decimal("98"), now=now)
    assert exit_event is not None
    assert exit_event.reason == "trailing_stop_hit"
    assert exit_event.exit_price == Decimal("98")
    assert tracker.snapshot().open_positions == []


def test_on_tick_exit_short_position():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
        trailing_policy=TrailingStopPolicy(
            step=Decimal("1"), cooldown_seconds=0, max_modifications_per_trade=5,
        ),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="TCS", direction=Direction.SHORT,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("102"), trailing_stop_step=Decimal("1"), now=now,
    )
    # Price rises to stop level
    exit_event = tracker.on_tick(symbol="TCS", price=Decimal("102"), now=now)
    assert exit_event is not None
    assert exit_event.reason == "trailing_stop_hit"
    assert tracker.snapshot().open_positions == []


def test_on_tick_noop_for_unknown_symbol():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    result = tracker.on_tick(symbol="UNKNOWN", price=Decimal("100"), now=now)
    assert result is None


def test_on_tick_trailing_stop_update():
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
    # Price moves favorably — trailing stop should advance
    result = tracker.on_tick(symbol="INFY", price=Decimal("103"), now=now)
    assert result is None  # no exit
    pos = tracker.snapshot().open_positions[0]
    assert pos.trailing.current_stop > Decimal("98")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_position_tracker.py -k "on_tick" -v`
Expected: FAIL with `AttributeError: 'PositionTracker' object has no attribute 'on_tick'`

- [ ] **Step 3: Implement on_tick**

```python
# src/arthabot/position_tracker.py (append to PositionTracker class)

    def on_tick(
        self, *, symbol: str, price: Decimal, now: datetime
    ) -> ExitEvent | None:
        position = self._positions.get(symbol)
        if position is None:
            return None

        # Update trailing stop
        if position.trailing is not None and self._trailing_policy is not None:
            updated = self._trailing_policy.propose_update(
                position.trailing, price=price, now=now
            )
            if updated is not None:
                position = replace(position, trailing=updated)
                self._positions[symbol] = position

        # Check exit condition
        current_stop = (
            position.trailing.current_stop
            if position.trailing
            else position.stop_loss
        )
        if position.direction == Direction.LONG and price <= current_stop:
            return self.close_position(
                symbol=symbol, exit_price=current_stop,
                reason="trailing_stop_hit", now=now,
            )
        if position.direction == Direction.SHORT and price >= current_stop:
            return self.close_position(
                symbol=symbol, exit_price=current_stop,
                reason="trailing_stop_hit", now=now,
            )
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_position_tracker.py -k "on_tick" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arthabot/position_tracker.py tests/unit/test_position_tracker.py
git commit -m "feat: add PositionTracker.on_tick with trailing stop and exit detection"
```

---

### Task 5: PositionTracker.close_all_positions + unrealized_pnl

**Files:**
- Modify: `src/arthabot/position_tracker.py`
- Modify: `tests/unit/test_position_tracker.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_position_tracker.py (append)


def test_close_all_positions():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("0"), now=now,
    )
    tracker.open_position(
        symbol="TCS", direction=Direction.SHORT,
        entry_price=Decimal("200"), quantity=5,
        stop_loss=Decimal("202"), trailing_stop_step=Decimal("0"), now=now,
    )
    events = tracker.close_all_positions(
        prices={"INFY": Decimal("105"), "TCS": Decimal("195")},
        reason="square_off", now=now,
    )
    assert len(events) == 2
    assert tracker.snapshot().open_positions == []
    assert tracker.snapshot().open_symbols == set()


def test_unrealized_pnl_long():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("0"), now=now,
    )
    pnl = tracker.unrealized_pnl(prices={"INFY": Decimal("105")})
    assert pnl == Decimal("50")


def test_unrealized_pnl_short():
    tracker = PositionTracker(
        starting_capital=Decimal("5000"),
        brokerage=BrokerageCalculator(BrokerageConfig()),
    )
    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    tracker.open_position(
        symbol="TCS", direction=Direction.SHORT,
        entry_price=Decimal("200"), quantity=5,
        stop_loss=Decimal("202"), trailing_stop_step=Decimal("0"), now=now,
    )
    pnl = tracker.unrealized_pnl(prices={"TCS": Decimal("195")})
    assert pnl == Decimal("25")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_position_tracker.py -k "close_all or unrealized" -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement close_all_positions and unrealized_pnl**

```python
# src/arthabot/position_tracker.py (append to PositionTracker class)

    def close_all_positions(
        self, *, prices: dict[str, Decimal], reason: str, now: datetime
    ) -> list[ExitEvent]:
        events: list[ExitEvent] = []
        for symbol in list(self._positions.keys()):
            price = prices.get(symbol, self._positions[symbol].entry_price)
            events.append(self.close_position(
                symbol=symbol, exit_price=price, reason=reason, now=now,
            ))
        return events

    def unrealized_pnl(self, *, prices: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for position in self._positions.values():
            current_price = prices.get(position.symbol)
            if current_price is None:
                continue
            if position.direction == Direction.LONG:
                total += (current_price - position.entry_price) * position.quantity
            else:
                total += (position.entry_price - current_price) * position.quantity
        return total
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_position_tracker.py -k "close_all or unrealized" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arthabot/position_tracker.py tests/unit/test_position_tracker.py
git commit -m "feat: add PositionTracker.close_all_positions and unrealized_pnl"
```

---

### Task 6: Config — Trailing Stop Settings

**Files:**
- Modify: `config/risk.yaml`
- Modify: `src/arthabot/config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_position_tracker.py (append)


def test_config_loads_trailing_stop_settings():
    from arthabot.config import load_runtime_config
    from pathlib import Path
    config = load_runtime_config(Path("config"))
    assert config.risk.trailing_stop_enabled is True
    assert config.risk.trailing_stop_step == Decimal("0.5")
    assert config.risk.trailing_stop_cooldown_seconds == 30
    assert config.risk.trailing_stop_max_modifications == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_config_loads_trailing_stop_settings -v`
Expected: FAIL with `AttributeError: 'RuntimeRiskConfig' object has no attribute 'trailing_stop_enabled'`

- [ ] **Step 3: Add trailing_stop section to risk.yaml**

```yaml
# config/risk.yaml
starting_capital: "5000"
max_risk_per_trade_pct: "0.01"
max_daily_loss_pct: "0.03"
min_allocation_pct: "0.05"
max_trades_per_day: 3
quote_max_age_seconds: 15
square_off_time: "15:15"
leverage_allowed: false
trailing_stop_enabled: true
trailing_stop_step: "0.5"
trailing_stop_cooldown_seconds: 30
trailing_stop_max_modifications: 5
```

- [ ] **Step 4: Add fields to RuntimeRiskConfig and load_runtime_config**

```python
# src/arthabot/config.py — add to RuntimeRiskConfig dataclass
@dataclass(frozen=True)
class RuntimeRiskConfig:
    starting_capital: Decimal
    max_risk_per_trade_pct: Decimal
    max_daily_loss_pct: Decimal
    min_allocation_pct: Decimal
    max_trades_per_day: int
    quote_max_age_seconds: int
    square_off_time: str
    leverage_allowed: bool
    trailing_stop_enabled: bool
    trailing_stop_step: Decimal
    trailing_stop_cooldown_seconds: int
    trailing_stop_max_modifications: int
```

```python
# src/arthabot/config.py — add to load_runtime_config
        runtime = RuntimeConfig(
            risk=RuntimeRiskConfig(
                # ... existing fields ...
                trailing_stop_enabled=bool(risk.get("trailing_stop_enabled", False)),
                trailing_stop_step=Decimal(str(risk.get("trailing_stop_step", "0"))),
                trailing_stop_cooldown_seconds=int(risk.get("trailing_stop_cooldown_seconds", 30)),
                trailing_stop_max_modifications=int(risk.get("trailing_stop_max_modifications", 5)),
            ),
            # ...
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_config_loads_trailing_stop_settings -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add config/risk.yaml src/arthabot/config.py tests/unit/test_position_tracker.py
git commit -m "feat: add trailing stop config to risk.yaml and RuntimeRiskConfig"
```

---

### Task 7: PaperSession.record_exit

**Files:**
- Modify: `src/arthabot/paper_session.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_position_tracker.py (append)


def test_paper_session_record_exit():
    from arthabot.paper_session import PaperSession, PaperTradeIntent
    from arthabot.execution import ExecutionEngine
    from arthabot.position_tracker import ExitEvent

    session = PaperSession(
        trading_date=datetime(2026, 6, 12).date(),
        starting_capital=Decimal("5000"),
        execution=ExecutionEngine(),
    )
    session.submit(PaperTradeIntent(
        symbol="INFY", direction=Direction.LONG,
        quantity=10, entry_price=Decimal("100"),
        exit_price=Decimal("105"), total_costs=Decimal("5"),
    ))
    exit_event = ExitEvent(
        symbol="INFY", direction=Direction.LONG,
        entry_price=Decimal("100"), exit_price=Decimal("105"),
        quantity=10, gross_pnl=Decimal("50"),
        total_costs=Decimal("5"), net_pnl=Decimal("45"),
        reason="trailing_stop_hit",
        timestamp=datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc),
    )
    session.record_exit(exit_event)
    report = session.daily_report().summarize()
    assert report["net_pnl"] == Decimal("45")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_paper_session_record_exit -v`
Expected: FAIL with `AttributeError: 'PaperSession' object has no attribute 'record_exit'`

- [ ] **Step 3: Add record_exit to PaperSession**

```python
# src/arthabot/paper_session.py — add import and method

from arthabot.position_tracker import ExitEvent

# Inside PaperSession class:
    def record_exit(self, exit_event: ExitEvent) -> None:
        for trade in self._trades:
            if trade.symbol == exit_event.symbol and trade.accepted:
                self._trades.remove(trade)
                self._trades.append(TradeRecord(
                    symbol=exit_event.symbol,
                    gross_pnl=exit_event.gross_pnl,
                    total_costs=exit_event.total_costs,
                    accepted=True,
                ))
                break
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_paper_session_record_exit -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arthabot/paper_session.py tests/unit/test_position_tracker.py
git commit -m "feat: add PaperSession.record_exit for PositionTracker-driven exits"
```

---

### Task 8: Wire PositionTracker into PaperRuntimePipeline

**Files:**
- Modify: `src/arthabot/runtime_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_position_tracker.py (append)


def test_pipeline_uses_position_tracker_for_capital():
    from arthabot.runtime_pipeline import PaperRuntimePipeline, HermesAdapter
    from arthabot.risk import RiskEngine, RiskConfig
    from arthabot.audit_store import JsonlAuditStore
    from arthabot.common import MarketQuote
    from arthabot.strategies import TradeCandidate
    import tempfile, os

    audit_path = os.path.join(tempfile.mkdtemp(), "test.audit.jsonl")
    broker_cfg = BrokerageConfig()
    broker_calc = BrokerageCalculator(broker_cfg)
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
    # Pipeline should read capital from tracker
    assert pipeline.tracker.snapshot().available_capital == Decimal("5000")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_pipeline_uses_position_tracker_for_capital -v`
Expected: FAIL with `TypeError: __init__() missing 1 required keyword-only argument: 'position_tracker'`

- [ ] **Step 3: Modify PaperRuntimePipeline**

```python
# src/arthabot/runtime_pipeline.py — modify imports and constructor

from arthabot.position_tracker import PositionTracker  # NEW

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

- [ ] **Step 4: Update on_tick to use tracker**

```python
# src/arthabot/runtime_pipeline.py — replace on_tick method

    def on_tick(self, tick: Tick) -> None:
        self.feed.record_tick(tick)
        exit_event = self.tracker.on_tick(
            symbol=tick.symbol, price=tick.last_price, now=tick.timestamp,
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

- [ ] **Step 5: Update process_candidate to use tracker**

```python
# src/arthabot/runtime_pipeline.py — replace process_candidate method

    def process_candidate(self, candidate: TradeCandidate, *, now: datetime) -> OrderResult | None:
        health = self.feed.health(candidate.symbol, now=now)
        if not health.ok:
            self.session.reject(symbol=candidate.symbol, reason=health.reason_code)
            self.audit.append(
                event_type="risk_rejection",
                payload={"symbol": candidate.symbol, "reason_code": health.reason_code},
            )
            return None
        proposal = self.hermes.evaluate(candidate, now=now)
        self.audit.append(
            event_type="decision",
            payload={
                "symbol": candidate.symbol,
                "direction": candidate.direction.value,
                "strategy_version": proposal.strategy_version,
            },
        )
        tick = self.feed.latest_tick(candidate.symbol)
        snapshot = self.tracker.snapshot()
        decision = self.risk.evaluate(
            proposal=proposal,
            quote=tick,
            mode=Mode.PAPER,
            available_capital=snapshot.available_capital,
            daily_realized_pnl=snapshot.daily_realized_pnl,
            trades_today=snapshot.trades_today,
            open_symbols=snapshot.open_symbols,
            now=now,
        )
        if not decision.approved:
            self.session.reject(symbol=candidate.symbol, reason=decision.reason_code)
            self.audit.append(
                event_type="risk_rejection",
                payload={"symbol": candidate.symbol, "reason_code": decision.reason_code},
            )
            return None
        self.tracker.open_position(
            symbol=candidate.symbol,
            direction=candidate.direction,
            entry_price=proposal.entry_price,
            quantity=decision.quantity,
            stop_loss=proposal.stop_loss,
            trailing_stop_step=proposal.trailing_stop_step,
            now=now,
        )
        self.audit.append(
            event_type="risk_approved",
            payload={"symbol": candidate.symbol, "quantity": decision.quantity},
        )
        result = self.session.submit(
            PaperTradeIntent(
                symbol=candidate.symbol,
                direction=candidate.direction,
                quantity=decision.quantity,
                entry_price=proposal.entry_price,
                exit_price=proposal.target_price,
                total_costs=decision.estimated_total_costs,
            )
        )
        self.audit.append(
            event_type="paper_signal_executed",
            payload={"symbol": candidate.symbol, "order_id": result.order_id, "simulated": result.simulated},
        )
        return result
```

- [ ] **Step 6: Update daily_report**

```python
# src/arthabot/runtime_pipeline.py — replace daily_report method

    def daily_report(self):
        session_report = self.session.daily_report()
        snapshot = self.tracker.snapshot()
        report = session_report.summarize()
        report["available_capital"] = snapshot.available_capital
        report["daily_realized_pnl"] = snapshot.daily_realized_pnl
        report["unrealized_pnl"] = self.tracker.unrealized_pnl(
            prices={pos.symbol: pos.entry_price for pos in snapshot.open_positions}
        )
        report["open_positions"] = len(snapshot.open_positions)
        return report
```

- [ ] **Step 7: Remove old local attributes**

Remove these lines from `__init__`:
```python
        self.available_capital = starting_capital
        self.trades_today = 0
        self.open_symbols: set[str] = set()
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_position_tracker.py::test_pipeline_uses_position_tracker_for_capital -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/arthabot/runtime_pipeline.py tests/unit/test_position_tracker.py
git commit -m "feat: wire PositionTracker into PaperRuntimePipeline"
```

---

### Task 9: Backtest Stop Simulation

**Files:**
- Modify: `src/arthabot/backtest.py`
- Create: `tests/unit/test_backtest_stops.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_backtest_stops.py
from datetime import datetime, date, timezone
from decimal import Decimal

from arthabot.backtest import BacktestExecutionEngine, BacktestSignal, Candle
from arthabot.brokerage import BrokerageCalculator, BrokerageConfig
from arthabot.common import Direction
from arthabot.trailing_stop import TrailingStopPolicy


def test_fixed_stop_hit():
    broker = BrokerageCalculator(BrokerageConfig())
    engine = BacktestExecutionEngine(
        starting_capital=Decimal("5000"), brokerage=broker,
    )
    candles = (
        Candle(timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
               open=Decimal("100"), high=Decimal("101"), low=Decimal("97"), close=Decimal("98")),
        Candle(timestamp=datetime(2026, 1, 5, 10, 1, tzinfo=timezone.utc),
               open=Decimal("98"), high=Decimal("99"), low=Decimal("96"), close=Decimal("97")),
    )
    signal = BacktestSignal(
        symbol="INFY", direction=Direction.LONG,
        entry_date=date(2026, 1, 5), entry_price=Decimal("100"),
        exit_price=Decimal("105"), quantity=10,
        stop_loss=Decimal("98"), candles=candles,
    )
    report = engine.run([signal])
    assert report.number_of_trades == 1
    assert report.max_drawdown > Decimal("0")


def test_no_stop_target_reached():
    broker = BrokerageCalculator(BrokerageConfig())
    engine = BacktestExecutionEngine(
        starting_capital=Decimal("5000"), brokerage=broker,
    )
    candles = (
        Candle(timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
               open=Decimal("100"), high=Decimal("106"), low=Decimal("99"), close=Decimal("105")),
    )
    signal = BacktestSignal(
        symbol="INFY", direction=Direction.LONG,
        entry_date=date(2026, 1, 5), entry_price=Decimal("100"),
        exit_price=Decimal("105"), quantity=10,
        stop_loss=Decimal("98"), candles=candles,
    )
    report = engine.run([signal])
    assert report.number_of_trades == 1
    assert report.net_profit > Decimal("0")


def test_short_position_stop_hit():
    broker = BrokerageCalculator(BrokerageConfig())
    engine = BacktestExecutionEngine(
        starting_capital=Decimal("5000"), brokerage=broker,
    )
    candles = (
        Candle(timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
               open=Decimal("100"), high=Decimal("103"), low=Decimal("99"), close=Decimal("102")),
    )
    signal = BacktestSignal(
        symbol="TCS", direction=Direction.SHORT,
        entry_date=date(2026, 1, 5), entry_price=Decimal("100"),
        exit_price=Decimal("95"), quantity=10,
        stop_loss=Decimal("102"), candles=candles,
    )
    report = engine.run([signal])
    assert report.number_of_trades == 1


def test_trailing_stop_exits_at_trail():
    broker = BrokerageCalculator(BrokerageConfig())
    policy = TrailingStopPolicy(
        step=Decimal("1"), cooldown_seconds=0, max_modifications_per_trade=5,
    )
    engine = BacktestExecutionEngine(
        starting_capital=Decimal("5000"), brokerage=broker,
        trailing_policy=policy,
    )
    candles = (
        Candle(timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
               open=Decimal("100"), high=Decimal("102"), low=Decimal("99"), close=Decimal("101")),
        Candle(timestamp=datetime(2026, 1, 5, 10, 1, tzinfo=timezone.utc),
               open=Decimal("101"), high=Decimal("104"), low=Decimal("100"), close=Decimal("103")),
        Candle(timestamp=datetime(2026, 1, 5, 10, 2, tzinfo=timezone.utc),
               open=Decimal("103"), high=Decimal("103"), low=Decimal("99"), close=Decimal("100")),
    )
    signal = BacktestSignal(
        symbol="INFY", direction=Direction.LONG,
        entry_date=date(2026, 1, 5), entry_price=Decimal("100"),
        exit_price=Decimal("110"), quantity=10,
        stop_loss=Decimal("98"), trailing_stop_step=Decimal("1"),
        candles=candles,
    )
    report = engine.run([signal])
    assert report.number_of_trades == 1
    # Should exit at trailing stop, not at target
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_backtest_stops.py -v`
Expected: FAIL — BacktestSignal doesn't have stop_loss/candles fields

- [ ] **Step 3: Add fields to BacktestSignal**

```python
# src/arthabot/backtest.py — modify BacktestSignal dataclass

@dataclass(frozen=True)
class BacktestSignal:
    symbol: str
    direction: Direction
    entry_date: date
    entry_price: Decimal
    exit_price: Decimal
    quantity: int
    stop_loss: Decimal = Decimal("0")
    trailing_stop_step: Decimal = Decimal("0")
    candles: tuple[Candle, ...] = ()
```

- [ ] **Step 4: Add trailing_policy to BacktestExecutionEngine**

```python
# src/arthabot/backtest.py — add import and modify constructor

from arthabot.trailing_stop import TrailingStopPolicy, TrailingStopState  # add import

class BacktestExecutionEngine:
    def __init__(
        self,
        *,
        starting_capital: Decimal,
        brokerage: BrokerageCalculator,
        trailing_policy: TrailingStopPolicy | None = None,
    ) -> None:
        self.starting_capital = starting_capital
        self.brokerage = brokerage
        self.trailing_policy = trailing_policy
```

- [ ] **Step 5: Add _simulate_stops method**

```python
# src/arthabot/backtest.py — add to BacktestExecutionEngine

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
                        symbol=signal.symbol,
                        direction=signal.direction,
                        current_stop=current_stop,
                        last_reference_price=candle.close,
                        last_modified_at=candle.timestamp,
                        modifications=0,
                    )
                else:
                    updated = self.trailing_policy.propose_update(
                        trailing_state, price=candle.close, now=candle.timestamp,
                    )
                    if updated is not None:
                        trailing_state = updated
                        current_stop = updated.current_stop

        return signal.exit_price, "target"
```

- [ ] **Step 6: Update run method to use _simulate_stops**

```python
# src/arthabot/backtest.py — replace run method

    def run(self, signals: list[BacktestSignal]) -> BacktestReport:
        trades: list[BacktestTrade] = []
        missed = 0
        for signal in signals:
            if signal.quantity <= 0:
                trades.append(
                    BacktestTrade(
                        symbol=signal.symbol, direction=signal.direction,
                        entry_date=signal.entry_date, exit_date=signal.entry_date,
                        gross_pnl=Decimal("0"), total_costs=Decimal("0"),
                        rejected=True, entry_time_label="unknown",
                    )
                )
                continue
            if signal.entry_price <= 0 or signal.exit_price <= 0:
                missed += 1
                continue

            exit_price, exit_label = self._simulate_stops(signal)
            side = TradeSide.LONG if signal.direction == Direction.LONG else TradeSide.SHORT
            costs = self.brokerage.estimate_intraday_equity(
                side=side, entry_price=signal.entry_price,
                exit_price=exit_price, quantity=signal.quantity,
            )
            trades.append(
                BacktestTrade(
                    symbol=signal.symbol, direction=signal.direction,
                    entry_date=signal.entry_date, exit_date=signal.entry_date,
                    gross_pnl=costs.gross_pnl, total_costs=costs.total_charges,
                    rejected=False, entry_time_label=exit_label,
                )
            )
        report = BacktestAccounting(starting_capital=self.starting_capital).summarize(trades)
        return replace(report, number_of_missed_trades=missed)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_backtest_stops.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/arthabot/backtest.py tests/unit/test_backtest_stops.py
git commit -m "feat: add stop simulation to BacktestExecutionEngine"
```

---

### Task 10: Wire PositionTracker in run_paper_loop.py

**Files:**
- Modify: `scripts/run_paper_loop.py`

- [ ] **Step 1: Read current run_paper_loop.py to find injection point**

Read: `scripts/run_paper_loop.py` — find where `PaperRuntimePipeline` is constructed

- [ ] **Step 2: Add PositionTracker creation before pipeline construction**

```python
# scripts/run_paper_loop.py — add imports and tracker creation

from arthabot.position_tracker import PositionTracker
from arthabot.trailing_stop import TrailingStopPolicy

# Before PaperRuntimePipeline construction:
trailing_policy = None
if config.risk.trailing_stop_enabled:
    trailing_policy = TrailingStopPolicy(
        step=config.risk.trailing_stop_step,
        cooldown_seconds=config.risk.trailing_stop_cooldown_seconds,
        max_modifications_per_trade=config.risk.trailing_stop_max_modifications,
    )
position_tracker = PositionTracker(
    starting_capital=config.risk.starting_capital,
    brokerage=brokerage_calculator,
    trailing_policy=trailing_policy,
)
```

- [ ] **Step 3: Pass tracker to pipeline constructor**

```python
# scripts/run_paper_loop.py — add position_tracker to PaperRuntimePipeline call

pipeline = PaperRuntimePipeline(
    # ... existing arguments ...
    position_tracker=position_tracker,  # ADD THIS
)
```

- [ ] **Step 4: Run the paper loop briefly to verify no import errors**

Run: `uv run python -c "from scripts.run_paper_loop import main"` (or similar import check)
Expected: No ImportError

- [ ] **Step 5: Commit**

```bash
git add scripts/run_paper_loop.py
git commit -m "feat: inject PositionTracker into paper loop"
```

---

### Task 11: Update Existing Tests

**Files:**
- Modify: `tests/unit/test_pipeline_modules.py`

- [ ] **Step 1: Update test_pipeline_modules.py to pass PositionTracker**

The existing tests in `test_pipeline_modules.py` don't construct `PaperRuntimePipeline` directly, so they should still pass. Run the full suite to verify:

Run: `uv run pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 2: If any test constructs PaperRuntimePipeline, add position_tracker parameter**

Search for `PaperRuntimePipeline` in test files:
```bash
grep -r "PaperRuntimePipeline" tests/
```

If found, add the required `position_tracker` argument.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: update existing tests for PositionTracker integration"
```

---

### Task 12: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 3: Run type checker if available**

Run: `uv run pyright src/arthabot/position_tracker.py` (or equivalent)
Expected: No type errors

- [ ] **Step 4: Verify no secrets in code**

Run: `grep -r "api_key\|secret\|token" src/arthabot/position_tracker.py`
Expected: No matches

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: critical runtime wiring — PositionTracker, trailing stops, backtest stops, P&L tracking"
```
