from datetime import time
from pathlib import Path

from arthabot.config import parse_market_time


def test_dashboard_polls_runtime_health_and_shows_degraded_state():
    source = Path("dashboard/main.js").read_text(encoding="utf-8")

    assert "fetch('/api/health'" in source
    assert "Connected (PAPER, degraded:" in source
    assert "setInterval(refreshRuntimeHealth" in source


def test_dashboard_includes_remote_zerodha_reauthentication_controls():
    html = Path("dashboard/index.html").read_text(encoding="utf-8")
    source = Path("dashboard/main.js").read_text(encoding="utf-8")
    nginx = Path("dashboard/nginx.conf").read_text(encoding="utf-8")

    assert 'id="zerodha-auth-modal"' in html
    assert 'id="zerodha-login-url"' in html
    assert 'id="zerodha-redirect-url"' in html
    assert "'/api/auth/zerodha'" in source
    assert "'/api/auth/zerodha/exchange'" in source
    assert "location /api/auth/zerodha" in nginx
    assert "proxy_read_timeout 300s" in nginx
    assert "KITE_REAUTH_REQUIRED" in source
    assert "ws.send('ping')" in source
    assert "reconnectDelay" in source
    assert "const net = data.capital;" in source


def test_paper_loop_imports_kite_session_client_for_dashboard_auth():
    source = Path("scripts/run_paper_loop.py").read_text(encoding="utf-8")

    assert "from kiteconnect import KiteConnect, KiteTicker" in source


def test_paper_loop_parses_configured_market_time():
    assert parse_market_time("15:15") == time(15, 15)
    assert parse_market_time(time(15, 15)) == time(15, 15)
