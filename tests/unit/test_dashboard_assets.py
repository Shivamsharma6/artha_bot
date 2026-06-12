from pathlib import Path


def test_dashboard_polls_runtime_health_and_shows_degraded_state():
    source = Path("dashboard/main.js").read_text(encoding="utf-8")

    assert "fetch('/api/health'" in source
    assert "Connected (PAPER, degraded)" in source
    assert "setInterval(refreshRuntimeHealth" in source
