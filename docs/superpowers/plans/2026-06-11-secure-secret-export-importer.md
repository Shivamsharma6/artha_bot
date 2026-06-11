# Secure Secret Export Importer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import the approved credential export into memory safely and validate NewsAPI read access without weakening Kite safety gates.

**Architecture:** Add a strict parser beside `SecretConfig`, then a small read-only NewsAPI smoke service using existing HTTP clients and redacted audit storage. No persistence or environment mutation is introduced.

**Tech Stack:** Python pathlib/stat, dataclasses, existing HTTP clients, pytest.

---

### Task 1: Strict in-memory importer

**Files:**
- Modify: `src/arthabot/secrets.py`
- Modify: `tests/unit/test_secrets_and_broker_gateway.py`

- [x] Add failing tests for valid, missing token, duplicate, unsafe mode, and
  redacted failure behavior.
- [x] Implement strict label parsing and owner-only validation.
- [x] Run focused tests.

### Task 2: NewsAPI read-only smoke

**Files:**
- Create: `src/arthabot/news_smoke.py`
- Create: `tests/unit/test_news_smoke.py`

- [x] Add failing injected-client tests proving no secret data enters audit.
- [x] Implement minimal read-only smoke service.
- [x] Run focused tests, then run the real probe using in-memory imported data.

### Task 3: Verification and status

**Files:**
- Modify: `docs/PROJECT_STATUS.md`
- Modify: this checklist

- [x] Run full tests and compileall.
- [x] Record NewsAPI probe outcome without secret values.
- [x] Persist the distilled outcome to UAMS.
