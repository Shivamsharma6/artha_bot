# Market Eligibility Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent runtime strategy candidate generation on closed NSE sessions or active/unknown corporate-action states.

**Architecture:** Add a deterministic eligibility guard and validated YAML loader, then inject the guard and optional audit store into the existing runtime market snapshot provider. All unsafe states fail closed before strategy generation, while existing non-injected callers remain compatible.

**Tech Stack:** Python 3.14, dataclasses, `zoneinfo`, PyYAML, pytest, JSONL audit storage.

---

### Task 1: Market eligibility domain and configuration

**Files:**
- Create: `src/arthabot/market_eligibility.py`
- Create: `config/market.yaml`
- Test: `tests/unit/test_market_eligibility.py`

- [x] Write failing tests for open sessions, weekends, holidays, session hours,
  corporate-action exclusions, provider failures, timezone conversion, and YAML
  validation.
- [x] Run `.venv/bin/pytest tests/unit/test_market_eligibility.py -q` and verify
  failure because `arthabot.market_eligibility` does not exist.
- [x] Implement `MarketEligibilityConfig`, `MarketEligibilityDecision`,
  `MarketEligibilityError`, `load_market_eligibility_config`, and
  `MarketEligibilityGuard` with stable reason codes and fail-closed provider
  behavior.
- [x] Run the focused test and verify it passes.

### Task 2: Runtime provider enforcement and auditing

**Files:**
- Modify: `src/arthabot/runtime_market_provider.py`
- Modify: `tests/unit/test_runtime_market_provider.py`

- [x] Write failing tests proving market-level rejection occurs before the mover
  client call and symbol-level rejection occurs before snapshots reach strategy
  generation, with `market_eligibility_rejected` audit evidence.
- [x] Run `.venv/bin/pytest tests/unit/test_runtime_market_provider.py -q` and
  verify the new tests fail against the current constructor.
- [x] Add optional `eligibility_guard` and `audit` dependencies, enforce market
  and symbol decisions, audit rejection metadata, and raise
  `MarketEligibilityError`.
- [x] Run both focused test files and verify they pass.

### Task 3: Documentation and verification

**Files:**
- Modify: `docs/PROJECT_STATUS.md`

- [x] Document the guard, configuration, fail-closed corporate-action behavior,
  and runtime-provider integration.
- [x] Run `.venv/bin/pytest -q` and require zero failures.
- [x] Run `.venv/bin/python -m compileall -q src tests scripts` and require exit 0.
- [x] Record the exact verification result in `docs/PROJECT_STATUS.md` and store
  the durable outcome in UAMS.
