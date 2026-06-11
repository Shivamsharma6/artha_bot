# Backtest Report Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce constitution-complete, cost-aware backtest metrics and auditable strategy/data metadata.

**Architecture:** Extend existing immutable backtest trade/report models and centralize derived calculations in `BacktestAccounting`. Preserve current constructor compatibility through defaults, while providing an explicit fail-closed promotion metadata validator.

**Tech Stack:** Python dataclasses, `Decimal`, datetime/date, pytest.

---

### Task 1: Derived profitability and daily risk metrics

**Files:**
- Modify: `src/arthabot/backtest.py`
- Modify: `tests/unit/test_backtest_accounting.py`

- [x] Add failing tests for average win/loss, profit factor, expectancy, best and
  worst day, Sharpe-like metric, zero-trade behavior, and all-win behavior.
- [x] Run the focused tests and verify missing report attributes fail.
- [x] Implement deterministic accepted-trade and daily aggregation metrics.
- [x] Run focused tests and require all passing.

### Task 2: Time windows and report metadata

**Files:**
- Modify: `src/arthabot/backtest.py`
- Modify: `tests/unit/test_backtest_accounting.py`

- [x] Add failing tests for open/close/other window P&L, metadata validation, and
  fail-closed promotion metadata requirements.
- [x] Run focused tests and verify missing metadata APIs fail.
- [x] Add timestamp/label aggregation, `BacktestReportMetadata`, report defaults,
  and `require_promotion_metadata()`.
- [x] Run focused and related calibration tests.

### Task 3: Documentation and full verification

**Files:**
- Modify: `docs/PROJECT_STATUS.md`
- Modify: this plan checklist

- [x] Document the complete report contract.
- [x] Run `.venv/bin/pytest -q` and require zero failures.
- [x] Run `.venv/bin/python -m compileall -q src tests scripts` and require exit 0.
- [x] Record exact verification evidence and persist the outcome in UAMS.
