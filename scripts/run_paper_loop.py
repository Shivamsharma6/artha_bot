#!/usr/bin/env python
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal

from arthabot.audit_store import JsonlAuditStore
from arthabot.brokerage import BrokerageCalculator, BrokerageConfig
from arthabot.config import load_runtime_config
from arthabot.deployment_config import load_deployment_config
from arthabot.execution import ExecutionEngine
from arthabot.http_clients import ZerodhaHttpClient, UrllibHttpTransport
from arthabot.instruments import InstrumentTokenCache, InstrumentTokenStore
from arthabot.live_feed import ZerodhaWebSocketFeedClient, FeedReconnectController, LiveFeedSupervisor
from arthabot.risk import RiskConfig, RiskEngine, TradeProposal
from arthabot.runtime_market_provider import RuntimeMarketSnapshotProvider, RuntimeStrategyCandidateComposer
from arthabot.runtime_pipeline import HermesAdapter, PaperRuntimePipeline
from arthabot.runtime_strategy_provider import load_runtime_strategy_config
from arthabot.secrets import SecretConfig, load_access_token_file
from arthabot.top_movers import KiteTopMoversClient
from arthabot.dashboard_api import (
    DashboardZerodhaAuth,
    app,
    broadcast_update,
    configure_runtime_state,
    configure_zerodha_auth,
    set_runtime_health,
)
from arthabot.http_clients import KiteAuthenticationError
from arthabot.runtime_state import RuntimeStateStore, deserialize_trades, serialize_trades
from arthabot.zerodha_auth import RemoteZerodhaSessionRenewal
import threading
import uvicorn
from kiteconnect import KiteConnect, KiteTicker


def build_hermes_proposal(candidate, now, *, entry: Decimal) -> TradeProposal:
    # Deterministic PAPER proposal built from a fresh broker tick. This is not
    # promoted to LIVE and does not bypass the Risk Engine.
    return TradeProposal(
        symbol=candidate.symbol,
        direction=candidate.direction,
        entry_price=entry,
        stop_loss=entry * Decimal("0.98") if candidate.direction.name == "LONG" else entry * Decimal("1.02"),
        target_price=entry * Decimal("1.04") if candidate.direction.name == "LONG" else entry * Decimal("0.96"),
        confidence=Decimal("0.8"),
        trailing_stop_step=Decimal("1"),
        timestamp=now,
        strategy_version=candidate.strategy_version,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ArthaBot PAPER trading loop with Kite WebSocket.")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--audit-path", default="logs/paper_loop.audit.jsonl")
    parser.add_argument("--instrument-store-path", default="data/instruments.json")
    parser.add_argument("--interval-seconds", type=int, default=10)
    parser.add_argument("--runtime-state-path", default="data/paper_runtime_state.json")
    parser.add_argument("--renewed-token-path", default="data/zerodha.env")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    renewed_token = load_access_token_file(args.renewed_token_path)
    if renewed_token:
        os.environ["ZERODHA_ACCESS_TOKEN"] = renewed_token
    try:
        secrets = SecretConfig.from_env(require_zerodha=True)
    except Exception as e:
        logging.error(f"Failed to load secrets: {e}")
        return 1

    deployment_config = load_deployment_config(args.config_dir)
    runtime_config = load_runtime_config(args.config_dir)
    strategy_config = load_runtime_strategy_config(f"{args.config_dir}/strategy.yaml")

    audit = JsonlAuditStore(args.audit_path)
    runtime_state_store = RuntimeStateStore(args.runtime_state_path)
    restored_runtime_state = runtime_state_store.load_or_default()
    configure_runtime_state(runtime_state_store)
    dashboard_kite = KiteConnect(api_key=secrets.zerodha_api_key or "")
    configure_zerodha_auth(
        DashboardZerodhaAuth(
            audit=audit,
            renewal=RemoteZerodhaSessionRenewal(
                api_secret=secrets.zerodha_api_secret or "",
                env_path=args.renewed_token_path,
                kite=dashboard_kite,
            ),
        )
    )

    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    logging.info("Dashboard API Server started on http://0.0.0.0:8080")

    def hold_degraded_dashboard(reason_code: str) -> int:
        set_runtime_health(trading_ready=False, reason_code=reason_code)
        logging.error("PAPER is stopped with %s; dashboard recovery remains available", reason_code)
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            return 1
    
    execution = ExecutionEngine()
    risk = RiskEngine(
        config=RiskConfig(
            starting_capital=runtime_config.risk.starting_capital,
            max_risk_per_trade_pct=runtime_config.risk.max_risk_per_trade_pct,
            max_daily_loss_pct=runtime_config.risk.max_daily_loss_pct,
            min_allocation_pct=runtime_config.risk.min_allocation_pct,
            max_trades_per_day=runtime_config.risk.max_trades_per_day,
            quote_max_age_seconds=runtime_config.risk.quote_max_age_seconds,
            square_off_time=runtime_config.risk.square_off_time,
        ),
        brokerage=BrokerageCalculator(BrokerageConfig())
    )

    latest_entry_prices: dict[str, Decimal] = {}

    def proposal_factory(candidate, now):
        return build_hermes_proposal(
            candidate,
            now,
            entry=latest_entry_prices[candidate.symbol],
        )

    pipeline = PaperRuntimePipeline(
        trading_date=datetime.now().date(),
        starting_capital=runtime_config.risk.starting_capital,
        execution=execution,
        risk=risk,
        hermes=HermesAdapter(proposal_factory=proposal_factory),
        audit=audit,
        max_tick_age_seconds=runtime_config.risk.quote_max_age_seconds,
    )
    restored_trades = deserialize_trades(restored_runtime_state.get("trades"))
    pipeline.session.restore_trades(restored_trades)
    pipeline.trades_today = sum(1 for trade in restored_trades if trade.accepted)

    zerodha_client = ZerodhaHttpClient(
        secret_config=secrets,
        transport=UrllibHttpTransport(base_url="https://api.kite.trade", timeout_seconds=3.0),
    )
    
    instrument_store = InstrumentTokenStore(args.instrument_store_path)
    instrument_cache = InstrumentTokenCache(client=lambda exchange: zerodha_client.fetch_instruments(exchange=exchange))
    
    symbols_to_track = []
    for job in deployment_config.scheduler.jobs:
        if job.type == "news_ingestion" and getattr(job, "symbols", None):
            symbols_to_track.extend(job.symbols)
            
    if not symbols_to_track:
        symbols_to_track = ["INFY", "RELIANCE"]

    tokens = []
    token_to_symbol = {}
    today = datetime.now().date()
    for sym in symbols_to_track:
        try:
            record = instrument_cache.lookup(exchange="NSE", tradingsymbol=sym, as_of=today)
            tok = record.instrument_token
        except (KeyError, ValueError):
            logging.info(f"Could not resolve token for {sym}, fetching from Kite...")
            try:
                instrument_cache.refresh(exchange="NSE", as_of=today)
                record = instrument_cache.lookup(exchange="NSE", tradingsymbol=sym, as_of=today)
                tok = record.instrument_token
            except Exception as e:
                logging.error(f"Failed to fetch instruments: {e}")
                tok = None
        
        if tok:
            tokens.append(tok)
            token_to_symbol[tok] = sym

    if not tokens:
        logging.error("No valid instrument tokens resolved.")
        return hold_degraded_dashboard("KITE_REAUTH_REQUIRED")

    feed_client = ZerodhaWebSocketFeedClient(
        secret_config=secrets,
        monitor=pipeline.feed, 
        ticker_factory=lambda key, tok: KiteTicker(key, tok),
        token_to_symbol=token_to_symbol,
    )

    reconnect_controller = FeedReconnectController(base_delay_seconds=2, max_delay_seconds=60, max_failures=10)
    supervisor = LiveFeedSupervisor(feed_client=feed_client, reconnect_controller=reconnect_controller, audit=audit)

    logging.info(f"Connecting to Kite WebSocket for tokens {list(token_to_symbol.values())}...")
    decision = supervisor.connect(tokens=tokens, now=datetime.now())
    if decision.must_stop_trading:
        set_runtime_health(trading_ready=False, reason_code=decision.reason_code)
        logging.error("Failed to connect to Kite WebSocket.")
        return hold_degraded_dashboard(decision.reason_code)

    universe_symbols = [
        "NSE:INFY", "NSE:RELIANCE", "NSE:TCS", "NSE:HDFCBANK", "NSE:SBIN",
        "NSE:ICICIBANK", "NSE:KOTAKBANK", "NSE:LT", "NSE:ITC", "NSE:AXISBANK"
    ]
    top_movers_client = KiteTopMoversClient(http_client=zerodha_client, universe_symbols=universe_symbols)

    market_provider = RuntimeMarketSnapshotProvider(
        top_movers_client=top_movers_client, 
        max_age_seconds=runtime_config.risk.quote_max_age_seconds,
    )
    composer = RuntimeStrategyCandidateComposer(
        market_provider=market_provider,
        strategy_config=strategy_config
    )

    logging.info("Paper trading loop started. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(args.interval_seconds)
            now = datetime.now()
            
            for sym in symbols_to_track:
                health = pipeline.feed.health(sym, now=now)
                if health.ok:
                    tick = pipeline.feed.latest_tick(sym)
                    logging.info(f"[{sym}] Tick OK: Price {tick.price}, Vol {tick.volume}")
                else:
                    logging.info(f"[{sym}] Feed Health: {health.reason_code}")

            feed_ready = all(pipeline.feed.health(sym, now=now).ok for sym in symbols_to_track)
            set_runtime_health(
                trading_ready=feed_ready,
                reason_code="READY" if feed_ready else "MARKET_DATA_UNAVAILABLE",
            )
                    
            try:
                candidates = list(composer.generate_from_top_movers(limit=5, now=now))
            except KiteAuthenticationError as exc:
                set_runtime_health(trading_ready=False, reason_code=exc.reason_code)
                audit.append(
                    event_type="kite_reauthentication_required",
                    payload={"reason_code": exc.reason_code, "timestamp": now.isoformat()},
                )
                logging.error("Zerodha session expired; run scripts/login_zerodha.py and restart PAPER")
                return hold_degraded_dashboard(exc.reason_code)
            except Exception as exc:
                set_runtime_health(trading_ready=False, reason_code="CANDIDATE_PROVIDER_FAILED")
                logging.exception("Candidate refresh failed; skipping this cycle")
                audit.append(
                    event_type="paper_candidate_refresh_failed",
                    payload={
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "timestamp": now.isoformat(),
                    },
                )
                candidates = []
            for candidate in candidates:
                logging.info(f"Processing candidate: {candidate.symbol} ({candidate.direction.name})")
                health = pipeline.feed.health(candidate.symbol, now=now)
                if not health.ok:
                    pipeline.process_candidate(candidate, now=now)
                    continue
                latest_entry_prices[candidate.symbol] = pipeline.feed.latest_tick(candidate.symbol).price
                pipeline.process_candidate(candidate, now=now)
            
            # Calculate stats
            accepted_trades = [t for t in pipeline.session.trades if t.accepted]
            total_trades = len(accepted_trades)
            win_count = sum(1 for t in accepted_trades if (t.gross_pnl - t.total_costs) > 0)
            win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
            pnl = sum((t.gross_pnl - t.total_costs) for t in accepted_trades)
            capital = float(pipeline.session.starting_capital + pnl)
            positions = [{"symbol": t.symbol, "pnl": float(t.gross_pnl - t.total_costs)} for t in accepted_trades]

            # Broadcast the latest state to the dashboard
            broadcast_update({
                "type": "MARKET_TICK",
                "timestamp": now.isoformat(),
                "open_positions": len(positions),
                "pnl": float(pnl),
                "win_rate": float(win_rate),
                "total_trades": total_trades,
                "capital": capital,
                "starting_capital": float(pipeline.session.starting_capital),
                "daily_loss_limit": float(capital * runtime_config.risk.max_daily_loss_pct),
                "mode": "PAPER",
                "positions_list": positions,
                "candidates": [f"{c.symbol} {c.direction.name} {c.strategy_version}" for c in candidates],
                "trades": serialize_trades(list(pipeline.session.trades)),
            })

    except KeyboardInterrupt:
        logging.info("Stopping paper loop...")
    finally:
        feed_client.disconnect()
        report = pipeline.daily_report()
        logging.info(f"Daily Report: {report}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
