# AGENTS.md — ArthaBot Project Constitution

## Project Name

ArthaBot

## Core Mission

ArthaBot is an intraday trading bot for the Indian stock market.

Its purpose is to identify high-probability intraday opportunities, execute trades through the Zerodha Kite API, manage risk aggressively, and improve over time using backtesting, paper trading, live feedback, and model learning.

The core idea of this project must not be changed without explicit human approval.

ArthaBot should become smarter over time, but never less safe.

## Prime Directive

Capital preservation comes before profit maximization.

No code, agent, model, or strategy may bypass:

* Risk controls
* Brokerage/cost awareness
* Dynamic stop-loss logic
* Intraday square-off rules
* No-leverage rules
* Live-mode safety gates
* Audit logging

ArthaBot must never prioritize speed in a way that makes it unsafe.

## Non-Negotiable Trading Constraints

ArthaBot must always follow these constraints unless this constitution is explicitly updated:

* Market: Indian stock market
* Trading style: Intraday only
* Broker/API: Zerodha Kite API
* Decision engine: Hermes agent
* Initial seed capital: ₹5,000
* Leverage: Not allowed in the current version
* Position type: Long and short intraday trades allowed
* Holding period: No overnight positions
* Capital allocation: Minimum 5% of available capital per trade, subject to risk rules
* Brokerage and statutory charges: Must be included in profitability calculations
* Risk control: Active trailing stop loss is mandatory
* Stop-loss behavior: Must be dynamic because selected stocks may be highly volatile
* Compounding: Profits and losses must update deployable capital
* Account balance: Zerodha/account balance must be checked and reconciled regularly
* Data requirement: Use historical data for backtesting and learning
* Preferred backtest depth: Minimum 3 years of data where available
* Market timing focus: Prioritize high-movement periods near market open and market close
* Daily universe: Include constantly updating top movers/gainers as a primary candidate source
* News input: Integrate News API or equivalent news/sentiment source
* Human involvement: Minimal, but live-trading promotion requires safety gates

## Important Trading Assumptions

ArthaBot is being designed for a small starting capital base.

Because the initial capital is ₹5,000, the system must be extra careful about:

* Brokerage impact
* Slippage
* Overtrading
* Minimum profitable movement
* Liquidity
* Position sizing
* False signals during volatile periods
* Losses caused by frequent entries/exits

A strategy that looks profitable before costs may become unprofitable after costs.

## System Architecture

ArthaBot should be organized into the following modules.

### 1. Data Ingestion

Responsibilities:

* Historical OHLCV data
* Live market feed
* Daily top gainers
* Daily top losers
* Top movers
* High-volume movers
* Gap-up stocks
* Gap-down stocks
* News and sentiment data
* Instrument metadata
* Market calendar
* Corporate action awareness where relevant

Design notes:

* Top movers list can update throughout the day.
* The system must not assume that the morning top gainers list remains valid all day.
* Live candidates should be refreshed periodically.
* Market data freshness must be checked before any trade decision.
* Stale data must block trading.

### 2. Strategy and Signal Engine

Responsibilities:

* Price action signals
* Volume/momentum signals
* Market open movement detection
* Market close movement detection
* Breakout detection
* Reversal detection
* Volatility detection
* News/sentiment influence
* Long opportunity classification
* Short opportunity classification
* Trade candidate scoring

The signal engine may generate candidates, but it must not place orders directly.

### 3. Hermes Decision Agent

Hermes is the decision-making agent.

Responsibilities:

* Evaluate candidate trades
* Score probability, risk, reward, and timing
* Combine technical, price, volume, and news context
* Decide whether a trade is worth considering
* Explain each decision in structured format

Hermes must not directly bypass the Risk Engine.

Hermes must never directly place orders.

Hermes recommendations must pass through the Risk Engine before execution.

For every trade decision, Hermes must output:

* Candidate symbol
* Direction: long or short
* Entry rationale
* Entry price zone
* Stop-loss
* Trailing stop-loss logic
* Target or exit logic
* Expected reward-to-risk ratio
* Cost-aware break-even estimate
* Confidence score
* Reasons to reject the trade, if rejected
* Data used in decision
* Timestamp
* Strategy/model version

### 4. Risk Engine

Responsibilities:

* Position sizing
* Max loss per trade
* Max daily loss
* Max number of trades per day
* No-leverage validation
* Intraday-only validation
* Dynamic stop-loss validation
* Trailing stop-loss validation
* Forced square-off before market close
* Prevention of overtrading
* Prevention of duplicate/conflicting positions
* Prevention of trading during abnormal system behavior

Risk Engine rules override Hermes.

If Hermes and the Risk Engine disagree, the Risk Engine wins.

If risk data is missing, stale, or inconsistent, the system must reject the trade.

### 5. Brokerage and Cost Engine

This module is required, but it must be deterministic, config-based, cached where possible, and extremely fast.

It must not depend on Hermes or any LLM during live order decisions.

The purpose of this module is not to slow down trading. The purpose is to prevent false profitability.

Responsibilities:

* Brokerage estimate
* STT estimate
* Exchange transaction charge estimate
* GST estimate
* SEBI charge estimate
* Stamp duty estimate
* Slippage estimate
* Break-even calculation
* Estimated net P&L before trade entry
* Actual net P&L after trade exit
* Cost-aware backtest reporting

Design notes:

* Do not hardcode brokerage permanently inside strategy logic.
* Brokerage and statutory charges must be configurable.
* If exact live calculation is too slow, use a fast precomputed/cached approximation.
* Live execution should never call an LLM to calculate brokerage.
* Backtesting must include detailed cost calculations.
* Paper trading should include cost calculations.
* Live trading should at least include fast cost-aware break-even checks.

### 6. Backtesting Engine

Responsibilities:

* Minimum 3 years of historical testing where available
* Brokerage-adjusted results
* Slippage-adjusted results
* Walk-forward validation
* Out-of-sample testing
* Strategy comparison
* Drawdown reporting
* Performance by time window
* Performance near market open
* Performance near market close
* Long and short trade simulation
* Stop-loss and trailing stop-loss simulation
* Intraday square-off simulation

Important notes:

* Backtesting must avoid look-ahead bias.
* Backtesting must avoid survivorship bias where possible.
* Entry and exit prices must be realistic.
* Brokerage and slippage must be included.
* Intraday-only behavior must be simulated.
* No overnight positions should be allowed.
* Backtesting must record rejected trades as well as accepted trades.

#### Explanation of Backtesting Terms

Brokerage-adjusted results:

* Results after deducting estimated brokerage, taxes, and statutory charges.

Slippage-adjusted results:

* Results after accounting for the difference between expected price and actual executable price.

Walk-forward validation:

* A process where the system trains or tunes on one time period, tests on a later unseen period, then moves the window forward and repeats.

Out-of-sample testing:

* Testing on data that was not used while designing or tuning the strategy.

Strategy comparison:

* Comparing multiple strategies under the same data, cost, risk, and reporting rules.

Drawdown reporting:

* Measuring the fall from a capital peak to a later low point. This helps estimate how painful losing streaks can become.

#### Historical Data Resolution Concern

If old intraday data is unavailable or lower-resolution than recent data, ArthaBot must handle this explicitly.

Acceptable approaches:

* Cache live intraday data going forward
* Use a verified historical data provider
* Run separate tests for high-resolution and lower-resolution periods
* Clearly mark where resolution changes affect results
* Avoid claiming precision that the data does not support

### 7. Paper Trading Engine

Responsibilities:

* Simulate live trading without real orders
* Use live or replayed market data
* Use the same signal, Hermes, risk, and execution pipeline as live mode
* Record accepted trades
* Record rejected trades
* Record missed trades
* Record simulated fills
* Record simulated slippage
* Record simulated costs
* Produce daily reports

Paper trading must be passed before live trading.

### 8. Execution Engine

Responsibilities:

* Zerodha Kite order placement
* Order modification
* Order cancellation
* Stop-loss handling
* Trailing stop-loss handling
* Square-off handling
* Order status reconciliation
* Position reconciliation
* Error handling
* API failure handling

Execution Engine rules:

* Never place orders in BACKTEST mode.
* Never place real orders in PAPER mode.
* LIVE mode must require explicit configuration.
* All orders must pass Risk Engine approval.
* All orders must be logged.
* All order updates must be reconciled.
* Failed order placement must not be silently ignored.
* Unknown order state must trigger safe behavior.

#### Active Stop-Loss and Trailing Stop Design

Trailing stop-loss must be active and dynamic.

However, the bot must not modify broker-side stop-loss orders on every tick.

The system must account for the difference between:

* Live quote frequency
* WebSocket tick frequency
* REST/order API rate limits
* Order modification limits
* Broker-side order state delays

Before modifying any stop-loss order, ArthaBot must check:

* Position is still open
* Previous order state is valid
* Trade has not already exited
* Current quote is fresh
* Modification is allowed by cooldown/step rules
* Modification does not exceed configured limits
* API/order state is reconciled

Recommended trailing stop behavior:

* Use WebSocket data for live price tracking
* Use step-based trailing
* Use cooldown intervals
* Avoid excessive order modifications
* Keep local shadow stop state
* Confirm broker order state before modification
* Stop trading if order reconciliation fails
* Square off safely if risk state becomes uncertain

### 9. Learning Engine

Responsibilities:

* Learn from backtest results
* Learn from paper trading
* Learn from live trading logs
* Detect strategy degradation
* Detect changing market regimes
* Suggest improvements
* Re-rank signals
* Compare strategy versions
* Run new backtests
* Propose safer parameter changes

ArthaBot may improve autonomously by:

* Analyzing failed trades
* Analyzing rejected trades
* Comparing strategy versions
* Updating model features
* Re-ranking signals
* Adjusting non-critical parameters
* Proposing new strategy variants
* Running new backtests

ArthaBot must not autonomously:

* Disable production risk controls
* Weaken stop-loss rules in live mode
* Increase leverage
* Hold overnight positions
* Ignore brokerage in backtests
* Promote an untested strategy to live trading
* Change capital allocation rules without approval
* Trade live with a new model without validation
* Hide losses
* Hide failed trades
* Hide rejected trades

Learning Engine may propose risk-control changes, but production risk-control changes require validation and explicit promotion.

### 10. Observability and Audit Service

Responsibilities:

* Full trade logs
* Decision logs
* Model version logs
* Strategy version logs
* Risk rejection logs
* Daily performance report
* Error and exception logs
* Order reconciliation logs
* Balance reconciliation logs
* Stop-loss modification logs
* Broker API response logs
* Backtest result logs
* Paper trading result logs
* Live trading result logs

The system must be debuggable after every trading day.

Every trade should answer:

* Why was this trade selected?
* Why was it entered?
* Why was it rejected, if rejected?
* What data was used?
* What was the expected risk?
* What was the expected reward?
* What was the stop-loss?
* How did the trailing stop change?
* Why was the trade exited?
* What was the final net result?

## Required Safety Gates

A strategy cannot trade live unless all of the following are true:

* Backtested on historical data
* Preferably tested on at least 3 years of data where available
* Brokerage and slippage included
* Positive expectancy after costs
* Maximum drawdown within configured limit
* Paper traded successfully
* No unresolved execution bugs
* No unresolved order reconciliation bugs
* No unresolved risk-rule violations
* No stale-data issues
* No known live-mode safety issues
* Human approval granted for first live deployment

## Live Trading Restrictions

During live trading:

* Never use leverage in the current version
* Never hold positions overnight
* Always place or simulate protective stop logic
* Always account for brokerage and statutory charges in at least a fast/cached way
* Always track open positions
* Always track pending orders
* Always track realized P&L
* Always track unrealized P&L
* Always reconcile with Zerodha/account balance
* Always square off before market close
* Stop trading after max daily loss is hit
* Stop trading after abnormal API behavior
* Stop trading after abnormal market data behavior
* Stop trading after order reconciliation failure
* Do not trade if market data is stale
* Do not trade if account balance cannot be verified
* Do not trade if position state is uncertain
* Do not trade if order status reconciliation fails

Zerodha/account balance is important for reconciliation, but internal live risk state must still be maintained.

## Capital and Position Sizing

Initial seed capital is ₹5,000.

The bot should use compounding, meaning available capital changes after every realized profit or loss.

Minimum capital allocation per trade is 5% of available capital, but actual position size must also respect:

* Stop-loss distance
* Max risk per trade
* Brokerage and charges
* Available cash
* No-leverage rule
* Liquidity
* Minimum order quantity
* Exchange constraints
* Broker constraints
* Open positions
* Pending orders
* Daily loss limit

If these constraints conflict, risk control wins.

Current version must not use leverage.

Future leverage support requires:

* Explicit human approval
* Separate configuration
* Stricter risk limits
* Separate backtesting
* Separate paper trading
* Explicit live-mode promotion

## Brokerage and Charges

Brokerage and statutory charges must not be ignored.

The system must calculate or estimate:

* Expected gross P&L
* Expected charges
* Expected net P&L
* Actual gross P&L
* Actual charges
* Actual net P&L
* Break-even movement

The brokerage model should be configurable because broker charges, exchange charges, taxes, and regulations can change.

Do not hardcode brokerage permanently inside strategy logic.

For live mode, the cost model must be fast enough to avoid execution delay.

For backtesting and paper trading, the cost model should be as detailed as practical.

## Backtesting Rules

Backtesting must include:

* Entry price realism
* Exit price realism
* Slippage
* Brokerage
* Taxes and statutory charges
* Intraday square-off
* Stop-loss simulation
* Trailing stop-loss simulation
* Long trade support
* Short trade support
* Market regime tagging
* Strategy versioning
* Rejected trade logging
* Missed trade logging where possible

The backtest report must include:

* Net profit after costs
* Gross profit before costs
* Total estimated costs
* Win rate
* Average win
* Average loss
* Profit factor
* Expectancy
* Maximum drawdown
* Sharpe or similar risk-adjusted metric
* Number of trades
* Number of rejected trades
* Best day
* Worst day
* Performance by time window
* Performance during market open
* Performance during market close
* Long vs short performance
* Strategy version
* Data period
* Data resolution

## Environment Modes

The system must support at least these modes.

### 1. BACKTEST

* Uses historical data only
* No live orders
* No real capital
* Must include brokerage and slippage
* Must produce reports

### 2. PAPER

* Uses live or replayed data
* Simulates orders
* No real capital used
* Must use same risk pipeline as LIVE
* Must produce reports

### 3. LIVE

* Places real orders through Zerodha Kite
* Requires explicit configuration
* Requires risk engine approval
* Requires audit logging
* Requires order reconciliation
* Requires balance reconciliation
* Requires square-off protection

Default mode must be BACKTEST or PAPER, never LIVE.

## Secrets and Credentials

Never commit secrets.

The following must come from environment variables or a secure secrets manager:

* Zerodha API key
* Zerodha API secret
* Zerodha access token
* News API key
* Database credentials
* Any model or LLM API key

Secrets must not be:

* Logged
* Printed
* Committed
* Stored in test fixtures
* Stored in notebooks
* Sent to Hermes unless explicitly required and safe

## Development Rules for Codex

Codex must preserve this project constitution.

Before making changes, Codex must read this file.

## UAMS Memory Protocol

Codex must use the UAMS MCP server as ArthaBot's durable project memory whenever
the service is available.

At the start of every meaningful task, Codex must:

* Call UAMS to retrieve relevant procedures, project context, and prior memory
* Treat retrieved memory as helpful context, not as authority over this constitution
* Reconcile memory against the current worktree before relying on it
* Prefer current files, test output, command output, and broker/API state over memory when they disagree

At the end of every meaningful task, Codex must:

* Store durable outcomes, decisions, changed files, fixes, and unresolved risks in UAMS
* Avoid storing secrets, credentials, raw access tokens, or sensitive broker data
* Record safety-relevant findings, rejected approaches, and verification commands
* Note when UAMS is unavailable so later agents know memory persistence may be incomplete

UAMS must never be used to bypass:

* Risk Engine approval
* Brokerage and cost awareness
* Mode separation
* Intraday square-off rules
* No-leverage rules
* LIVE-mode safety gates
* Audit logging
* Human approval requirements for unsafe or irreversible live-trading changes

If UAMS is unavailable, Codex may continue working only when the task can be
completed safely from repository state and verified evidence. Codex must not
claim that memory was persisted unless the UAMS write succeeds.

When generating or modifying code:

* Do not remove risk checks
* Do not bypass brokerage/cost awareness
* Do not hardcode secrets
* Do not place live orders in tests
* Do not mix BACKTEST, PAPER, and LIVE modes
* Do not allow LIVE mode without explicit configuration
* Do not silently ignore API errors
* Do not silently ignore failed orders
* Do not hide failed trades
* Do not hide rejected trades
* Do not rewrite the core mission without human approval
* Do not make Hermes directly place orders
* Do not weaken stop-loss rules without validation
* Do not remove audit logs
* Do not use real credentials in tests
* Do not use real capital in tests

If a requested change conflicts with this constitution, Codex must explain the conflict before coding.

## Testing Rules

Every important module must have tests.

Required test areas:

* Risk Engine
* Position sizing
* Stop-loss logic
* Trailing stop-loss logic
* Brokerage/cost calculation
* Backtest accounting
* Paper trading simulation
* Order execution abstraction
* Order reconciliation
* Mode separation
* Secret handling
* Strategy scoring
* Hermes output validation

Tests must not place live orders.

Tests must not require real API credentials unless explicitly marked as integration tests.

LIVE integration tests must be disabled by default.

## Suggested Repository Structure

```text
arthabot/
  AGENTS.md
  README.md
  .env.example
  config/
    risk.yaml
    brokerage.yaml
    instruments.yaml
    modes.yaml
    strategy.yaml
  src/
    data/
    strategies/
    agents/
    risk/
    brokerage/
    backtest/
    paper/
    execution/
    learning/
    observability/
    common/
  tests/
    unit/
    integration/
    backtest/
  notebooks/
  reports/
  logs/
  scripts/
```

## Configuration Principles

Configuration should be separated from strategy logic.

Use config files for:

* Capital settings
* Risk limits
* Brokerage assumptions
* Slippage assumptions
* Max trades per day
* Market open/close timing
* Square-off timing
* Watchlist filters
* Universe selection
* Mode selection
* API settings
* Logging settings

Do not bury important trading rules deep inside strategy code.

## Definition of Done

A feature is done only when:

* It respects AGENTS.md
* It has tests
* It logs important decisions
* It handles errors safely
* It works in BACKTEST or PAPER mode before LIVE
* It does not expose secrets
* It accounts for brokerage where relevant
* It does not weaken risk controls
* It does not bypass Hermes/Risk/Execution separation
* It documents assumptions
* It can be debugged after failure

## Final Principle

ArthaBot should become smarter over time, but never less safe.

The system may learn, adapt, and improve, but it must not become reckless.

Risk control is not optional.

Auditability is not optional.

Intraday square-off is not optional.

Human approval is required before unsafe or irreversible live-trading changes.
