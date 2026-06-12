# ArthaBot

ArthaBot is a constitution-first intraday trading bot scaffold for the Indian stock market. Its default posture is safety: `BACKTEST` or `PAPER` mode, explicit `LIVE` promotion, brokerage-aware decisions, and auditable risk controls.

The system uses an autonomous decision engine ("Hermes") bounded by strict risk controls and a full observability suite. 

**IMPORTANT**: Please read `AGENTS.md` before changing any code. `AGENTS.md` acts as the constitution for this project.

## Core Features

- **Data Ingestion Engine**: Robust handling of live ticks, historical OHLCV, top movers, and news/sentiment data.
- **Hermes Decision Agent**: LLM-driven trade scoring and rationale formulation, rigorously bound by the Risk Engine.
- **Risk Engine**: Strictly enforces maximum risk, stop losses, trailing stops, forced intraday square-offs, and no-leverage rules.
- **Brokerage Engine**: Deterministic, pre-trade break-even calculation including all Indian statutory charges (STT, GST, SEBI, etc.).
- **Strict Mode Separation**:
  - `BACKTEST`: Validate on historical data with simulated slippage.
  - `PAPER`: Test signals on live data without deploying real capital.
  - `LIVE`: True execution via Zerodha Kite API (requires manual `approve_live.py` safety gate).
- **Observability Dashboard**: An integrated UI (`arthabot-dashboard`) for monitoring trades, performance, internal state, and remote token generation.

## Project Structure

```
├── AGENTS.md                  # The project constitution
├── config/                    # Configuration for risk, brokerage, strategy, etc.
├── dashboard/                 # Frontend UI for monitoring and token generation
├── docs/                      # Agent plans, statuses, and design specs
├── scripts/                   # CLI scripts for running loops, deployments, checks
├── src/arthabot/              # Core modules (Data, Strategies, Hermes, Risk, Brokerage)
└── tests/                     # Massive unit/integration test suite
```

## Setup & Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Shivamsharma6/artha_bot.git
   cd artha_bot
   ```

2. **Setup Environment**:
   Ensure you have Python 3.11+ and `uv` installed.
   ```bash
   uv sync
   ```

3. **Configure Environment Variables**:
   Copy the example `.env` file and fill in your credentials.
   ```bash
   cp .env.example .env
   ```
   **Required Variables**:
   - `ARTHABOT_MODE`: `PAPER` (default)
   - `ZERODHA_API_KEY`: Your Kite Connect API Key
   - `ZERODHA_API_SECRET`: Your Kite Connect API Secret
   - `DASHBOARD_ADMIN_TOKEN`: At least 16 random characters used for securing remote dashboard operations.

## Running Tests

The repository contains a highly resilient test suite covering integration bounds, reconciliation logic, risk pipelines, and more.

```bash
uv run pytest
```

## Daily Zerodha Login

Kite Connect access tokens expire at 6:00 AM the next day. ArthaBot automates the supported redirect capture, token exchange, read-only profile validation, and secure `.env` update, but Zerodha login and TOTP remain interactive:

```bash
uv run python scripts/login_zerodha.py
```

Configure the Kite Connect app redirect URL as `http://127.0.0.1:8765/`. After the browser login succeeds, restart the PAPER container/service so it loads the new environment value. The token file is written owner-only and the token is never printed.

For remote deployments, use the **Dashboard**. The dashboard's Zerodha Session panel displays the official login URL and accepts the full redirected URL after interactive login. The backend exchanges and validates the request token, then writes the access token securely to `data/zerodha.env`. Restart the ArthaBot container afterward.

## Usage & Scripts

ArthaBot provides CLI abstractions for managing all trading lifecycle events.

**Run Paper Loop Locally**:
```bash
uv run python scripts/run_paper_loop.py
```

**Deploy to EC2**:
There are automated scripts that package the application into Docker containers and deploy them via SSH to your remote instance:
```bash
./scripts/deploy_to_ec2.sh
./scripts/deploy_dashboard_to_ec2.sh
```

**Promoting to Live**:
Going live requires an explicit manual review to ensure paper trading expectancy was positive.
```bash
uv run python scripts/approve_live.py
```

## Persistence
`PAPER` runtime state is stored by default at `data/paper_runtime_state.json` and restored after process or container restart. JSONL audit stores rotate at 10 MB with five backups by default. 
When deployed remotely, `data/` and `logs/` are mounted persistently.

---

*ArthaBot strictly abides by its prime directive: Capital preservation comes before profit maximization.*
