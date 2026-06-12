# ArthaBot

ArthaBot is a constitution-first intraday trading bot scaffold for the Indian
stock market. Its default posture is safety: BACKTEST or PAPER mode, explicit
LIVE promotion, brokerage-aware decisions, and auditable risk controls.

Read `AGENTS.md` before changing code.

## Daily Zerodha Login

Kite Connect access tokens expire at 6:00 AM the next day. ArthaBot automates
the supported redirect capture, token exchange, read-only profile validation,
and secure `.env` update, but Zerodha login and TOTP remain interactive:

```bash
uv run python scripts/login_zerodha.py
```

Configure the Kite Connect app redirect URL as
`http://127.0.0.1:8765/`. After the browser login succeeds, restart the PAPER
container/service so it loads the new environment value. The token file is
written owner-only and the token is never printed.

PAPER runtime state is stored by default at `data/paper_runtime_state.json` and
restored after process or container restart. JSONL audit stores rotate at 10 MB
with five backups by default; `data/` and `logs/` are mounted persistently by
the EC2 deployment script.

For remote deployments, set a random `DASHBOARD_ADMIN_TOKEN` of at least 16
characters. The dashboard's Zerodha Session panel displays the official login
URL and accepts the full redirected URL after interactive login. The backend
exchanges and validates the request token, then writes the access token to
`data/zerodha.env`. Restart the ArthaBot container afterward. The dashboard
never receives or displays the access token.
