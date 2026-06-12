from pathlib import Path


def test_dashboard_polls_runtime_health_and_shows_degraded_state():
    source = Path("dashboard/main.js").read_text(encoding="utf-8")

    assert "fetch('/api/health'" in source
    assert "Connected (PAPER, degraded)" in source
    assert "setInterval(refreshRuntimeHealth" in source


def test_dashboard_includes_remote_zerodha_reauthentication_controls():
    html = Path("dashboard/index.html").read_text(encoding="utf-8")
    source = Path("dashboard/main.js").read_text(encoding="utf-8")
    nginx = Path("dashboard/nginx.conf").read_text(encoding="utf-8")

    assert 'id="zerodha-login-url"' in html
    assert 'id="zerodha-redirect-url"' in html
    assert "'/api/auth/zerodha'" in source
    assert "'/api/auth/zerodha/exchange'" in source
    assert "location /api/auth/zerodha" in nginx


def test_paper_loop_imports_kite_session_client_for_dashboard_auth():
    source = Path("scripts/run_paper_loop.py").read_text(encoding="utf-8")

    assert "from kiteconnect import KiteConnect, KiteTicker" in source
