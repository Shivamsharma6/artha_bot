# Market Eligibility Guard Design

## Purpose

ArthaBot must reject runtime candidates when the NSE market is closed or when a
symbol is subject to a configured corporate-action exclusion. This closes the
market-calendar and corporate-action-awareness gaps in `AGENTS.md` without
granting LIVE permission or moving order authority out of Risk and Execution.

## Architecture

Add a focused `MarketEligibilityGuard` in `src/arthabot/market_eligibility.py`.
It receives immutable session configuration, holiday dates, and an injected
corporate-action provider. It returns a structured eligibility decision with a
stable reason code instead of silently filtering input.

`RuntimeMarketSnapshotProvider` receives the guard as an optional dependency.
When supplied, it evaluates the requested timestamp before calling the mover
provider and evaluates every normalized symbol before returning snapshots. Any
ineligible condition raises `MarketEligibilityError`, so no strategy candidate
can be produced from unsafe market context.

## Rules

* Times are converted to `Asia/Kolkata` before evaluation.
* Saturday and Sunday are closed.
* Configured NSE holidays are closed.
* The regular session is inclusive from 09:15 through 15:30 IST.
* A missing or failed corporate-action provider is fail-closed.
* An active corporate action rejects only the affected symbol.
* Rejections use stable reason codes: `MARKET_WEEKEND`, `MARKET_HOLIDAY`,
  `MARKET_SESSION_CLOSED`, `CORPORATE_ACTION_ACTIVE`, and
  `CORPORATE_ACTION_STATE_UNKNOWN`.
* Existing callers without an injected guard retain current behavior, allowing
  staged adoption in PAPER deployments.

## Configuration

Add `config/market.yaml` with timezone, regular-session boundaries, holidays,
and a fail-closed corporate-action setting. A loader validates timezone and
time/date values. The initial holiday list is explicitly configuration data,
not claimed as a complete exchange calendar; production refresh can replace it
through the same boundary.

## Auditability

The guard itself is deterministic. `RuntimeMarketSnapshotProvider` optionally
receives `JsonlAuditStore` and records `market_eligibility_rejected` with the
reason code, symbol when applicable, and evaluation timestamp before raising.
No secret or provider payload is logged.

## Testing

Unit tests cover open-session acceptance, weekends, configured holidays,
outside-session times, active corporate actions, provider failure, timezone
conversion, config loading, runtime-provider rejection, and audit events.
Existing runtime-provider tests must continue to pass without guard injection.

