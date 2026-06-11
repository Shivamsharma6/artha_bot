# ArthaBot Project Status

Date: 2026-06-11

## Implemented Bootstrap Slice

* `AGENTS.md` includes the UAMS Memory Protocol.
* Python package scaffold exists under `src/arthabot`.
* Default repository mode guidance is PAPER, not LIVE.
* Config files exist for risk, brokerage, modes, strategy, and instruments.
* Brokerage engine estimates intraday equity costs, slippage, net P&L, and break-even.
* Risk engine blocks stale data, duplicate positions, late entries, max-trade breaches,
  max-daily-loss breaches, invalid stop loss, missing trailing stop, leverage, and
  unapproved LIVE mode.
* Hermes decision contract requires cost-aware break-even and trailing stop logic.
* Execution engine simulates BACKTEST and PAPER orders and blocks unapproved LIVE orders.
* Audit logger redacts secret-like fields.
* Data, strategy, backtest, paper, and learning modules have initial safety boundaries.
* Runtime config loader validates non-LIVE defaults and no-leverage configuration.
* Reconciliation service fails closed on cash, account-balance, and position mismatches.
* Trailing stop policy uses step, cooldown, and modification-limit rules.
* Daily report summarizes accepted trades, rejected trades, gross P&L, costs, net P&L,
  and ending capital.
* Secret loader reads credentials from environment variables and masks values in repr.
* Zerodha gateway boundary requires credentials and injected live adapter before broker
  order submission.
* Order reconciliation fails closed on unknown broker states, missing broker orders,
  status mismatches, symbol mismatches, and fill mismatches.
* Backtest accounting reports net profit after costs, gross profit, costs, win rate,
  rejected trades, drawdown, and long-vs-short net P&L.
* Market data cache stores live snapshots with freshness enforcement and historical
  bars with explicit data resolution.
* Deterministic news sentiment engine scores configured positive and negative terms.
* Paper session records simulated fills and rejected trades into daily reports.
* Live promotion gate requires every safety condition plus explicit human approval.
* Zerodha gateway boundary supports injected order modify and cancel adapters with
  credential, quantity, price, and order-id validation.
* Live feed monitor tracks WebSocket-style ticks and reports missing, stale, future,
  and fresh quote health states.
* Zerodha WebSocket feed adapter boundary requires credentials, subscribes by
  instrument token through an injected ticker factory, normalizes ticks into the
  freshness monitor, and rejects unmapped or timestampless ticks.
* Live feed reconnect controller uses bounded exponential backoff, resets after
  successful connection, and fails closed with `LIVE_FEED_UNSTABLE` after repeated
  disconnects so trading can stop on abnormal market-data behavior.
* Live feed supervisor wraps the WebSocket feed client and reconnect controller,
  auditing successful connections, scheduled reconnects, and fail-closed feed
  instability decisions for scheduler-driven deployments.
* Backtest execution loop converts valid signals into cost-adjusted trades and counts
  rejected and missed trades.
* JSONL audit store persists redacted audit events and can read them back in order.
* Learning report detects degraded strategy windows and proposes PAPER-mode parameter
  changes through the Learning Engine guardrails.
* Validation harness converts evidence into the live-promotion checklist so missing
  data depth, unresolved bugs, stale-data issues, and missing approval block LIVE mode.
* Historical data provider boundary normalizes injected client rows into internal
  datasets without hardcoding a vendor.
* Historical data provider can be built from Zerodha/Kite instrument-token mappings;
  it requires explicit backtest date ranges, calls `/instruments/historical/:token/:interval`,
  maps internal resolutions to Kite intervals, and normalizes candle-array responses.
* Historical range chunker splits long backtest ranges into provider-safe windows
  by resolution and merges chunked candle responses for multi-month and multi-year
  data fetches.
* Instrument token cache parses Zerodha `/instruments/:exchange` CSV rows, indexes
  tokens by `exchange:tradingsymbol`, fails closed on stale daily caches, rejects
  duplicate rows, and exports token maps for historical data providers.
* Instrument token store persists daily token snapshots to auditable JSON, reloads
  snapshots into the cache, and pre-market refresh planner decides when a daily
  instrument refresh is due.
* Pre-market instrument refresh job uses the planner, cache, persistent store, and
  audit log to refresh daily tokens, skip fresh caches, and fail closed on refresh
  errors.
* Scheduler runner executes named time-of-day jobs once per day, audits completed,
  skipped, and failed outcomes, and marks critical job failures as stop-trading
  conditions.
* Runtime job factory composes PAPER-safe scheduled jobs for instrument refresh and
  news ingestion from injected provider clients, secrets, stores, and query builders.
* News provider boundary requires `NEWS_API_KEY` when configured for live access and
  normalizes injected client rows into internal articles.
* News provider can be built from a News API `/v2/everything` client with explicit
  date windows, header-based API-key authentication, provider error rejection, and
  headline/source normalization for sentiment scoring.
* News query builder expands market symbols into configured company/search terms,
  and news provider backoff controller uses bounded exponential retry decisions
  before failing closed with `NEWS_PROVIDER_UNSTABLE`.
* Replay paper runner executes replay signals through PAPER-mode simulation and counts
  unexecutable signals as missed trades.
* Validation analytics can build walk-forward train/test windows, split
  out-of-sample periods chronologically, flag missing constituent membership history
  as survivorship-bias risk, and summarize backtest performance by time window.
* Strategy comparison harness ranks strategy versions by net profit and drawdown,
  marks drawdown and non-positive-profit failures as not promotable, and exposes the
  best result.
* Learning comparison report identifies the best strategy and proposes PAPER-mode
  backtest reruns for weaker strategy versions through Learning Engine guardrails.
* Operational audit helper writes decision, risk rejection, and execution update events
  to persistent redacted audit storage.
* Broker trailing-stop workflow validates open position, modifiable broker stop state,
  matching quantity, fresh quote, step/cooldown policy, and then calls the injected
  gateway modify adapter while auditing outcomes.
* Human LIVE approval workflow records explicit approver, timestamp, strategy version,
  checklist decision, and stores approval only when the live-promotion gate passes.
* Broker balance provider boundary requires Zerodha credentials, uses an injected
  balance client, and normalizes available cash for reconciliation.
* Broker balance provider can be built from the Zerodha HTTP client; it fetches
  `/user/margins/:segment`, uses Kite API version headers, and normalizes
  `available.live_balance` as reconciled available cash.
* Live-feed paper loop ingests ticks, rejects stale/missing feed signals as missed
  trades, executes fresh signals through PAPER-mode simulation, and audits outcomes.
* PAPER runtime pipeline orchestrates Strategy candidate -> Hermes proposal -> Risk
  decision -> PAPER execution with audit events, while stale feed data is rejected
  and logged.
* Operational learning workflow runs PAPER-mode injected backtest reruns from learning
  recommendations, stores JSON comparison artifacts, rejects LIVE-mode reruns, and
  audits rerun outcomes.
* Human LIVE approval interface renders explicit checklist templates, loads structured
  approval JSON, submits through the audited approval workflow, and includes a CLI
  entrypoint at `scripts/approve_live.py`.
* External HTTP client scaffolds build redacted transport requests for Zerodha order
  placement, historical data fetches, and news fetches using injected transports and
  required credential checks.
* Production HTTP transport boundary uses stdlib URL requests with JSON encoding,
  timeout configuration, non-2xx failure handling, and injectable openers for tests.
* Zerodha HTTP client supports credential-gated place, modify, and cancel order
  requests through the injectable transport boundary.
* Breakout, reversal, and high-volume mover signal engines generate ranked trade
  candidates only; they do not place orders or bypass Hermes, Risk, or Execution.
* Provider-backed PAPER loop coordination runs scheduled provider jobs before
  strategy candidates, fails closed when a critical provider job returns a
  stop-trading condition, and only then routes candidates through the audited
  PAPER runtime pipeline.
* Deployment scheduler configuration exists in `config/deployment.yaml` for
  PAPER-mode operational jobs, including instrument refresh, news ingestion,
  live-feed supervision, operational learning reruns, and historical strategy
  calibration reruns; the loader rejects unsafe LIVE deployments when live
  trading is disabled.
* Deployment scheduler worker builds enabled jobs from the deployment manifest,
  rejects unknown job types, runs due jobs through the audited scheduler runner,
  skips disabled jobs, and fails closed when a critical configured job fails.
* Deployment scheduler service loop can run bounded or continuous worker ticks,
  sleeps between ticks, audits service completion and stop-trading events, and
  includes a safe CLI wrapper at `scripts/run_deployment_scheduler.py`.
* Provider-backed deployment job registry maps deployment config job types to
  injected PAPER-safe operational jobs for instrument refresh, news ingestion,
  live-feed supervision, learning reruns, and strategy calibration reruns; the
  CLI requires an explicit `--allow-noop-registry` flag before running
  placeholder jobs.
* Production-like PAPER deployment command builder loads PAPER deployment config,
  reads credentials from environment-backed `SecretConfig`, constructs Zerodha
  and News API clients through injectable HTTP transports, persists instrument
  snapshots, and wires the deployment scheduler service to provider-backed jobs
  without enabling LIVE trading.
* News-source curation is config-driven via `config/news.yaml`; News API
  ingestion uses an explicit domain allowlist and curated company search terms,
  and provider-backed deployment jobs pass that policy into every news request.
* Strategy calibration gate records auditable evidence for data depth,
  resolution, costs, walk-forward windows, out-of-sample testing, survivorship
  checks, expectancy, net profit, drawdown, and rejected-trade logging before a
  strategy can be considered promotable; live promotion validation treats
  missing calibration as a live-safety blocker.
* Strategy calibration artifact store persists and reloads calibration evidence
  plus gate decisions as JSON artifacts so historical validation results can be
  audited and reused for promotion decisions.
* Strategy calibration job runner builds calibration evidence from injected
  historical coverage and backtest summary providers, evaluates the calibration
  gate, persists the artifact, and audits promotability plus rejection reasons.
* Backtest reports can be converted into calibration backtest summaries with
  derived expectancy, cost-awareness, drawdown, rejected-trade counts, and
  validation flags for calibration job inputs.
* Strategy calibration registry dispatches named strategy versions to injected
  calibration runners and fails closed for unknown strategy versions, providing
  the wiring point for momentum, breakout, reversal, and volume-mover jobs.
* Historical datasets can be converted into calibration coverage evidence with
  symbols, date span, and resolution, while empty or mixed-resolution datasets
  are rejected before calibration.
* Strategy calibration factory builds the core momentum, breakout, reversal, and
  volume-mover calibration registry from historical datasets, cost-aware
  backtest reports, and explicit validation flags, failing closed when required
  evidence inputs are missing.
* Historical strategy backtest builder converts historical candle datasets into
  market snapshots, lets injected strategy engines generate candidates, converts
  those candidates into backtest signals, and runs them through cost-aware
  backtest execution before calibration.
* Historical backtest-to-calibration input adapter generates calibration factory
  inputs from versioned datasets, strategy engines, execution engines, quantities,
  and explicit validation flags, failing closed when any strategy version is
  missing required builder inputs.
* Strategy calibration configuration in `config/strategy.yaml` declares explicit
  momentum, breakout, reversal, and volume-mover historical calibration jobs with
  symbols, resolution, date windows, quantities, validation flags, and engine
  parameters.
* Strategy calibration config loader and composer fetch provider-backed
  historical datasets for configured symbols/date ranges, instantiate the
  concrete core signal engines, run brokerage-aware historical backtests, and
  produce calibration factory inputs without enabling LIVE trading.
* Strategy calibration run service executes configured historical calibration
  backtests, builds the strategy calibration registry for selected versions,
  persists calibration artifacts, and audits batch promotability summaries.
* Historical strategy calibration CLI and `scripts/run_strategy_calibration.py`
  can run the calibration service from an explicit historical JSON export,
  producing auditable calibration artifacts without live orders or implicit
  credentials.
* Scheduled PAPER deployment wiring includes a non-critical
  `strategy_calibration` job that calls an explicitly injected calibration
  handler after market-close provider jobs, keeping recurring calibration
  auditable without enabling LIVE trading.
* Runtime strategy configuration in `config/strategy.yaml` declares enabled
  momentum, breakout, reversal, and volume-mover strategy versions for PAPER
  candidate generation.
* Configured runtime strategy provider instantiates allowlisted signal engines
  from strategy config, generates ranked `TradeCandidate` objects with strategy
  version metadata from injected fresh market snapshots, and keeps strategies
  candidate-only so Hermes, Risk, and PAPER execution remain separate.
* Provider-backed PAPER loop coverage verifies configured runtime strategy
  candidates can flow through provider jobs, Hermes, Risk, and PAPER execution
  while preserving strategy version audit context.
* Runtime market snapshot provider normalizes injected top-mover rows into
  fresh `MarketSnapshot` objects and fails closed on stale mover data before any
  strategy candidate generation.
* Runtime strategy candidate composer fetches fresh top-mover snapshots and
  feeds them into the configured strategy provider, producing candidates for the
  provider-backed PAPER loop without live credentials or order placement.
* Kite smoke-test runner exercises broker balance reconciliation and, only with
  explicit non-live approval, order place/modify/cancel adapter request wiring
  through injected clients while auditing probe outcomes.
* `scripts/run_kite_smoke.py` provides an env-backed smoke CLI that defaults to
  balance-only checks and refuses order-adapter probes unless
  `--approved-non-live-order-probe` is supplied.
* Operational audit coverage checker validates that required runtime event
  families are present in JSONL audit logs, including decisions, risk decisions,
  PAPER execution, provider loop completion, scheduler completion, calibration,
  Kite smoke probes, and human live approval.
* `scripts/check_operational_audit_coverage.py` returns a non-zero exit code
  when required operational audit event coverage is missing.
* Deployment scheduler service can run an optional fail-closed operational audit
  coverage gate after bounded scheduler runs, stopping deployment if required
  audit event families are missing.
* Operational learning rerun worker executes PAPER-mode backtest rerun changes
  with bounded retries, audits failed attempts, writes rerun artifacts through
  the existing workflow, and fails closed for scheduler use when retry limits are
  exhausted.
* Learning rerun scheduler handler adapts the worker into a deployment-scheduler
  payload with completed/failed counts and stop-trading status.
* Live approval package builder creates deployable approval artifacts containing
  the rendered human approval checklist template and manifest metadata while
  refusing configs where LIVE is enabled or human approval is not required.
* `scripts/package_live_approval.py` packages the approval request flow for a
  strategy version and audits the generated artifact paths without enabling LIVE
  trading.
* Promotion readiness auditor converts calibration artifacts, PAPER results,
  unresolved safety issue counts, stale-data evidence, live-safety evidence, and
  human approval state into an explicit `LivePromotionGate` decision artifact
  while keeping `live_enabled` false.
* `scripts/review_promotion_readiness.py` writes an audited promotion readiness
  JSON review and fails closed when calibration, PAPER, safety, or human approval
  evidence is missing.
* Market eligibility policy in `config/market.yaml` defines the NSE timezone,
  regular-session boundaries, configured holidays, and fail-closed corporate
  action behavior.
* Market eligibility guard rejects weekends, configured holidays, out-of-session
  timestamps, active corporate actions, and unknown corporate-action state with
  stable reason codes before runtime strategy candidate generation.
* Guarded runtime candidate composition requires explicit top-mover and corporate
  action providers, audits eligibility rejections, and prevents external mover
  requests when the market itself is ineligible.
* Backtest accounting now reports average win, average loss, profit factor,
  expectancy, best and worst day, a Sharpe-like daily metric, open/close and
  arbitrary time-window net P&L, while preserving cost-adjusted net results.
* Backtest report metadata records strategy version, data period, and resolution;
  promotion consumers can fail closed through `require_promotion_metadata()`.
* Backtest execution preserves all derived accounting metrics when adding missed
  trade counts, and timestamped trades are classified into first-hour open,
  final-hour close, or midday performance windows.
* Deployment preflight validates PAPER-only modes, disabled LIVE/leverage,
  required environment credentials, real operational handlers, writable audit
  and instrument paths, owner-only sensitive files/SSH keys, and Git-ignore
  evidence before any EC2 deployment is allowed.
* `scripts/check_deployment_preflight.py` writes only redacted check names and
  reason codes, audits the result, and returns non-zero when deployment is not
  ready. It never parses prose secret exports or invokes broker order endpoints.
* Local deployment preflight currently fails closed because Zerodha/News
  credentials are not loaded through environment variables and live-feed,
  learning-rerun, and calibration handlers remain placeholders. No EC2 access or
  deployment was attempted.
* Owner-only secret export importer recognizes exact Kite API key/secret,
  optional access-token, and NewsAPI labels, rejects duplicate/empty/unsafe
  inputs, and returns only the existing redacted `SecretConfig` in memory.
* Read-only NewsAPI smoke runner requests at most one article and audits only
  provider, success, and article-count metadata. A real probe completed
  successfully on 2026-06-11 with zero matching articles returned.
* Production HTTP transport now passes urllib timeouts by keyword; a regression
  test closes the positional-argument bug that previously prevented real GETs.
* Kite authenticated probes remain blocked because the current secret export has
  no access token. No Kite API request, order operation, EC2 access, or deployment
  was attempted.

## Verified

Command:

```bash
.venv/bin/pytest -q
```

Latest observed result:

```text
264 passed in 0.43s
```

## Not Yet Complete

The full constitution is not complete yet. Remaining work includes:

* Real production credentials, live broker sessions, and human approval have not
  been supplied in this repository environment
* LIVE trading remains intentionally disabled until external smoke tests,
  calibration artifacts, PAPER results, audit coverage, and a signed human
  approval package are reviewed
* PAPER EC2 deployment remains blocked until the deployment preflight passes;
  the current non-secret blockers are recorded above

No live trading is implemented or enabled.
