# PAPER Operational Handlers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire real file-backed PAPER learning reruns and historical-export strategy calibration into deployment while preserving the explicit Kite access-token/live-feed blocker.

**Architecture:** Add focused scheduler adapters around existing learning and calibration services, then compose them from explicit CLI paths. Extend deployment preflight with actionable local/external blocker categories and credential-specific checks.

**Tech Stack:** Python 3, dataclasses, JSON, pathlib, pytest, existing ArthaBot audit/backtest/calibration services.

---

### Task 1: File-backed learning rerun handler

**Files:**
- Create: `src/arthabot/operational_handlers.py`
- Create: `tests/unit/test_operational_handlers.py`

- [x] Write tests proving valid PAPER queue entries are parsed, delegated to `LearningRerunWorker`, summarized, and cleared only after success.
- [x] Run `pytest tests/unit/test_operational_handlers.py -v` and confirm failure because the handler does not exist.
- [x] Implement strict JSON parsing for `name`, `target`, `value`, and `mode`; reject non-PAPER modes and non-rerun targets before worker execution.
- [x] Add tests proving malformed/unsafe/failed queues remain intact and empty queues return a successful zero-work result.
- [x] Run `pytest tests/unit/test_operational_handlers.py -v` and confirm all learning-handler tests pass.

### Task 2: Historical calibration scheduler handler

**Files:**
- Modify: `src/arthabot/operational_handlers.py`
- Modify: `tests/unit/test_operational_handlers.py`

- [x] Write a failing test for a callable adapter that invokes `StrategyCalibrationRunService.run` and returns configured, promotable, and rejected versions.
- [x] Implement the adapter without swallowing service errors so critical scheduler execution fails closed.
- [x] Run `pytest tests/unit/test_operational_handlers.py -v` and confirm the calibration tests pass.

### Task 3: Deployment composition

**Files:**
- Modify: `src/arthabot/deployment_service_cli.py`
- Create or modify: `tests/unit/test_deployment_service_cli.py`

- [x] Write failing CLI composition tests requiring explicit learning queue and historical JSON paths and proving no fake live-feed handler is injected.
- [x] Add factories that build the existing learning workflow/worker and calibration service from repository configuration and explicit data paths.
- [x] Make incomplete normal composition return a non-zero status before scheduler execution; retain the explicitly requested no-op diagnostic mode.
- [x] Run `pytest tests/unit/test_deployment_service_cli.py -v` and confirm all tests pass.

### Task 4: Actionable preflight blockers

**Files:**
- Modify: `src/arthabot/secrets.py`
- Modify: `src/arthabot/deployment_preflight.py`
- Modify: `src/arthabot/deployment_preflight_cli.py`
- Modify: `tests/unit/test_deployment_preflight.py`
- Modify or create: `tests/unit/test_deployment_preflight_cli.py`

- [x] Write failing tests for separate Kite API credential and access-token checks plus `local_reason_codes` and `external_reason_codes`.
- [x] Add narrowly scoped credential properties and blocker classification without weakening `has_zerodha_credentials`.
- [x] Include both blocker categories in CLI JSON output.
- [x] Run the focused preflight test files and confirm they pass.

### Task 5: Verification and documentation

**Files:**
- Modify: `docs/PROJECT_STATUS.md`

- [x] Run all focused handler, deployment, preflight, learning, and calibration tests.
- [x] Run `pytest -q` and require a clean pass.
- [x] Run `python -m compileall -q src tests` and require exit code 0.
- [x] Run deployment preflight with current local evidence and record the remaining access-token/live-feed blockers without exposing credentials.
- [x] Update project status with implemented handlers, verification evidence, and unresolved external deployment requirements.
- [x] Persist durable outcomes and unresolved safety risks to UAMS.
