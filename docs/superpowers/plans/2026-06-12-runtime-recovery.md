# ArthaBot Runtime Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore reliable PAPER operation with broker-compliant daily Zerodha reauthentication, durable runtime state, and bounded audit storage.

**Architecture:** Add a focused login callback boundary, normalize expired-session errors at the HTTP client boundary, persist versioned PAPER runtime snapshots atomically, and rotate JSONL audit files by size. Existing risk and execution layering remains unchanged.

**Tech Stack:** Python 3.12, Kite Connect SDK, standard-library HTTP server, FastAPI, pytest, JSONL/JSON persistence.

---

### Task 1: Zerodha session renewal

**Files:** `src/arthabot/zerodha_auth.py`, `scripts/login_zerodha.py`, `tests/unit/test_zerodha_auth.py`

- [x] Write tests for callback parsing, token exchange/storage, and rejected callbacks.
- [x] Run the focused tests and confirm they fail for the missing module.
- [x] Implement the loopback callback and read-only validation workflow.
- [x] Run focused tests and confirm they pass.

### Task 2: Expired-session classification

**Files:** `src/arthabot/http_clients.py`, `src/arthabot/runtime_market_provider.py`, `tests/unit/test_http_clients.py`

- [x] Write tests proving token exceptions become `KITE_REAUTH_REQUIRED` and no candidates are emitted.
- [x] Run the tests and confirm the expected failure.
- [x] Add the typed authentication error and fail-closed classification.
- [x] Run focused tests and confirm they pass.

### Task 3: Durable PAPER/dashboard snapshots

**Files:** `src/arthabot/runtime_state.py`, `src/arthabot/dashboard_api.py`, `scripts/run_paper_loop.py`, `tests/unit/test_runtime_state.py`, `tests/unit/test_dashboard_api.py`

- [x] Write round-trip, corrupt-state, restart, and API state tests.
- [x] Run the tests and confirm the missing behavior fails.
- [x] Implement atomic versioned snapshot storage and wire it into the loop/API.
- [x] Run focused tests and confirm they pass.

### Task 4: Bounded audit volume

**Files:** `src/arthabot/audit_store.py`, `src/arthabot/scheduler.py`, `tests/unit/test_audit_storage_learning_validation.py`, `tests/unit/test_scheduler.py`

- [x] Write tests for size rotation and skip-event suppression.
- [x] Run the tests and confirm failures.
- [x] Implement rotation and suppress routine skip writes.
- [x] Run focused tests and confirm they pass.

### Task 5: Operational verification

**Files:** `README.md`, `.env.example`, `docs/PROJECT_STATUS.md`

- [x] Document the daily login command, callback URL requirement, state path, and audit limits.
- [ ] Run focused tests, the full unit suite, source compilation, and safe read-only CLI checks.
- [ ] Inspect the diff for secrets, LIVE bypasses, and unrelated changes.
