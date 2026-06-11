# PAPER Deployment Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove ArthaBot is safe and operationally ready for a PAPER-only EC2 deployment before any remote action.

**Architecture:** Add a deterministic preflight service and CLI that compose existing config/secret loaders, filesystem checks, and explicit handler evidence. Persist only redacted reason codes and statuses; remote deployment remains a separate approved operation after a passing preflight.

**Tech Stack:** Python dataclasses, pathlib/stat, JSON, argparse, pytest.

---

### Task 1: Preflight domain checks

**Files:**
- Create: `src/arthabot/deployment_preflight.py`
- Create: `tests/unit/test_deployment_preflight.py`

- [x] Write failing tests for ready, mode, LIVE, leverage, credentials, handlers,
  writable paths, sensitive-file permissions/ignore status, and SSH key checks.
- [x] Run focused tests and verify the module is missing.
- [x] Implement stable check/reason models and deterministic evaluation.
- [x] Run focused tests and require all passing.

### Task 2: Audited preflight CLI

**Files:**
- Create: `src/arthabot/deployment_preflight_cli.py`
- Create: `scripts/check_deployment_preflight.py`
- Create: `tests/unit/test_deployment_preflight_cli.py`

- [x] Write failing CLI tests for redacted artifact output and non-zero blockers.
- [x] Implement environment-backed CLI wiring without parsing secret files.
- [x] Run focused CLI tests and require all passing.

### Task 3: Verification and EC2 readiness decision

**Files:**
- Modify: `docs/PROJECT_STATUS.md`
- Modify: this plan checklist

- [x] Run the preflight against current local state without printing secrets.
- [x] Run `.venv/bin/pytest -q` and compileall.
- [x] If preflight passes, request explicit network approval and perform only the
  approved PAPER deployment steps; otherwise record exact non-secret blockers.
- [x] Persist the outcome in UAMS.
