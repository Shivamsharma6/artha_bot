# ArthaBot Runtime Recovery Design

## Scope

Restore PAPER operation when Zerodha's daily access token expires, prevent candidate-provider retry storms, persist dashboard/PAPER runtime state across restarts, and bound audit-log growth.

## Authentication

`scripts/login_zerodha.py` will support a local HTTP callback. It opens the official Kite login URL, waits for Zerodha to redirect to a configured loopback URL, validates the callback status, exchanges the short-lived `request_token` through the official SDK, writes only the resulting access token to the owner-only `.env`, and performs a read-only profile validation. Password and TOTP entry remain interactive in Zerodha's browser page; ArthaBot never stores those credentials.

Runtime HTTP failures that identify an invalid or expired Kite session are normalized to `KITE_REAUTH_REQUIRED`. PAPER trading fails closed and emits one actionable audit event rather than treating every candidate refresh as an unrelated provider failure.

## Persistence

The PAPER loop writes an atomic, versioned runtime snapshot after every cycle. The snapshot contains dashboard metrics and simulated trade records needed to restore state, but no secrets. The dashboard API loads the last snapshot at startup and exposes it through a state endpoint; WebSocket clients receive the latest snapshot when they connect.

## Audit Retention

`JsonlAuditStore` gains optional size-based rotation. Routine scheduler skip events are suppressed by default because the scheduler's due-state and job outcomes already provide the durable operational evidence. Failure, execution, stop, and completion events remain audited.

## Safety

No login bypass, password automation, TOTP storage, order placement, LIVE-mode promotion, or risk-rule change is introduced. Authentication, fresh quotes, candidate generation, Hermes, Risk, and PAPER execution remain separate gates.

